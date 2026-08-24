import logging
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.vector_chunk import CodeChunk
from app.models.base import AsyncSessionLocal

logger = logging.getLogger("prguard")


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_code(content: str, path: str, language: str) -> list[dict]:
    """
    Split a file into function-level chunks.
    Falls back to line-based chunking for non-Python files.
    """
    if language == "python":
        return _chunk_python(content, path)
    else:
        return _chunk_by_lines(content, path, language)


def _chunk_python(content: str, path: str) -> list[dict]:
    """
    Split Python files at function and class boundaries.
    Each function/class becomes one chunk.
    """
    lines = content.split("\n")
    chunks = []
    current_chunk_lines = []
    current_start = 0
    in_chunk = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # detect function or class definition
        is_definition = (
            stripped.startswith("def ")
            or stripped.startswith("async def ")
            or stripped.startswith("class ")
        )

        if is_definition and in_chunk and current_chunk_lines:
            # save previous chunk
            chunk_content = "\n".join(current_chunk_lines).strip()
            if chunk_content:
                chunks.append({
                    "content":    chunk_content,
                    "path":       path,
                    "start_line": current_start + 1,
                    "end_line":   i,
                    "language":   "python",
                })
            current_chunk_lines = [line]
            current_start = i
        else:
            if is_definition:
                in_chunk = True
                current_start = i
            current_chunk_lines.append(line)

    # save last chunk
    if current_chunk_lines:
        chunk_content = "\n".join(current_chunk_lines).strip()
        if chunk_content:
            chunks.append({
                "content":    chunk_content,
                "path":       path,
                "start_line": current_start + 1,
                "end_line":   len(lines),
                "language":   "python",
            })

    # if no functions found treat whole file as one chunk
    if not chunks:
        chunks.append({
            "content":    content.strip(),
            "path":       path,
            "start_line": 1,
            "end_line":   len(lines),
            "language":   "python",
        })

    return chunks


def _chunk_by_lines(
    content: str,
    path: str,
    language: str,
    chunk_size: int = 60,
    overlap: int = 10,
) -> list[dict]:
    """
    For non-Python files split into overlapping line windows.
    Overlap ensures context is not lost at chunk boundaries.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    step = chunk_size - overlap
    if step <= 0:
        raise ValueError("overlap must be strictly less than chunk_size")

    lines = content.split("\n")
    chunks = []
    start = 0

    while start < len(lines):
        end = min(start + chunk_size, len(lines))
        chunk_lines = lines[start:end]
        chunk_content = "\n".join(chunk_lines).strip()

        if chunk_content:
            chunks.append({
                "content":    chunk_content,
                "path":       path,
                "start_line": start + 1,
                "end_line":   end,
                "language":   language,
            })

        start += step  # overlap for context continuity

    return chunks


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed(text: str) -> list[float]:
    """Convert a single text string into an embedding vector."""
    if not settings.OPENAI_API_KEY:
        raise ValueError(
            "RAG requires OPENAI_API_KEY. "
            "Add it to .env or disable RAG with "
            "CHAT_ENABLE_RAG=False"
        )
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    res = await client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return res.data[0].embedding


# ── Indexing ──────────────────────────────────────────────────────────────────

async def index_repo(repo: str, files: list[dict]) -> dict:
    """
    Index all files from a repo into PostgreSQL using pgvector.
    Called after github.py fetches all files.

    files = [{ path, content, language, size }]
    Returns indexing stats.
    """
    async with AsyncSessionLocal() as session:
        # clear existing index for this repo
        # so re-indexing is always fresh
        await session.execute(
            CodeChunk.__table__.delete().where(CodeChunk.repo_name == repo)
        )
        await session.commit()

        all_chunks = []
        for file in files:
            chunks = chunk_code(
                content=file["content"],
                path=file["path"],
                language=file["language"],
            )
            all_chunks.extend(chunks)

        if not all_chunks:
            return {"indexed": 0, "chunks": 0, "repo": repo}

        # batch embed for performance
        BATCH_SIZE = 256
        total_indexed = 0
        total_chunks = len(all_chunks)
        
        print(f"DEBUG: Indexing {total_chunks} code snippets for {repo}...")

        for i in range(0, total_chunks, BATCH_SIZE):
            batch = all_chunks[i: i + BATCH_SIZE]
            texts = [c["content"] for c in batch]

            # generate embeddings via OpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError(
                    "RAG requires OPENAI_API_KEY. "
                    "Add it to .env or disable RAG with "
                    "CHAT_ENABLE_RAG=False"
                )
            _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            res = await _client.embeddings.create(
                input=texts,
                model="text-embedding-3-small"
            )
            vectors = [item.embedding for item in res.data]

            db_chunks = []
            for j, c in enumerate(batch):
                db_chunk = CodeChunk(
                    repo_name=repo,
                    path=c["path"],
                    language=c["language"],
                    start_line=c["start_line"],
                    end_line=c["end_line"],
                    content=c["content"],
                    embedding=vectors[j]
                )
                db_chunks.append(db_chunk)

            session.add_all(db_chunks)
            await session.commit()

            total_indexed += len(batch)
            if (i // BATCH_SIZE) % 5 == 0:
                print(f"DEBUG: Indexing in progress... {total_indexed}/{total_chunks} ({(total_indexed/total_chunks)*100:.1f}%)")

        return {
            "repo":    repo,
            "files":   len(files),
            "chunks":  total_indexed,
            "indexed": True,
        }


# ── Retrieval ─────────────────────────────────────────────────────────────────

async def retrieve(
    repo: str,
    query: str,
    n_results: int = 8,
    language_filter: Optional[str] = None,
) -> list[dict]:
    """
    Search pgvector for the most relevant code chunks.
    Returns ranked list of chunks with metadata.
    """
    # embed the query
    query_vector = await embed(query)

    async with AsyncSessionLocal() as session:
        stmt = select(CodeChunk).where(CodeChunk.repo_name == repo)
        if language_filter:
            stmt = stmt.where(CodeChunk.language == language_filter)
            
        # Order by cosine distance
        stmt = stmt.order_by(CodeChunk.embedding.cosine_distance(query_vector)).limit(n_results)
        
        result = await session.execute(stmt)
        chunks = result.scalars().all()

        results = []
        for c in chunks:
            results.append({
                "content":    c.content,
                "path":       c.path,
                "start_line": c.start_line,
                "end_line":   c.end_line,
                "language":   c.language,
                "similarity": 1.0, # Distance isn't natively returned with scalar, but it's ordered correctly
            })

        return results


async def get_file_chunks(repo: str, path: str) -> list[dict]:
    """Return all indexed chunks for a specific repo-relative file path."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(CodeChunk)
            .where(CodeChunk.repo_name == repo)
            .where(CodeChunk.path == path)
            .order_by(CodeChunk.start_line.asc(), CodeChunk.end_line.asc())
        )
        result = await session.execute(stmt)
        chunks = result.scalars().all()

    return [
        {
            "content": c.content,
            "path": c.path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "language": c.language,
            "similarity": 1.0,
        }
        for c in chunks
    ]


async def get_file_references(repo: str, path: str, n_results: int = 8) -> list[dict]:
    """Find other indexed chunks that reference a specific file path or module name."""
    basename = path.rsplit("/", 1)[-1]
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    dotted = path.replace("/", ".")
    module_path = dotted.rsplit(".", 1)[0] if "." in dotted else dotted

    search_terms = []
    for term in (path, basename, stem, dotted, module_path):
        normalized = term.strip()
        if normalized and normalized not in search_terms:
            search_terms.append(normalized)

    if not search_terms:
        return []

    conditions = [CodeChunk.content.ilike(f"%{term}%") for term in search_terms]

    async with AsyncSessionLocal() as session:
        stmt = (
            select(CodeChunk)
            .where(CodeChunk.repo_name == repo)
            .where(CodeChunk.path != path)
            .where(or_(*conditions))
            .order_by(CodeChunk.path.asc(), CodeChunk.start_line.asc())
            .limit(n_results)
        )
        result = await session.execute(stmt)
        chunks = result.scalars().all()

    return [
        {
            "content": c.content,
            "path": c.path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "language": c.language,
            "similarity": 1.0,
        }
        for c in chunks
    ]


def format_file_explanation_context(file_path: str, file_chunks: list[dict], references: list[dict]) -> str:
    """Build grounded context for file explanation requests."""
    parts = [f"Target file: {file_path}"]

    if file_chunks:
        parts.append("Indexed file content:")
        for chunk in file_chunks:
            parts.append(
                f"--- {chunk['path']} (lines {chunk['start_line']}-{chunk['end_line']}) ---\n"
                f"{chunk['content']}"
            )

    if references:
        parts.append("Other indexed code that references this file or module:")
        for ref in references:
            excerpt = ref["content"][:500].strip()
            parts.append(
                f"--- {ref['path']} (lines {ref['start_line']}-{ref['end_line']}) ---\n"
                f"{excerpt}"
            )
    else:
        parts.append("Other indexed code that references this file or module: none found.")

    parts.append(
        "Use only the indexed code above. Explain what the file does, why it exists in PRGuard, "
        "how it participates in repo analysis or other flows, and what depends on it if anything. "
        "Do not use boilerplate headings or generic filler."
    )

    return "\n\n".join(parts)


# ── Format for LLM prompt ─────────────────────────────────────────────────────

def format_chunks_for_prompt(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a clean string
    to inject into the LLM prompt.
    """
    if not chunks:
        return "No relevant code found."

    parts = []
    for chunk in chunks:
        parts.append(
            f"--- {chunk['path']} "
            f"(lines {chunk['start_line']}-{chunk['end_line']}) ---\n"
            f"{chunk['content']}"
        )

    return "\n\n".join(parts)


# ── Check if repo is indexed ──────────────────────────────────────────────────

async def is_indexed(repo: str) -> bool:
    """Check if a repo has been indexed into pgvector."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(func.count()).where(CodeChunk.repo_name == repo)
            result = await session.execute(stmt)
            count = result.scalar() or 0
            return count > 0
    except Exception:
        logger.exception(f"Failed to check index status for repo={repo}")
        return False


async def get_index_stats(repo: str) -> dict:
    """Get stats about a repo's index."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(func.count()).where(CodeChunk.repo_name == repo)
            result = await session.execute(stmt)
            count = result.scalar() or 0
            return {
                "repo": repo,
                "chunks": count,
                "indexed": count > 0
            }
    except Exception as e:
        logger.exception(f"Failed to get index stats for repo={repo}: {e}")
        return {"repo": repo, "chunks": 0, "indexed": False}
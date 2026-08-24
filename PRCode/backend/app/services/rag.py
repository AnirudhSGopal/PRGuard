import os
import uuid
import logging
import threading
from typing import Optional
from fastapi.concurrency import run_in_threadpool
from app.config import settings

try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter  # noqa: F401
except ImportError:
    OTLPSpanExporter = None

logger = logging.getLogger("prguard")

# ── Lazy-loaded heavy dependencies ────────────────────────────────────────────
# ChromaDB + SentenceTransformers are loaded on first use, NOT at import time.
# This prevents the server from blocking for 30-60s during startup.

_chroma_client = None
_embedding_model = None
_chroma_lock = threading.Lock()
_embedding_lock = threading.Lock()


def _get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        with _chroma_lock:
            if _chroma_client is None:
                logger.info("[RAG] Initializing ChromaDB client (first use)...")
                import chromadb
                from chromadb.config import Settings as ChromaSettings
                _chroma_client = chromadb.PersistentClient(
                    path=settings.CHROMA_DB_PATH,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                logger.info("[RAG] ChromaDB client ready.")
    return _chroma_client


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                logger.info("[RAG] Loading embedding model (first use, may take a moment)...")
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("[RAG] Embedding model loaded.")
    return _embedding_model


# ── Collection per repo ───────────────────────────────────────────────────────

def get_collection(repo: str):
    """
    Get or create a ChromaDB collection for a repo.
    Each repo gets its own isolated collection.
    Collection name must be alphanumeric + dashes only.
    """
    collection_name = repo.replace("/", "--").replace("_", "-").lower()
    return _get_chroma_client().get_or_create_collection(
        name=collection_name,
        metadata={"repo": repo},
    )


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

def embed(texts: list[str]) -> list[list[float]]:
    """Convert a list of text strings into embedding vectors."""
    return _get_embedding_model().encode(texts, show_progress_bar=False).tolist()


# ── Indexing ──────────────────────────────────────────────────────────────────

async def index_repo(repo: str, files: list[dict]) -> dict:
    """
    Index all files from a repo into ChromaDB.
    Called after github.py fetches all files.

    files = [{ path, content, language, size }]
    Returns indexing stats.
    """
    collection = get_collection(repo)

    # clear existing index for this repo
    # clear existing index for this repo
    # so re-indexing is always fresh
    existing = await run_in_threadpool(collection.get)
    if existing["ids"]:
        await run_in_threadpool(lambda: collection.delete(ids=existing["ids"]))

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

    # batch embed for performance (Higher is faster but uses more RAM)
    BATCH_SIZE = 256
    total_indexed = 0
    total_chunks = len(all_chunks)
    
    print(f"DEBUG: Indexing {total_chunks} code snippets for {repo}...")

    for i in range(0, total_chunks, BATCH_SIZE):
        batch = all_chunks[i: i + BATCH_SIZE]
        texts = [c["content"] for c in batch]

        # generate embeddings
        # 🏃‍♂️ Background Task: Run heavy CPU embeddings in a separate thread so it doesn't freeze the whole backend
        vectors = await run_in_threadpool(lambda: embed(texts))

        # build ChromaDB inputs
        ids = [str(uuid.uuid4()) for _ in batch]
        metadatas = [
            {
                "path":       c["path"],
                "start_line": c["start_line"],
                "end_line":   c["end_line"],
                "language":   c["language"],
                "repo":       repo,
            }
            for c in batch
        ]

        await run_in_threadpool(
            lambda: collection.add(
                ids=ids,
                embeddings=vectors,
                documents=texts,
                metadatas=metadatas,
            )
        )

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
    Search ChromaDB for the most relevant code chunks.
    Returns ranked list of chunks with metadata.
    """
    collection = get_collection(repo)

    # check if collection has any data
    count = await run_in_threadpool(collection.count)
    if count == 0:
        return []

    # embed the query
    query_vector = await run_in_threadpool(lambda: embed([query])[0])

    # build filter
    where = {"repo": repo}
    if language_filter:
        where["language"] = language_filter

    results = await run_in_threadpool(
        lambda: collection.query(
            query_embeddings=[query_vector],
            n_results=min(n_results, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    )

    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        distance = results["distances"][0][i]

        # convert distance to similarity score (0-1)
        # ChromaDB returns L2 distance — lower = more similar
        similarity = round(1 / (1 + distance), 3)

        chunks.append({
            "content":    doc,
            "path":       meta["path"],
            "start_line": meta["start_line"],
            "end_line":   meta["end_line"],
            "language":   meta["language"],
            "similarity": similarity,
        })

    # sort by similarity highest first
    chunks.sort(key=lambda x: x["similarity"], reverse=True)
    return chunks


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
    """Check if a repo has been indexed into ChromaDB."""
    try:
        collection = get_collection(repo)
        count = await run_in_threadpool(lambda: collection.count())
        return count > 0
    except Exception:
        logger.exception(f"Failed to check index status for repo={repo}")
        return False


def get_index_stats(repo: str) -> dict:
    """Get stats about a repo's index."""
    try:
        collection = get_collection(repo)
        count = collection.count()
        return {
            "repo":    repo,
            "chunks":  count,
            "indexed": count > 0,
        }
    except Exception as e:
        logger.exception(f"Failed to get index stats for repo={repo}: {e}")
        return {"repo": repo, "chunks": 0, "indexed": False}
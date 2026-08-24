import asyncio
import logging
from app.services.github import fetch_all_files, fetch_issue
from app.services.rag import index_repo, retrieve, format_chunks_for_prompt
from app.services.llm import generate, handle_llm_error
from app.services.diff_parser import parse_diff

logger = logging.getLogger("prguard")


# ── Index repo worker ─────────────────────────────────────────────────────────

def run_index_repo(repo: str, token: str = None, token_ref: str = None) -> dict:
    """
    Background worker function for indexing a repo.
    Runs in a separate RQ worker process.

    Flow:
    1. Fetch all files from GitHub
    2. Chunk + embed + store in ChromaDB
    3. Return stats
    """
    try:
        if token is None:
            from app.services.queue import resolve_secret_ref
            token = resolve_secret_ref(token_ref)
        if not token:
            raise ValueError("Missing indexing token")
        # fetch all files from GitHub
        files = asyncio.run(
            fetch_all_files(repo=repo, token=token)
        )

        if not files:
            return {
                "status":  "failed",
                "repo":    repo,
                "error":   "No files found in repo",
                "indexed": False,
            }

        # index into ChromaDB
        stats = asyncio.run(
            index_repo(repo=repo, files=files)
        )

        return {
            "status":  "completed",
            "repo":    repo,
            "files":   stats["files"],
            "chunks":  stats["chunks"],
            "indexed": True,
        }

    except Exception as e:
        return {
            "status":  "failed",
            "repo":    repo,
            "error":   str(e),
            "indexed": False,
        }


# ── PR review worker ──────────────────────────────────────────────────────────

def run_pr_review(
    repo:      str,
    pr_number: int,
    token:     str = None,
    provider:  str = "claude",
    api_key:   str = None,
    token_ref: str = None,
    api_key_ref: str = None,
) -> dict:
    """
    Background worker function for reviewing a PR.
    Runs in a separate RQ worker process.

    Flow:
    1. Fetch PR diff from GitHub
    2. Parse diff into changed files + lines
    3. Retrieve relevant chunks from ChromaDB
    4. Send diff + chunks to LLM for review
    5. Post review comment back to GitHub PR
    """
    try:
        from app.services.github import fetch_pr_diff, post_pr_comment
        from app.services.queue import resolve_secret_ref

        if not token:
            token = resolve_secret_ref(token_ref)
        if not api_key:
            api_key = resolve_secret_ref(api_key_ref)
        if not token or not api_key:
            return {"status": "failed", "error": "Missing token or API key"}

        # fetch the PR diff
        diff_text = asyncio.run(
            fetch_pr_diff(
                repo=repo,
                pr_number=pr_number,
                token=token,
            )
        )

        if not diff_text:
            return {
                "status": "failed",
                "error":  "Could not fetch PR diff",
            }

        # parse diff into structured format
        parsed = parse_diff(diff_text)

        # build question from complete file chunks without cutting file entries mid-block
        changed_files = [f["path"] for f in parsed["files"]]
        max_diff_chars = 3000
        diff_parts = []
        used_chars = 0
        for file in parsed["files"]:
            file_block = f"\n--- {file['path']} [{file['status']}] ---\n"
            for hunk in file.get("hunks", []):
                file_block += f"@@ {hunk.get('header', '')} @@\n"
                for line in hunk.get("lines", []):
                    prefix = {"added": "+", "removed": "-", "context": " "}.get(line.get("type"), " ")
                    file_block += f"{prefix} {line.get('content', '')}\n"
            remaining_chars = max_diff_chars - used_chars
            if remaining_chars <= 0:
                break

            if len(file_block) > remaining_chars:
                # Ensure we always include at least a truncated portion of the first file.
                if used_chars == 0:
                    marker = "\n...[Diff truncated due to prompt size limit]...\n"
                    slice_len = max(0, remaining_chars - len(marker))
                    truncated_block = file_block[:slice_len] + marker
                    diff_parts.append(truncated_block)
                break

            diff_parts.append(file_block)
            used_chars += len(file_block)
        diff_text_for_prompt = "".join(diff_parts)

        if not diff_text_for_prompt.strip() or len(diff_text_for_prompt.strip()) < 80:
            logger.warning(
                "[PR_REVIEW] diff_text_for_prompt is empty or very small (chars=%s, files=%s)",
                len(diff_text_for_prompt),
                len(parsed.get("files", [])),
            )

        question = (
            f"Review these changes in PR #{pr_number}:\n"
            f"Files changed: {', '.join(changed_files)}\n\n"
            f"Diff:\n{diff_text_for_prompt}"
        )

        # generate review using LLM + RAG
        result = asyncio.run(
            generate(
                question=question,
                repo=repo,
                history=[],
                provider=provider,
                api_key=api_key,
                n_chunks=6,
            )
        )

        # post review comment to GitHub PR
        comment_body = (
            f"## PRGuard AI Review\n\n"
            f"{result['answer']}\n\n"
            f"---\n"
            f"*Reviewed by PRGuard using {provider}*"
        )

        asyncio.run(
            post_pr_comment(
                repo=repo,
                pr_number=pr_number,
                body=comment_body,
                token=token,
            )
        )

        return {
            "status":   "completed",
            "repo":     repo,
            "pr":       pr_number,
            "provider": provider,
            "chunks":   result["chunks"],
        }

    except Exception as e:
        return {
            "status": "failed",
            "repo":   repo,
            "pr":     pr_number,
            "error":  str(e),
        }
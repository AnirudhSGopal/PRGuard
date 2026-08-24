"""
Background task workers for PR review and repository indexing.
These functions create their own DB sessions and are safe to run
as fire-and-forget asyncio tasks.
"""

import logging

from app.models.base import AsyncSessionLocal
from app.services import rag, github
from app.services import llm
from app.services.diff_parser import parse_diff, format_diff_for_prompt
from app.models.review import Review
from app.models.webhook import WebhookEvent

logger = logging.getLogger(__name__)

# In-memory job status tracking for background indexing jobs.
_job_status: dict[str, dict] = {}


async def run_pr_review(
    repo: str,
    pr_number: int,
    token: str,
    provider: str = "claude",
    api_key: str = "",
) -> None:
    """
    Perform an AI-powered review of a GitHub Pull Request.

    Steps:
    1. Fetch the PR diff from GitHub
    2. Parse the diff into structured data
    3. Generate an AI review using the LLM service
    4. Post the review comment back to the GitHub PR
    5. Save the review result to the database
    """
    db = AsyncSessionLocal()
    try:
        logger.info(f"[PR_REVIEW] Starting review for {repo} PR #{pr_number}")

        # 1. Fetch PR diff from GitHub
        diff_text = await github.fetch_pr_diff(repo, pr_number, token)
        if not diff_text:
            logger.warning(f"[PR_REVIEW] No diff found for {repo} PR #{pr_number}")
            return

        # 2. Parse the diff
        parsed_diff = parse_diff(diff_text)
        diff_prompt = format_diff_for_prompt(parsed_diff)

        # 3. Generate AI review
        review_prompt = (
            f"Review this pull request diff for repository {repo} "
            f"(PR #{pr_number}).\n\n"
            f"Analyze the changes for:\n"
            f"- Bugs and potential issues\n"
            f"- Security vulnerabilities\n"
            f"- Code quality and best practices\n"
            f"- Performance concerns\n\n"
            f"Diff:\n{diff_prompt}"
        )

        result = await llm.generate(
            question=review_prompt,
            repo=repo,
            history=[],
            provider=provider,
            api_key=api_key,
            n_chunks=0,  # No RAG for PR reviews — we use the diff directly
        )

        review_text = result.get("answer", "") if result else ""
        if not review_text:
            logger.warning(f"[PR_REVIEW] LLM returned empty review for {repo} PR #{pr_number}")
            return

        # 4. Post review comment back to GitHub PR
        posted = await github.post_pr_comment(
            repo=repo,
            pr_number=pr_number,
            body=f"## 🛡️ PRGuard AI Review\n\n{review_text}",
            token=token,
        )

        if posted:
            logger.info(f"[PR_REVIEW] Review posted for {repo} PR #{pr_number}")
        else:
            logger.warning(f"[PR_REVIEW] Failed to post review comment for {repo} PR #{pr_number}")

        # 5. Save review result to database
        review = Review(
            user_id="system",
            repo_name=repo,
            issue_number=pr_number,
            issue_title=f"PR #{pr_number}",
            answer=review_text,
            fix=None,
            chunks_used=None,
        )
        db.add(review)
        await db.commit()
        logger.info(f"[PR_REVIEW] Review saved to database for {repo} PR #{pr_number}")

    except Exception as e:
        logger.error(f"[PR_REVIEW] Failed to review {repo} PR #{pr_number}: {e}", exc_info=True)
    finally:
        await db.close()


async def run_index_repo(
    repo: str,
    token: str,
    job_id: str | None = None,
) -> None:
    """
    Index a repository's source code into the vector store for RAG.

    Steps:
    1. Fetch all source files from GitHub
    2. Index them into pgvector using the RAG service
    3. Update job status if job_id is provided
    """
    db = AsyncSessionLocal()
    try:
        logger.info(f"[INDEX] Starting indexing for {repo} (job_id={job_id})")

        if job_id:
            _job_status[job_id] = {"status": "processing", "repo": repo}

        # 1. Fetch all files from GitHub
        files = await github.fetch_all_files(repo=repo, token=token)
        if not files:
            logger.warning(f"[INDEX] No source files found in {repo}")
            if job_id:
                _job_status[job_id] = {
                    "status": "completed",
                    "repo": repo,
                    "files": 0,
                    "chunks": 0,
                }
            return

        # 2. Index into vector store
        result = await rag.index_repo(repo=repo, files=files)

        logger.info(
            f"[INDEX] Indexing complete for {repo}: "
            f"{result.get('files', 0)} files, {result.get('chunks', 0)} chunks"
        )

        if job_id:
            _job_status[job_id] = {
                "status": "completed",
                "repo": repo,
                "files": result.get("files", 0),
                "chunks": result.get("chunks", 0),
            }

    except Exception as e:
        logger.error(f"[INDEX] Failed to index {repo}: {e}", exc_info=True)
        if job_id:
            _job_status[job_id] = {
                "status": "failed",
                "repo": repo,
                "error": str(e),
            }
    finally:
        await db.close()

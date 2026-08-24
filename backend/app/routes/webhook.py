import json
import hmac
import hashlib
import asyncio
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from app.config import settings
from app.services.diff_parser import get_diff_summary, parse_diff
import uuid
from workers.review_worker import run_pr_review, run_index_repo
from app.models.webhook import WebhookEvent
from app.models.base import get_db, AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware import logger

router = APIRouter()


def _handle_task_error(task):
    """Callback for asyncio tasks — logs unhandled exceptions."""
    if task.exception():
        logger.error(
            f"Background task failed: {task.exception()}",
            exc_info=task.exception(),
        )


# ── Signature verification ────────────────────────────────────────────────────

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify GitHub webhook HMAC signature.
    GitHub signs every webhook with your secret.
    If signature doesn't match → reject the request.
    """
    if not signature:
        return False

    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    expected_sig = f"sha256={expected}"
    return hmac.compare_digest(expected_sig, signature)


# ── Main webhook endpoint ─────────────────────────────────────────────────────

@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str     = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
    db: AsyncSession        = Depends(get_db),
):
    """
    Main GitHub webhook handler.

    GitHub sends events here when:
    - A PR is opened, closed, updated
    - A push is made to a branch
    - An issue is created

    Work is executed inline so the app stays compatible with free-tier hosts.
    """

    # 1. read raw body first for signature check
    payload_bytes = await request.body()

    # 2. verify signature — reject if invalid
    if settings.GITHUB_WEBHOOK_SECRET:
        if not verify_webhook_signature(payload_bytes, x_hub_signature_256):
            raise HTTPException(
                status_code=401,
                detail="Invalid webhook signature"
            )

    # 3. parse payload
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 4. get repo name
    repo_name = (payload.get("repository") or {}).get("full_name") or "unknown"

    # 5. save webhook event to database
    event = WebhookEvent(
        event_type=x_github_event,
        repo_name=repo_name,
        payload=payload_bytes.decode("utf-8"),
        status="received",
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # 6. route to correct handler
    if x_github_event == "pull_request":
        task = asyncio.create_task(_handle_pull_request(payload, repo_name, event.id))
        task.add_done_callback(_handle_task_error)

    elif x_github_event == "push":
        task = asyncio.create_task(_handle_push(payload, repo_name))
        task.add_done_callback(_handle_task_error)

    elif x_github_event == "issues":
        await _handle_issue(payload, repo_name, db)

    elif x_github_event == "ping":
        return {"status": "pong", "message": "Webhook connected successfully"}

    # 7. respond with the processed event summary
    return JSONResponse(
        status_code=202,
        content={
            "status":  "accepted",
            "event":   x_github_event,
            "repo":    repo_name,
        }
    )


# ── Pull request handler ──────────────────────────────────────────────────────

async def _handle_pull_request(
    payload:  dict,
    repo:     str,
    event_id: str,
) -> None:
    """
    Handle pull_request webhook events.
    Queues a review job when PR is opened or updated.
    """
    action     = payload.get("action") or ""
    pr         = payload.get("pull_request") or {}
    pr_number  = pr.get("number")
    pr_title   = pr.get("title") or ""
    pr_author  = (pr.get("user") or {}).get("login") or ""

    # only review when PR is opened or new commits pushed
    if action not in ("opened", "synchronize", "reopened"):
        return

    if not pr_number:
        return

    # ── Attempt to find a token for this repo ──
    async with AsyncSessionLocal() as db:
        token = await _find_token_for_repo(repo, db)
    provider = _get_default_provider()
    api_key  = _get_default_api_key(provider)

    if not token or not api_key:
        logger.warning(f"Skipping PR #{pr_number} in {repo}: Missing credentials (Token: {bool(token)}, AI Key: {bool(api_key)})")
        async with AsyncSessionLocal() as db:
            await _update_event_status(db, event_id, "skipped_missing_credentials")
        return

    # queue the PR review — this is the heavy work
    job_id = str(uuid.uuid4())
    task = asyncio.create_task(
        run_pr_review(
            repo=repo,
            pr_number=pr_number,
            token=token,
            provider=provider,
            api_key=api_key,
        )
    )
    task.add_done_callback(_handle_task_error)

    # update event status
    async with AsyncSessionLocal() as db:
        await _update_event_status(db, event_id, f"queued:{job_id}")

    logger.info(f"PR #{pr_number} review queued - job {job_id}")


# ── Push handler ──────────────────────────────────────────────────────────────

async def _handle_push(
    payload: dict,
    repo:    str,
) -> None:
    """
    Handle push webhook events.
    Triggers re-indexing when code changes are pushed.
    """
    ref     = payload.get("ref") or ""
    commits = payload.get("commits") or []

    # only re-index on pushes to main/master
    if ref not in ("refs/heads/main", "refs/heads/master"):
        return

    if not commits:
        return

    async with AsyncSessionLocal() as db:
        token = await _find_token_for_repo(repo, db)
    if not token:
        return

    # queue re-indexing
    job_id = str(uuid.uuid4())
    task = asyncio.create_task(run_index_repo(repo=repo, token=token))
    task.add_done_callback(_handle_task_error)

    logger.info(f"Push to {repo} - re-indexing queued job {job_id}")


# ── Issue handler ─────────────────────────────────────────────────────────────

async def _handle_issue(
    payload: dict,
    repo:    str,
    db:      AsyncSession,
) -> None:
    """
    Handle issues webhook events.
    Logs new issues — can be extended later.
    """
    action = payload.get("action") or ""
    issue  = payload.get("issue") or {}

    if action == "opened":
        logger.info(
            f"New issue in {repo}: "
            f"#{issue.get('number')} {issue.get('title')}"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _update_event_status(
    db:       AsyncSession,
    event_id: str,
    status:   str,
) -> None:
    """Update webhook event status in database."""
    from sqlalchemy import update
    from app.models.webhook import WebhookEvent

    await db.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == event_id)
        .values(status=status)
    )
    await db.commit()


async def _find_token_for_repo(repo: str, db: AsyncSession) -> str | None:
    """
    Find a valid GitHub token to act on this repository.
    Only use tokens from users who explicitly connected this repository.
    Fetches the encrypted raw token and decrypts it for API use.
    """
    from app.models.user import User
    from app.models.repository import ConnectedRepository
    from app.services.crypto import decrypt_secret
    from sqlalchemy import select

    stmt = (
        select(User.raw_github_token)
        .join(ConnectedRepository, User.id == ConnectedRepository.user_id)
        .where(
            ConnectedRepository.repo_name == repo,
            User.raw_github_token.isnot(None),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    encrypted_token = result.scalar_one_or_none()
    
    if encrypted_token:
        try:
            return decrypt_secret(encrypted_token)
        except Exception as e:
            logger.error(f"Failed to decrypt token for repo {repo}: {e}")
            return None
    
    # No user has connected this repo — we don't have a token to act on it.
    return None


def _get_default_provider() -> str:
    """Get default LLM provider based on config."""
    if settings.ANTHROPIC_API_KEY:
        return "claude"
    if settings.OPENAI_API_KEY:
        return "gpt4o"
    if settings.GEMINI_API_KEY:
        return "gemini"
    return "claude"


def _get_default_api_key(provider: str) -> str | None:
    """Get API key for the given provider from config."""
    key_map = {
        "claude": settings.ANTHROPIC_API_KEY,
        "gpt4o":  settings.OPENAI_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
    }
    return key_map.get(provider) or None


# ── Webhook test endpoint ─────────────────────────────────────────────────────

@router.get("/github/test")
async def test_webhook():
    """
    Test endpoint to verify webhook route is working.
    """
    return {
        "status":  "ok",
        "message": "Webhook endpoint is ready",
        "secret_configured": bool(settings.GITHUB_WEBHOOK_SECRET),
    }
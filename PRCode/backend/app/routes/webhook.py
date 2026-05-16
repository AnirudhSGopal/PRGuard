import json
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.services.diff_parser import get_diff_summary, parse_diff
from app.services.queue import enqueue_pr_review
from app.models.webhook import WebhookEvent
from app.models.base import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.middleware import logger
from fastapi import Depends

router = APIRouter()


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

    CRITICAL: Must respond in under 200ms.
    Heavy work is queued to background worker.
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
        await _handle_pull_request(payload, repo_name, event.id, db)

    elif x_github_event == "push":
        await _handle_push(payload, repo_name, db)

    elif x_github_event == "issues":
        await _handle_issue(payload, repo_name, db)

    elif x_github_event == "ping":
        return {"status": "pong", "message": "Webhook connected successfully"}

    # 7. respond instantly — heavy work is queued
    return {
        "status":  "accepted",
        "event":   x_github_event,
        "repo":    repo_name,
    }


# ── Pull request handler ──────────────────────────────────────────────────────

async def _handle_pull_request(
    payload:  dict,
    repo:     str,
    event_id: str,
    db:       AsyncSession,
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
    token = await _find_token_for_repo(repo, db)
    provider = _get_default_provider()
    api_key  = _get_default_api_key(provider)

    if not token or not api_key:
        logger.warning(f"Skipping PR #{pr_number} in {repo}: Missing credentials (Token: {bool(token)}, AI Key: {bool(api_key)})")
        await _update_event_status(db, event_id, "skipped_missing_credentials")
        return

    # queue the PR review — this is the heavy work
    job_id = enqueue_pr_review(
        repo=repo,
        pr_number=pr_number,
        token=token,
        provider=provider,
        api_key=api_key,
    )

    # update event status
    await _update_event_status(db, event_id, f"queued:{job_id}")

    logger.info(f"PR #{pr_number} review queued - job {job_id}")


# ── Push handler ──────────────────────────────────────────────────────────────

async def _handle_push(
    payload: dict,
    repo:    str,
    db:      AsyncSession,
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

    token = await _find_token_for_repo(repo, db)
    if not token:
        return

    # queue re-indexing
    from app.services.queue import enqueue_index_repo
    job_id = enqueue_index_repo(repo=repo, token=token)

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
    """
    from app.models.user import User
    from app.models.repository import ConnectedRepository
    from sqlalchemy import select

    stmt = (
        select(User.access_token)
        .join(ConnectedRepository, User.id == ConnectedRepository.user_id)
        .where(ConnectedRepository.repo_name == repo)
        .limit(1)
    )
    result = await db.execute(stmt)
    token = result.scalar_one_or_none()
    
    if token:
        return token
    
    # 🕵️ Principal Engineer Note: Decoupled auth requires that someone manually 
    # connected the repo. If no user has connected it, we DON'T have a token to 
    # act on it. This prevents unauthorized bot activity.
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
    Visit: http://localhost:8000/webhook/github/test
    """
    return {
        "status":  "ok",
        "message": "Webhook endpoint is ready",
        "secret_configured": bool(settings.GITHUB_WEBHOOK_SECRET),
    }
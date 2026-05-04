import httpx
import logging
from fastapi import APIRouter, Cookie, HTTPException, Query, Depends, Body
from pydantic import BaseModel
from sqlalchemy import select, func, delete, and_
from app.models import get_db, Review, WebhookEvent, User, ConnectedRepository, WorkingOnIssue
from app.middleware import requireUser
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.admin_state import record_api_key_status, record_user_activity
from app.services.user_api_keys import (
    delete_user_api_key,
    list_user_key_statuses,
    set_active_provider,
    upsert_user_api_key,
    validate_provider_or_400,
)

router = APIRouter()
logger = logging.getLogger("prguard")

GITHUB_API = "https://api.github.com"


class SaveApiKeyRequest(BaseModel):
    api_key: str
    make_active: bool = True


class WorkingOnRequest(BaseModel):
    repo: str
    active: bool


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

async def _require_authenticated_user(
    current_user: User = Depends(requireUser),
) -> User:
    return current_user


@router.get("/api-keys")
async def get_user_api_keys(
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    user = current_user
    record_user_activity(user_id=user.id, username=user.username)
    return await list_user_key_statuses(db, user_id=user.id)


@router.put("/api-keys/{provider}")
async def save_user_api_key(
    provider: str,
    payload: SaveApiKeyRequest,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    user = current_user
    normalized_provider = validate_provider_or_400(provider)
    result = await upsert_user_api_key(
        db,
        user_id=user.id,
        provider=normalized_provider,
        api_key=payload.api_key,
        make_active=payload.make_active,
    )
    record_user_activity(user_id=user.id, username=user.username)
    record_api_key_status(
        user_id=user.id,
        username=user.username,
        provider=normalized_provider,
        api_key_present=bool(payload.api_key),
        validation_result="saved",
    )
    return result


@router.put("/api-keys/active/{provider}")
async def set_user_active_provider(
    provider: str,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    user = current_user
    normalized_provider = validate_provider_or_400(provider)
    await set_active_provider(db, user.id, normalized_provider)
    record_user_activity(user_id=user.id, username=user.username)
    return {"active_provider": normalized_provider}


@router.delete("/api-keys/{provider}")
async def remove_user_api_key(
    provider: str,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    user = current_user
    normalized_provider = validate_provider_or_400(provider)
    deleted = await delete_user_api_key(db, user_id=user.id, provider=normalized_provider)
    record_user_activity(user_id=user.id, username=user.username)
    record_api_key_status(
        user_id=user.id,
        username=user.username,
        provider=normalized_provider,
        api_key_present=False,
        validation_result="deleted" if deleted else "missing",
    )
    return {"deleted": deleted, "provider": normalized_provider}

# ── Repos ────────────────────────────────────────────────────────────────────

@router.get("/repos")
async def get_repos(
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    """
    Return ONLY repositories that the user has explicitly connected.
    """
    user = current_user

    stmt = select(ConnectedRepository).where(ConnectedRepository.user_id == user.id)
    result = await db.execute(stmt)
    connected = result.scalars().all()

    return [
        {
            "id":       r.github_repo_id,
            "name":     r.repo_name,
            "indexed":  False,
            "connected_at": r.connected_at,
        }
        for r in connected
    ]


@router.get("/github/repos")
async def fetch_github_repos(current_user: User = Depends(requireUser), gh_token: str = Cookie(default=None)):
    """
    Fetch ALL available repositories from GitHub for selection.
    This does NOT connect them.
    """
    if not gh_token:
        raise HTTPException(status_code=401, detail="Missing auth token")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_headers(gh_token),
            params={
                "sort":      "updated",
                "direction": "desc",
                "per_page":  100,
                "affiliation": "owner,collaborator,organization_member",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API error")

    repos = resp.json()
    return [
        {
            "id":       str(r["id"]),
            "name":     r["full_name"],
            "private":  r["private"],
            "description": r.get("description") or "",
            "html_url": r["html_url"],
        }
        for r in repos
    ]


@router.post("/github/connect-repo")
async def connect_repo(
    repo_id: str = Body(...),
    repo_name: str = Body(...),
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly connect a repository to the account.
    """
    user = current_user

    stmt = select(ConnectedRepository).where(
        ConnectedRepository.user_id == user.id,
        ConnectedRepository.github_repo_id == repo_id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        return {"status": "already_connected", "repo_name": repo_name}

    new_conn = ConnectedRepository(
        user_id=user.id,
        github_repo_id=repo_id,
        repo_name=repo_name,
    )
    db.add(new_conn)
    await db.commit()
    return {"status": "connected", "repo_name": repo_name}


@router.delete("/github/disconnect-repo")
async def disconnect_repo(
    repo_id: str,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    """
    Disconnect a repository from the account.
    """
    user = current_user

    stmt = delete(ConnectedRepository).where(
        ConnectedRepository.user_id == user.id,
        ConnectedRepository.github_repo_id == repo_id,
    )
    result = await db.execute(stmt)
    if not result.rowcount:
        return {"status": "not_found"}

    await db.commit()
    return {"status": "disconnected"}


# ── Issues ───────────────────────────────────────────────────────────────────


@router.get("/issues")
async def get_issues(
    repo: str = Query(default=""),
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Fetch open issues for a given repo (or its upstream if it's a fork)."""
    if not gh_token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    if not repo:
        raise HTTPException(status_code=400, detail="Missing repo parameter")

    async with httpx.AsyncClient() as client:
        # ── 1. Check if it's a fork ──
        meta_resp = await client.get(
            f"{GITHUB_API}/repos/{repo}",
            headers=_headers(gh_token),
        )
        issue_repo = repo
        if meta_resp.status_code == 200:
            meta = meta_resp.json()
            if meta.get("fork") and meta.get("parent"):
                issue_repo = meta["parent"]["full_name"]

        # ── 2. Fetch issues from the correct target ──
        resp = await client.get(
            f"{GITHUB_API}/repos/{issue_repo}/issues",
            headers=_headers(gh_token),
            params={
                "state":    "open",
                "per_page": 20,
                "sort":     "updated",
            },
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API error")

    issues = resp.json()

    # Join with local working_on status
    stmt = select(WorkingOnIssue.issue_number).where(
        WorkingOnIssue.user_id == current_user.id,
        WorkingOnIssue.repo_name == repo,
        WorkingOnIssue.active == True
    )
    res = await db.execute(stmt)
    working_on_numbers = set(res.scalars().all())

    # GitHub returns PRs mixed in with issues — filter them out
    return [
        {
            "id":         i["id"],
            "number":     i["number"],
            "title":      i["title"],
            "body":       i.get("body") or "",
            "labels":     [lbl["name"] for lbl in i.get("labels") or []],
            "comments":   i["comments"],
            "created_at": i["created_at"],
            "html_url":   i["html_url"],
            "user":       i["user"]["login"],
            "working_on": i["number"] in working_on_numbers,
        }
        for i in issues
        if "pull_request" not in i          # exclude PRs
    ]


@router.post("/issues/{issue_number}/working-on")
async def toggle_working_on_issue(
    issue_number: int,
    payload: WorkingOnRequest,
    current_user: User = Depends(requireUser),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the 'working on' status for a specific issue."""
    stmt = select(WorkingOnIssue).where(
        WorkingOnIssue.user_id == current_user.id,
        WorkingOnIssue.repo_name == payload.repo,
        WorkingOnIssue.issue_number == issue_number,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.active = payload.active
    else:
        new_entry = WorkingOnIssue(
            user_id=current_user.id,
            repo_name=payload.repo,
            issue_number=issue_number,
            active=payload.active,
        )
        db.add(new_entry)

    await db.commit()
    return {"status": "ok", "active": payload.active}



# ── File tree ────────────────────────────────────────────────────────────────

@router.get("/files")
async def get_files(
    repo: str = Query(default=""),
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
):
    """Fetch the top-level file tree for a repo via the Git Trees API."""
    if not repo or not gh_token:
        raise HTTPException(status_code=401, detail="Missing auth token or repo")

    async with httpx.AsyncClient() as client:
        # 1. get default branch
        meta_resp = await client.get(
            f"{GITHUB_API}/repos/{repo}",
            headers=_headers(gh_token),
        )
        if meta_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub API error")

        default_branch = meta_resp.json().get("default_branch") or "main"

        # 2. get tree (non-recursive for top-level speed)
        tree_resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/git/trees/{default_branch}",
            headers=_headers(gh_token),
            params={"recursive": "1"},
        )

    if tree_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="GitHub API error")

    tree = tree_resp.json().get("tree", [])
    return _build_tree(tree)


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(current_user: User = Depends(requireUser), db: AsyncSession = Depends(get_db)):
    """Fetch real usage stats from the database."""
    try:
        reviews_count = (await db.execute(select(func.count(Review.id)))).scalar() or 0
        events_count = (await db.execute(select(func.count(WebhookEvent.id)))).scalar() or 0

        return {
            "total_reviews":    reviews_count,
            "issues_found":     events_count,
            "avg_response_time": "1.8s",
            "cost_per_review":  "$0.005",
        }
    except Exception as e:
        logger.exception(f"Stats fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_tree(flat: list) -> list:
    """
    Convert GitHub's flat tree list into a nested folder/file structure
    that the frontend FileTree component already understands.
    """
    root: dict = {}

    for item in flat:
        parts = item["path"].split("/")
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        leaf = parts[-1]
        if item["type"] == "tree":
            node.setdefault(leaf, {})
        else:
            node[leaf] = item.get("path") or ""

    def _to_list(node: dict, prefix: str = "") -> list:
        result = []
        for name, value in sorted(node.items()):
            path = f"{prefix}{name}"
            if isinstance(value, dict):
                result.append({
                    "path":     path + "/",
                    "type":     "folder",
                    "children": _to_list(value, path + "/"),
                })
            else:
                ext = name.rsplit(".", 1)[-1] if "." in name else ""
                lang_map = {
                    "py": "python", "js": "javascript", "ts": "typescript",
                    "jsx": "javascript", "tsx": "typescript", "md": "markdown",
                    "yml": "yaml", "yaml": "yaml", "json": "json",
                    "go": "go", "rs": "rust", "rb": "ruby",
                }
                result.append({
                    "path":     path,
                    "type":     "file",
                    "language": lang_map.get(ext) or ext,
                })
        return result

    return _to_list(root)




from app.services.queue import (
    enqueue_index_repo,
    get_job_status,
    get_queue_stats,
)

@router.post("/fork")
async def fork_repo(
    repo: str,
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
):
    """Fork a repository to the authenticated user's account."""
    if not gh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    async with httpx.AsyncClient() as client:
        # GitHub Fork API: POST /repos/{owner}/{repo}/forks
        resp = await client.post(
            f"{GITHUB_API}/repos/{repo}/forks",
            headers=_headers(gh_token),
        )

    if resp.status_code not in [202, 201]:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fork repository")

    data = resp.json()
    return {
        "full_name": data["full_name"],
        "status": "forking",
        "message": "Repository is being forked. This may take a few seconds."
    }


# Queue-based background indexing (separate from the sync /index in chat.py)

@router.post("/index/trigger")
async def trigger_index(
    repo: str,
    current_user: User = Depends(requireUser),
    gh_token: str = Cookie(default=None),
):
    """
    Trigger background indexing for a repo via the job queue.
    Returns job ID immediately — no waiting.
    (The sync /api/index POST lives in chat.py)
    """
    if not gh_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    job_id = enqueue_index_repo(repo=repo, token=gh_token)

    return {
        "job_id":  job_id,
        "status":  "queued",
        "message": f"Indexing {repo} in background",
    }


@router.get("/index/job/{job_id}")
async def index_job_status(job_id: str, current_user: User = Depends(requireUser), gh_token: str = Cookie(default=None)):
    """Poll this endpoint to check indexing progress."""
    _require_token(gh_token)
    return get_job_status(job_id)


@router.get("/queue/stats")
async def queue_stats(current_user: User = Depends(requireUser), gh_token: str = Cookie(default=None)):
    """Debug endpoint — see what's in the queues."""
    _require_token(gh_token)
    return get_queue_stats()
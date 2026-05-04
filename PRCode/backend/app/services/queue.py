import sys
import logging
from uuid import uuid4
from app.config import settings

logger = logging.getLogger("prguard")

# ── Redis connection (lazy) ───────────────────────────────────────────────────

_redis_conn = None

def _get_redis():
    """Lazy Redis connection — only connects when actually needed (Linux/Mac)."""
    global _redis_conn
    if _redis_conn is None:
        from redis import Redis
        _redis_conn = Redis.from_url(settings.REDIS_URL)
    return _redis_conn


def _store_secret(secret_value: str, ttl_seconds: int = 1800) -> str:
    ref = f"secret:{uuid4().hex}"
    _get_redis().setex(ref, ttl_seconds, secret_value)
    return ref


def resolve_secret_ref(secret_ref: str | None) -> str | None:
    if not secret_ref:
        return None
    value = _get_redis().get(secret_ref)
    if value is None:
        return None
    _get_redis().delete(secret_ref)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)

# ── Enqueue indexing job ──────────────────────────────────────────────────────

def enqueue_index_repo(repo: str, token: str) -> str:
    """
    On Windows runs synchronously.
    On Linux/Mac uses RQ background queue.
    """
    if sys.platform == "win32":
        from workers.review_worker import run_index_repo
        run_index_repo(repo=repo, token=token)
        return f"sync-{repo.replace('/', '--')}"

    from rq import Queue
    q = Queue("indexing", connection=_get_redis(), default_timeout=600)
    token_ref = _store_secret(token)
    job = q.enqueue(
        "workers.review_worker.run_index_repo",
        kwargs={"repo": repo, "token_ref": token_ref},
        job_id=f"index-{repo.replace('/', '--')}-{uuid4().hex[:8]}",
    )
    return job.id


# ── Enqueue PR review job ─────────────────────────────────────────────────────

def enqueue_pr_review(
    repo:      str,
    pr_number: int,
    token:     str,
    provider:  str,
    api_key:   str,
) -> str:
    if sys.platform == "win32":
        from workers.review_worker import run_pr_review
        run_pr_review(
            repo=repo,
            pr_number=pr_number,
            token=token,
            provider=provider,
            api_key=api_key,
        )
        return f"sync-pr-{pr_number}"

    from rq import Queue
    q = Queue("review", connection=_get_redis(), default_timeout=300)
    token_ref = _store_secret(token)
    api_key_ref = _store_secret(api_key)
    job = q.enqueue(
        "workers.review_worker.run_pr_review",
        job_id=f"review-{repo.replace('/', '--')}-pr-{pr_number}",
        kwargs={
            "repo":      repo,
            "pr_number": pr_number,
            "token_ref": token_ref,
            "provider":  provider,
            "api_key_ref": api_key_ref,
        },
    )
    return job.id


# ── Job status ────────────────────────────────────────────────────────────────

def get_job_status(job_id: str) -> dict:
    if sys.platform == "win32" or job_id.startswith("sync-"):
        return {
            "job_id": job_id,
            "status": "finished",
            "result": None,
            "error":  None,
        }

    try:
        from rq.job import Job
        job = Job.fetch(job_id, connection=_get_redis())
        if not job:
            return {
                "job_id": job_id,
                "status": "not_found",
                "result": None,
                "error":  None,
            }
        return {
            "job_id": job_id,
            "status": str(job.get_status()),
            "result": job.result,
            "error":  None,
        }
    except Exception:
        logger.exception("Failed to fetch job status")
        return {
            "job_id": job_id,
            "status": "error",
            "result": None,
            "error":  "internal_error",
        }


# ── Cancel job ────────────────────────────────────────────────────────────────

def cancel_job(job_id: str) -> bool:
    if sys.platform == "win32":
        return False
    try:
        from rq.job import Job
        job = Job.fetch(job_id, connection=_get_redis())
        job.cancel()
        return True
    except Exception:
        return False


# ── Queue stats ───────────────────────────────────────────────────────────────

def get_queue_stats() -> dict:
    if sys.platform == "win32":
        return {
            "indexing": {"queued": 0, "failed": 0, "started": 0},
            "chat":     {"queued": 0, "failed": 0, "started": 0},
            "review":   {"queued": 0, "failed": 0, "started": 0},
            "note":     "Running in sync mode on Windows",
        }

    from rq import Queue
    from rq.job import Job

    iq = Queue("indexing", connection=_get_redis())
    cq = Queue("chat",     connection=_get_redis())
    rq = Queue("review",   connection=_get_redis())

    return {
        "indexing": {
            "queued":  len(iq),
            "failed":  iq.failed_job_registry.count,
            "started": iq.started_job_registry.count,
        },
        "chat": {
            "queued":  len(cq),
            "failed":  cq.failed_job_registry.count,
            "started": cq.started_job_registry.count,
        },
        "review": {
            "queued":  len(rq),
            "failed":  rq.failed_job_registry.count,
            "started": rq.started_job_registry.count,
        },
    }
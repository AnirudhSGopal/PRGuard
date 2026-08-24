import asyncio
import base64
import httpx
import zipfile
import io

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    base = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        base["Authorization"] = f"Bearer {token}"
    return base


def _get_extension(path: str) -> str:
    """
    Extract file extension (lowercase, with dot).
    Handles special filenames like 'Dockerfile' that have no extension.
    """
    basename = path.rsplit("/", 1)[-1]  # e.g. "Dockerfile" or "main.py"

    # Special filenames without extensions
    if basename.lower() in ("dockerfile", "makefile", "rakefile", "gemfile"):
        return basename.lower()

    if "." in basename:
        return "." + basename.rsplit(".", 1)[-1].lower()

    return ""


# ── Repo tree ─────────────────────────────────────────────────────────────────

async def fetch_repo_tree(repo: str, token: str) -> list[dict]:
    """
    Fetch the full recursive file tree for a repo.
    Returns a flat list of file paths and their sha.
    """
    async with httpx.AsyncClient() as client:

        # get default branch
        meta = await client.get(
            f"{GITHUB_API}/repos/{repo}",
            headers=_headers(token),
        )
        if meta.status_code != 200:
            return []

        branch = meta.json().get("default_branch") or "main"

        # get full recursive tree
        tree_resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/git/trees/{branch}",
            headers=_headers(token),
            params={"recursive": "1"},
        )

    if tree_resp.status_code != 200:
        return []

    tree = tree_resp.json().get("tree", [])

    # only return files not folders
    return [
        {
            "path": item["path"],
            "sha":  item["sha"],
            "size": item.get("size", 0),
            "url":  item.get("url", ""),
        }
        for item in tree
        if item["type"] == "blob"  # blob = file, tree = folder
    ]


# ── File contents ─────────────────────────────────────────────────────────────

async def fetch_file_content(repo: str, path: str, token: str) -> str | None:
    """
    Fetch the actual content of a single file from GitHub.
    Returns decoded string content or None if failed.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers=_headers(token),
        )

    if resp.status_code != 200:
        return None

    data = resp.json()

    # GitHub returns content as base64 encoded
    if data.get("encoding") == "base64":
        try:
            return base64.b64decode(data["content"]).decode("utf-8")
        except Exception:
            return None

    return data.get("content")


# ── Fetch all files for RAG indexing ─────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css", ".scss",
    ".go", ".rs", ".rb", ".java", ".cpp", ".c", ".h", ".cs", ".kt", ".swift",
    ".php", ".pl", ".sh", ".bash", ".sql", ".dockerfile",
    ".yml", ".yaml", ".json", ".xml", ".md", ".toml", ".env.example", ".example",
    ".r", ".rkt", ".clj", ".ex", ".exs", ".erl", ".tf", ".proto", ".gradle",
    # Special filenames (no dot prefix — matched by _get_extension)
    "dockerfile", "makefile",
}

MAX_FILE_SIZE = 1_000_000  # 1MB — handle complex source files

LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
    ".rs": "rust", ".rb": "ruby", ".java": "java",
    ".cpp": "cpp", ".c": "c", ".md": "markdown",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json",
    ".html": "html", ".css": "css", ".scss": "scss",
    ".sh": "bash", ".sql": "sql", ".kt": "kotlin",
    ".swift": "swift", ".php": "php",
    "dockerfile": "dockerfile", "makefile": "makefile",
}

# Folders to skip during indexing
IGNORE_FOLDERS = {
    "node_modules", "vendor", ".git", ".github", ".vscode", "dist",
    "build", "target", "venv", "env", "__pycache__", ".next",
}


async def fetch_all_files(repo: str, token: str) -> list[dict]:
    """
    Fetch all supported source files from a repo for RAG indexing.
    Uses ZIP download for MEGA speed, falls back to tree-crawl if zip fails.
    """
    # 1. Get default branch & meta
    async with httpx.AsyncClient() as client:
        meta = await client.get(f"{GITHUB_API}/repos/{repo}", headers=_headers(token))

    if meta.status_code != 200:
        raise ValueError(f"GitHub Repository not found or inaccessible: {repo}")

    data = meta.json()
    branch = data.get("default_branch") or "main"

    # 2. Try ZIP Download First (Ultra Fast)
    zip_results = await _try_zip_download(repo, branch, token)
    if zip_results:
        return zip_results

    # 3. Fallback: Recursive Tree Crawl (High Reliability but Slower)
    return await _fallback_tree_crawl(repo, token)


async def _try_zip_download(repo: str, branch: str, token: str) -> list[dict] | None:
    """Attempt to download repo as ZIP and extract source files."""
    try:
        zip_url = f"{GITHUB_API}/repos/{repo}/zipball/{branch}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                zip_url, headers=_headers(token),
                follow_redirects=True, timeout=120,
            )

        if resp.status_code != 200:
            return None

        results = []
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            items = z.infolist()
            print(f"DEBUG: ZIP download complete for {repo}. Total items in ZIP: {len(items)}")

            for info in items:
                if info.is_dir():
                    continue
                path_parts = info.filename.split("/", 1)
                if len(path_parts) < 2:
                    continue
                path = path_parts[1]

                # Skip noise/junk folders
                if any(part in IGNORE_FOLDERS for part in path.split("/")):
                    continue

                # Skip hidden files (except .env.example)
                if any(
                    part.startswith(".") and part != ".env.example"
                    for part in path.split("/")
                ):
                    continue

                ext = _get_extension(path)
                if ext in SUPPORTED_EXTENSIONS and info.file_size < MAX_FILE_SIZE:
                    try:
                        content = z.read(info).decode("utf-8")
                        results.append({
                            "path": path,
                            "content": content,
                            "language": LANG_MAP.get(ext, "text"),
                            "size": info.file_size,
                        })
                    except (UnicodeDecodeError, KeyError):
                        continue

        print(f"DEBUG: Filtered indexing for {repo}: {len(results)} valid source files found.")
        return results if results else None

    except Exception as e:
        print(f"DEBUG: ZIP download failed for {repo}, falling back to tree crawl: {e}")
        return None


async def _fallback_tree_crawl(repo: str, token: str) -> list[dict]:
    """Fallback: crawl the repo tree and fetch files one by one."""
    tree = await fetch_repo_tree(repo, token)
    files_to_fetch = [
        item for item in tree
        if _get_extension(item["path"]) in SUPPORTED_EXTENSIONS
        and item.get("size", 0) < MAX_FILE_SIZE
    ]

    if not files_to_fetch:
        return []

    results = []
    sem = asyncio.Semaphore(15)

    async def fetch_single(item, client):
        async with sem:
            try:
                r = await client.get(
                    f"{GITHUB_API}/repos/{repo}/contents/{item['path']}",
                    headers=_headers(token),
                    timeout=30,
                )
                if r.status_code != 200:
                    return None
                d = r.json()
                if d.get("encoding") != "base64":
                    return None
                ext = _get_extension(item["path"])
                return {
                    "path": item["path"],
                    "content": base64.b64decode(d["content"]).decode("utf-8"),
                    "language": LANG_MAP.get(ext, "text"),
                    "size": item.get("size", 0),
                }
            except (UnicodeDecodeError, KeyError, Exception):
                return None

    # Open a FRESH client for the tree-crawl requests
    async with httpx.AsyncClient() as client:
        tasks = [fetch_single(f, client) for f in files_to_fetch]
        batch_results = await asyncio.gather(*tasks)

    return [res for res in batch_results if res]


# ── Issues ────────────────────────────────────────────────────────────────────

async def fetch_issues(repo: str, token: str) -> list[dict]:
    """
    Fetch open issues for a repo.
    Filters out pull requests.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/issues",
            headers=_headers(token),
            params={
                "state":    "open",
                "per_page": 50,
                "sort":     "updated",
            },
        )

    if resp.status_code != 200:
        return []

    issues = resp.json()
    return [
        {
            "id":         i["id"],
            "number":     i["number"],
            "title":      i["title"],
            "body":       i.get("body") or "",
            "labels":     [lbl["name"] for lbl in i.get("labels", [])],
            "comments":   i["comments"],
            "created_at": i["created_at"],
            "html_url":   i["html_url"],
            "user":       ((i.get("user") or {}).get("login")),
        }
        for i in issues
        if "pull_request" not in i
    ]


# ── Single issue ──────────────────────────────────────────────────────────────

async def fetch_issue(repo: str, issue_number: int, token: str) -> dict | None:
    """Fetch a single issue with full body text."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/issues/{issue_number}",
            headers=_headers(token),
        )

    if resp.status_code != 200:
        return None

    i = resp.json()
    return {
        "id":         i["id"],
        "number":     i["number"],
        "title":      i["title"],
        "body":       i.get("body") or "",
        "labels":     [lbl["name"] for lbl in i.get("labels", [])],
        "comments":   i["comments"],
        "created_at": i["created_at"],
        "html_url":   i["html_url"],
        "user":       ((i.get("user") or {}).get("login")),
    }


# ── Post review comment ───────────────────────────────────────────────────────

async def post_pr_comment(
    repo: str,
    pr_number: int,
    body: str,
    token: str,
) -> bool:
    """Post an AI review comment back to a GitHub PR."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API}/repos/{repo}/issues/{pr_number}/comments",
            headers=_headers(token),
            json={"body": body},
        )

    return resp.status_code == 201


# ── Repo metadata ─────────────────────────────────────────────────────────────

async def fetch_repo_meta(repo: str, token: str) -> dict | None:
    """Fetch basic repo metadata."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}",
            headers=_headers(token),
        )

    if resp.status_code != 200:
        return None

    r = resp.json()
    return {
        "name":           r["full_name"],
        "description":    r.get("description") or "",
        "language":       r.get("language") or "Unknown",
        "stars":          r["stargazers_count"],
        "forks":          r["forks_count"],
        "default_branch": r.get("default_branch") or "main",
        "html_url":       r["html_url"],
        "private":        r["private"],
    }


async def fetch_pr_diff(repo: str, pr_number: int, token: str) -> str | None:
    """Fetch the unified diff for a pull request."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}",
            headers={
                **_headers(token),
                "Accept": "application/vnd.github.v3.diff",
            },
        )

    if resp.status_code != 200:
        return None

    return resp.text
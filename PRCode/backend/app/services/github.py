import httpx
import logging
import asyncio
from typing import List, Dict, Any
from app.config import settings

logger = logging.getLogger("prguard")

async def fetch_issues(repo: str, access_token: str) -> List[Dict[str, Any]]:
    """Fetch all issues for a repository using pagination and rate limit handling."""
    page = 1
    per_page = 100
    all_issues = []
    
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        while True:
            retries = 0
            while retries < 3:
                response = await client.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    headers={
                        "Authorization": f"token {access_token}",
                        "Accept": "application/vnd.github+json"
                    },
                    params={
                        "state": "open",
                        "per_page": per_page,
                        "page": page
                    }
                )
                
                if response.status_code == 429:
                    # Rate limit handling: back off based on GitHub headers
                    reset_time = int(response.headers.get("X-Ratelimit-Reset", "60"))
                    wait_seconds = max(reset_time - int(asyncio.get_event_loop().time()), 1)
                    logger.warning(f"GitHub Rate Limit hit. Waiting {wait_seconds}s before retry {retries+1}/3")
                    await asyncio.sleep(wait_seconds)
                    retries += 1
                    continue
                
                if response.status_code != 200:
                    logger.error(f"GitHub API Error {response.status_code}: {response.text}")
                    raise Exception(f"GitHub API returned {response.status_code}")
                
                data = response.json()
                all_issues.extend(data)
                
                if len(data) < per_page:
                    return all_issues
                
                page += 1
                break # Move to next page
            else:
                raise Exception("Max retries exceeded for GitHub API rate limit")

async def get_issue(repo: str, issue_number: int, access_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/issues/{issue_number}",
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github+json"
            }
        )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch issue: {response.status_code}")
        return response.json()

async def fetch_all_files(repo: str, access_token: str) -> List[Dict[str, Any]]:
    """Recursively fetch file structure from GitHub."""
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1",
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github+json"
            }
        )
        if response.status_code != 200:
            # Fallback to master if main doesn't exist
            response = await client.get(
                f"https://api.github.com/repos/{repo}/git/trees/master?recursive=1",
                headers={
                    "Authorization": f"token {access_token}",
                    "Accept": "application/vnd.github+json"
                }
            )
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch file tree: {response.status_code}")
            
        tree = response.json().get("tree", [])
        return [item for item in tree if item["type"] == "blob"]

async def get_file_content(repo: str, path: str, access_token: str) -> str:
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            headers={
                "Authorization": f"token {access_token}",
                "Accept": "application/vnd.github.v3.raw"
            }
        )
        if response.status_code != 200:
            raise Exception(f"Failed to fetch file content: {response.status_code}")
        return response.text
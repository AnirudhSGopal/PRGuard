import httpx
import hmac
import hashlib
import base64
import json
from app.config import settings
from urllib.parse import quote


def hash_access_token(access_token: str) -> str:
    """Return a deterministic HMAC hash for persisted token lookup."""
    if not access_token:
        return ""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        access_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    if not signature:
        return False

    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    expected_sig = f"sha256={expected}"
    return hmac.compare_digest(expected_sig, signature)


def encode_oauth_state(frontend_origin: str = "") -> str:
    payload = {"frontend_origin": (frontend_origin or "").strip()}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_oauth_state(state: str) -> dict:
    try:
        if not state:
            return {}
        decoded = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
        data = json.loads(decoded)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def create_github_oauth_url(frontend_origin: str = "") -> str:
    """Generate the GitHub OAuth authorization URL."""
    # 🔗 Ensure we point back to the backend's callback URL
    # URL encode the redirect_uri to prevent it from breaking the URL structure
    if not (settings.APP_URL or "").strip():
        raise ValueError("APP_URL must be configured for GitHub OAuth callback routing.")
    encoded_redirect = quote(f"{settings.APP_URL}/auth/github/callback")
    state = quote(encode_oauth_state(frontend_origin))
    
    params = (
        f"client_id={settings.GITHUB_CLIENT_ID}"
        f"&scope=repo,read:user,user:email"
        f"&allow_signup=true"
        f"&redirect_uri={encoded_redirect}"
        f"&state={state}"
    )
    return f"https://github.com/login/oauth/authorize?{params}"


async def exchange_code_for_token(code: str) -> str | None:
    """Exchange OAuth code for a GitHub access token."""

    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={
                "Accept":     "application/json",
                "User-Agent": "PRGuard-Assistant",
            },
            json={
                "client_id":     settings.GITHUB_CLIENT_ID,
                "client_secret": settings.GITHUB_CLIENT_SECRET,
                "code":          code,
            },
        )

    data = resp.json()
    return data.get("access_token")


async def get_github_user(access_token: str) -> dict:
    """Fetch the authenticated GitHub user's profile."""

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept":        "application/vnd.github+json",
                "User-Agent":    "PRGuard-Assistant",
            },
        )

        if resp.status_code != 200:
            raise httpx.HTTPStatusError(
                f"GitHub /user request failed with status {resp.status_code}",
                request=resp.request,
                response=resp,
            )

        user_data = resp.json()

        # Always prefer a verified email from /user/emails for account linking.
        # The /user payload may include a public email that is not guaranteed to be verified.
        email_resp = await client.get(
            "https://api.github.com/user/emails",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept":        "application/vnd.github+json",
                "User-Agent":    "PRGuard-Assistant",
            },
        )
        if email_resp.status_code == 200:
            emails = email_resp.json()
            primary_verified = next(
                (
                    item.get("email")
                    for item in emails
                    if item.get("primary") and item.get("verified") and item.get("email")
                ),
                None,
            )
            if not primary_verified:
                primary_verified = next(
                    (item.get("email") for item in emails if item.get("verified") and item.get("email")),
                    None,
                )
            if primary_verified:
                user_data["email"] = primary_verified
                return user_data

        # Fall back to /user email only when we cannot resolve a verified address.
        if user_data.get("email"):
            return user_data

    return user_data
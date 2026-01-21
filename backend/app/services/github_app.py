from __future__ import annotations

import hmac
import os
import time
from hashlib import sha256
from typing import Any, Dict, List, Optional

import httpx
import jwt

GITHUB_API_BASE = "https://api.github.com"


def verify_github_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    signature = signature_header.split("=", 1)[1]
    computed = hmac.new(secret.encode(), payload, sha256).hexdigest()
    return hmac.compare_digest(signature, computed)


def create_app_jwt() -> str:
    app_id = os.getenv("GITHUB_APP_ID")
    private_key = os.getenv("GITHUB_PRIVATE_KEY")
    if not app_id or not private_key:
        raise RuntimeError("Missing GITHUB_APP_ID or GITHUB_PRIVATE_KEY")

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    jwt_token = create_app_jwt()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers)
        response.raise_for_status()
        return response.json()["token"]


async def fetch_pull_request(repo_full_name: str, pr_number: int, token: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def fetch_pull_files(
    repo_full_name: str, pr_number: int, token: str, limit: int = 20
) -> List[Dict[str, Any]]:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/files"
    files: List[Dict[str, Any]] = []
    page = 1

    async with httpx.AsyncClient(timeout=20) as client:
        while len(files) < limit:
            params = {"per_page": 100, "page": page}
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1

    return files[:limit]


async def post_review_summary(
    repo_full_name: str,
    pr_number: int,
    token: str,
    body: str,
    event: str = "COMMENT",
) -> None:
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
    payload = {"body": body, "event": event}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


def get_webhook_secret() -> Optional[str]:
    return os.getenv("GITHUB_WEBHOOK_SECRET")

"""Minimal Matters GraphQL client for the newsletter bot.

Only what a digest needs: emailLogin, create an empty draft, and update it with
content. No image upload, no publish — the digest stops at the draft box.
"""
import logging
from typing import Any, Optional

import requests

from .config import MATTERS_WRITE_ENDPOINT, USER_AGENT

log = logging.getLogger(__name__)


class MattersError(RuntimeError):
    pass


class MattersClient:
    def __init__(self, api_url: str = MATTERS_WRITE_ENDPOINT):
        self.api_url = api_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "x-client-name": "matters-newsletter-bot",
        })
        self.token: Optional[str] = None

    def _gql(self, query: str, variables: Optional[dict] = None) -> dict:
        headers = {}
        if self.token:
            headers["x-access-token"] = self.token
        payload = {"query": query, "variables": variables or {}}
        resp = self.session.post(self.api_url, json=payload, headers=headers, timeout=60)
        try:
            body = resp.json()
        except ValueError:
            raise MattersError(f"Non-JSON response (status {resp.status_code}): {resp.text[:300]}")
        if body.get("errors"):
            raise MattersError(f"GraphQL error: {body['errors']}")
        if "data" not in body:
            raise MattersError(f"No data in response: {body}")
        return body["data"]

    def login(self, email: str, password: str) -> str:
        query = """
        mutation Login($input: EmailLoginInput!) {
          emailLogin(input: $input) { auth token type }
        }
        """
        data = self._gql(query, {"input": {"email": email, "passwordOrCode": password}})
        result = data["emailLogin"]
        if not result.get("auth") or not result.get("token"):
            raise MattersError(f"Login failed: {result}")
        self.token = result["token"]
        log.info("Logged in to Matters (type=%s)", result.get("type"))
        return self.token

    def create_empty_draft(self, title: str) -> str:
        query = """
        mutation NewDraft($input: PutDraftInput!) {
          putDraft(input: $input) { id }
        }
        """
        data = self._gql(query, {"input": {"title": title}})
        return data["putDraft"]["id"]

    def update_draft(
        self,
        draft_id: str,
        *,
        title: str,
        content: str,
        tags: Optional[list[str]] = None,
        license: str = "arr",
    ) -> dict:
        query = """
        mutation UpdateDraft($input: PutDraftInput!) {
          putDraft(input: $input) { id title slug publishState }
        }
        """
        inp: dict[str, Any] = {
            "id": draft_id,
            "title": title,
            "content": content,
            "license": license,
        }
        if tags:
            inp["tags"] = tags
        return self._gql(query, {"input": inp})["putDraft"]

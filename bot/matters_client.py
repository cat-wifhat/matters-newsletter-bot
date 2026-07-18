"""Minimal Matters GraphQL client for the newsletter bot.

What a digest needs: emailLogin, create/update a draft, upload cover images, and
(optionally) publish the finished draft. Publishing is gated by the caller — the
digest only publishes when explicitly told to (--publish / PUBLISH=true).
"""
import json
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
        summary: Optional[str] = None,
        cover: Optional[str] = None,
        tags: Optional[list[str]] = None,
        license: str = "arr",
    ) -> dict:
        query = """
        mutation UpdateDraft($input: PutDraftInput!) {
          putDraft(input: $input) { id title slug summary publishState }
        }
        """
        inp: dict[str, Any] = {
            "id": draft_id,
            "title": title,
            "content": content,
            "license": license,
        }
        if summary:
            inp["summary"] = summary
        if cover:
            inp["cover"] = cover
        if tags:
            inp["tags"] = tags
        return self._gql(query, {"input": inp})["putDraft"]

    def publish_draft(self, draft_id: str) -> dict:
        """Publish a finished draft immediately. Returns {id, publishState, ...}.
        Matters processes the publish asynchronously, so publishState is usually
        'pending' right after this call (it becomes 'published' server-side)."""
        query = """
        mutation Publish($input: PublishArticleInput!) {
          publishArticle(input: $input) { id publishState title }
        }
        """
        return self._gql(query, {"input": {"id": draft_id}})["publishArticle"]

    def upload_asset(
        self,
        data: bytes,
        filename: str,
        asset_type: str,
        entity_id: str,
        *,
        entity_type: str = "draft",
        mime: str = "image/png",
    ) -> dict:
        """Upload an image via singleFileUpload (GraphQL multipart). Returns {id, path}."""
        query = ("mutation($input: SingleFileUploadInput!) "
                 "{ singleFileUpload(input: $input) { id path } }")
        variables = {"input": {"type": asset_type, "file": None,
                               "entityType": entity_type, "entityId": entity_id}}
        # GraphQL multipart request spec. Use a bare requests.post so the session's
        # default application/json Content-Type doesn't clobber the multipart boundary.
        multipart = {
            "operations": (None, json.dumps({"query": query, "variables": variables}), "application/json"),
            "map": (None, json.dumps({"0": ["variables.input.file"]}), "application/json"),
            "0": (filename, data, mime),
        }
        headers = {
            "User-Agent": USER_AGENT,
            "x-client-name": "matters-newsletter-bot",
            # Apollo Server blocks multipart unless a preflight header is present (CSRF guard).
            "apollo-require-preflight": "true",
            "x-apollo-operation-name": "singleFileUpload",
        }
        if self.token:
            headers["x-access-token"] = self.token
        resp = requests.post(self.api_url, files=multipart, headers=headers, timeout=120)
        try:
            body = resp.json()
        except ValueError:
            raise MattersError(f"Non-JSON upload response ({resp.status_code}): {resp.text[:300]}")
        if body.get("errors"):
            raise MattersError(f"upload error: {body['errors']}")
        return body["data"]["singleFileUpload"]

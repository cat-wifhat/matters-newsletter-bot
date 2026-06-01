"""Weekly / monthly Matters digest — compiles one draft from many articles.

Reads straight off Matters' own public GraphQL API and assembles a *single*
draft that lists many articles with @mentions of their authors. It stops at the
draft stage — nothing is published; the human reviews the draft box and
publishes manually.

Two digests:
  weekly  — site-wide hottest articles from the past 7 days, top 10, ranked.
  monthly — currently-pinned ("精選", the green channel pin) articles in each of
            the six topic channels.

Reads need no auth; we log in only to create the draft. Credentials come from the
MATTERS_EMAIL / MATTERS_PASSWORD env vars (the workflow maps the dedicated
newsletter account's secrets onto those names).
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from html import escape
from typing import Optional

import requests

from . import config
from .matters_client import MattersClient

log = logging.getLogger("digest")

MATTERS_SITE = "https://matters.town"

# Six topic channels to curate, in display order. The id is the base64 GraphQL
# node id (decodes to "TopicChannel:<n>"); discovered via the channels query.
# "創作・小說" (TopicChannel:10) is intentionally excluded.
CHANNELS: list[dict[str, str]] = [
    {"name": "生活事", "id": "VG9waWNDaGFubmVsOjE1"},   # TopicChannel:15
    {"name": "書音影", "id": "VG9waWNDaGFubmVsOjk="},    # TopicChannel:9
    {"name": "旅・居", "id": "VG9waWNDaGFubmVsOjM="},    # TopicChannel:3
    {"name": "性別／愛", "id": "VG9waWNDaGFubmVsOjEx"},  # TopicChannel:11
    {"name": "時事・趨勢", "id": "VG9waWNDaGFubmVsOjE0"}, # TopicChannel:14
    {"name": "身心靈", "id": "VG9waWNDaGFubmVsOjEz"},    # TopicChannel:13
]

# Digest article tags (Matters caps at 3 per article).
WEEKLY_TAGS = ["Matters週報", "一周熱門"]
MONTHLY_TAGS = ["Matters精選", "頻道精選"]


# ---- API reads (anonymous) ----

def _gql(query: str, variables: Optional[dict] = None) -> dict:
    """Run an anonymous read query against Matters' public GraphQL API."""
    resp = requests.post(
        config.MATTERS_API,
        json={"query": query, "variables": variables or {}},
        headers={
            "User-Agent": config.USER_AGENT,
            "Content-Type": "application/json",
            "x-client-name": "matters-newsletter-bot",
        },
        timeout=90,
    )
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL error: {body['errors']}")
    return body["data"]


_ARTICLE_FIELDS = """
  shortHash
  title
  createdAt
  appreciationsReceivedTotal
  commentCount
  readTime
  author { id userName displayName }
"""


def fetch_weekly_hottest(days: int = 7, limit: int = 10, *, scan: int = 120) -> list[dict]:
    """Site-wide hottest articles created within the past `days`, top `limit`.

    Matters' `hottest` feed already ranks by claps / comments / read-time, so we
    keep its order and just filter to the recent window. We scan up to `scan`
    articles deep (paginating) because the feed mixes in some older evergreen
    posts.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    # `first` is a custom scalar (first_Int_min_0), so it can't be bound as an
    # Int! variable — inline it. Only `after` is a plain String variable.
    query = """
    query($after:String){
      viewer{ recommendation{ hottest(input:{first:30,after:$after}){
        pageInfo{ hasNextPage endCursor }
        edges{ node{ %s } }
      } } }
    }
    """ % _ARTICLE_FIELDS

    out: list[dict] = []
    after: Optional[str] = None
    seen = 0
    while seen < scan and len(out) < limit:
        data = _gql(query, {"after": after})
        conn = data["viewer"]["recommendation"]["hottest"]
        for edge in conn["edges"]:
            seen += 1
            node = edge["node"]
            created = _parse_dt(node["createdAt"])
            if created >= cutoff:
                out.append(node)
                if len(out) >= limit:
                    break
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
    log.info("weekly: scanned %d, kept %d within %dd", seen, len(out), days)
    return out[:limit]


def fetch_channel_pinned(channel: dict, *, per_channel: int = 20) -> list[dict]:
    """Currently-pinned ("精選" green-pin) articles in one topic channel.

    The edge `pinned` flag is the channel pin. Matters exposes only the *current*
    pin state (not pin history), so this is "what's pinned now" — which is the
    rotating monthly curation.
    """
    query = """
    query($id:ID!){
      node(input:{id:$id}){ ... on TopicChannel {
        articles(input:{first:50}){
          edges{ pinned node{ %s } }
        }
      } }
    }
    """ % _ARTICLE_FIELDS
    data = _gql(query, {"id": channel["id"]})
    node = data.get("node") or {}
    edges = (node.get("articles") or {}).get("edges") or []
    pinned = [e["node"] for e in edges if e.get("pinned")]
    log.info("channel %s: %d pinned", channel["name"], len(pinned))
    return pinned[:per_channel]


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---- HTML composition (no images → no putDraft figure gotchas) ----

def _mention(author: dict) -> str:
    """Render a real Matters @mention anchor (notifies the author on publish)."""
    uname = author.get("userName") or ""
    disp = author.get("displayName") or uname
    uid = author.get("id") or ""
    return (
        f'<a class="mention" href="/@{escape(uname)}" data-id="{escape(uid)}" '
        f'data-user-name="{escape(uname)}" data-display-name="{escape(disp)}" '
        f'rel="noopener noreferrer nofollow"><span>@{escape(disp)}</span></a>'
    )


def _article_link(node: dict) -> str:
    url = f"{MATTERS_SITE}/a/{node['shortHash']}"
    return f'<a href="{escape(url)}">{escape(node["title"])}</a>'


def _stats(node: dict) -> str:
    # readTime is a site-wide accumulated reader-time ranking signal (not a
    # per-article minute estimate), so it's misleading to show; the hottest feed
    # already ranks by it. Display only the two stats that read cleanly.
    return f'👏 {node["appreciationsReceivedTotal"]} ・ 💬 {node["commentCount"]}'


def render_weekly_html(articles: list[dict], *, days: int) -> str:
    parts = [
        f"<p>過去 {days} 日 Matters 全站最熱門的 {len(articles)} 篇文章"
        f"（按拍手、留言、閱讀時長排序）。感謝各位作者：</p>"
    ]
    for i, n in enumerate(articles, 1):
        parts.append(
            f"<p>{i}. {_article_link(n)}<br>"
            f"by {_mention(n['author'])}　{_stats(n)}</p>"
        )
    return "".join(parts)


def render_monthly_html(by_channel: list[tuple[dict, list[dict]]]) -> str:
    parts = ["<p>本月各頻道精選（被置頂）文章，感謝各位作者：</p>"]
    for channel, articles in by_channel:
        parts.append(f"<h2>{escape(channel['name'])}</h2>")
        if not articles:
            parts.append("<p>（本月暫無精選）</p>")
            continue
        for n in articles:
            parts.append(
                f"<p>{_article_link(n)}<br>by {_mention(n['author'])}</p>"
            )
    return "".join(parts)


# ---- run ----

def _post_draft(title: str, content: str, tags: list[str], *, dry_run: bool) -> None:
    if dry_run:
        log.info("[DRY-RUN] title: %s", title)
        log.info("[DRY-RUN] tags: %s", tags)
        log.info("[DRY-RUN] content (%d chars):\n%s", len(content), content)
        return
    if not config.MATTERS_EMAIL or not config.MATTERS_PASSWORD:
        raise SystemExit("MATTERS_EMAIL / MATTERS_PASSWORD not set.")
    client = MattersClient()
    client.login(config.MATTERS_EMAIL, config.MATTERS_PASSWORD)
    draft_id = client.create_empty_draft(title=title)
    log.info("created draft %s", draft_id)
    client.update_draft(
        draft_id, title=title, content=content, tags=tags[:3], license="arr"
    )
    log.info("draft saved (left UNPUBLISHED in draft box): %s", title)


def run_weekly(*, dry_run: bool, days: int = 7, limit: int = 10) -> int:
    articles = fetch_weekly_hottest(days=days, limit=limit)
    if not articles:
        log.warning("no hottest articles in window; nothing to do")
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    title = f"Matters 一周熱門文章 ｜ {today}"
    content = render_weekly_html(articles, days=days)
    _post_draft(title, content, WEEKLY_TAGS, dry_run=dry_run)
    return 0


def run_monthly(*, dry_run: bool) -> int:
    by_channel = [(c, fetch_channel_pinned(c)) for c in CHANNELS]
    now = dt.datetime.now(dt.timezone.utc)
    title = f"Matters 各頻道精選 ｜ {now.year}年{now.month}月"
    content = render_monthly_html(by_channel)
    _post_draft(title, content, MONTHLY_TAGS, dry_run=dry_run)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a Matters digest draft.")
    parser.add_argument("--type", required=True, choices=["weekly", "monthly"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the composed draft instead of posting.")
    parser.add_argument("--days", type=int, default=7,
                        help="Weekly: lookback window in days (default 7).")
    parser.add_argument("--limit", type=int, default=10,
                        help="Weekly: max articles (default 10).")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    dry_run = args.dry_run or config.DRY_RUN
    if args.type == "weekly":
        return run_weekly(dry_run=dry_run, days=args.days, limit=args.limit)
    return run_monthly(dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())

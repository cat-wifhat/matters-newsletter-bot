"""Weekly / monthly Matters digest — compiles one draft from many articles.

Reads Matters' public GraphQL API and assembles a *single* draft listing many
articles with @mentions of their authors. It stops at the draft stage — nothing
is published; the human reviews the draft box and publishes manually.

Three modes:
  weekly   — site-wide top articles of the past 7 days, ranked transparently by
             (claps + comments) over the union of all topic channels, top 10,
             max 2 per author.
  snapshot — record today's channel-pinned ("精選" green pin) articles into the
             state file. Run daily so we accumulate a month of pins even though
             Matters' API exposes only the *current* pin (no history).
  monthly  — snapshot today's pins, then list every article pinned in the last
             30 days (from the accumulated state), grouped by channel.

Reads need no auth; we log in only to create the draft. Credentials come from
MATTERS_EMAIL / MATTERS_PASSWORD env vars (the workflow maps the dedicated
newsletter account's secrets onto those names).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from html import escape
from pathlib import Path
from typing import Optional

import requests

from . import config
from .matters_client import MattersClient

log = logging.getLogger("digest")

MATTERS_SITE = "https://matters.town"
DEFAULT_STATE = "state/channel_pins.json"
PIN_RETENTION_DAYS = 35  # prune state entries not seen pinned within this window

# Six channels for the monthly 精選 digest (base64 GraphQL node ids; decode to
# "TopicChannel:<n>"). "創作・小說" is intentionally excluded here.
CHANNELS: list[dict[str, str]] = [
    {"name": "生活事", "id": "VG9waWNDaGFubmVsOjE1"},   # TopicChannel:15
    {"name": "書音影", "id": "VG9waWNDaGFubmVsOjk="},    # TopicChannel:9
    {"name": "旅・居", "id": "VG9waWNDaGFubmVsOjM="},    # TopicChannel:3
    {"name": "性別／愛", "id": "VG9waWNDaGFubmVsOjEx"},  # TopicChannel:11
    {"name": "時事・趨勢", "id": "VG9waWNDaGFubmVsOjE0"}, # TopicChannel:14
    {"name": "身心靈", "id": "VG9waWNDaGFubmVsOjEz"},    # TopicChannel:13
]

# For the WEEKLY ranking we union all seven topic channels (incl. 創作・小說) to
# cover as much of the site as possible — channels exclude the SEO/spam noise
# that pollutes the raw newest feed.
WEEKLY_CHANNELS: list[dict[str, str]] = CHANNELS + [
    {"name": "創作・小說", "id": "VG9waWNDaGFubmVsOjEw"},  # TopicChannel:10
]

WEEKLY_TAGS = ["Matters週報", "一周熱門"]
MONTHLY_TAGS = ["Matters精選", "頻道精選"]

MAX_PER_AUTHOR_WEEKLY = 2  # diversify: cap any one author in the weekly top list


# ---- API reads (anonymous) ----

def _gql(query: str, variables: Optional[dict] = None) -> dict:
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
  author { id userName displayName }
"""


def _parse_dt(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _fetch_channel_articles(channel: dict, *, cutoff: Optional[dt.datetime],
                            max_pages: int) -> list[dict]:
    """Paginate a topic channel's articles, optionally stopping once older than
    `cutoff`. Returns the raw article nodes (also carrying each edge's `pinned`).
    """
    query = """
    query($id:ID!,$a:String){
      node(input:{id:$id}){ ... on TopicChannel {
        articles(input:{first:50,after:$a}){
          pageInfo{ hasNextPage endCursor }
          edges{ pinned node{ %s } }
        }
      } }
    }
    """ % _ARTICLE_FIELDS
    out: list[dict] = []
    after: Optional[str] = None
    for _ in range(max_pages):
        data = _gql(query, {"id": channel["id"], "a": after})
        conn = (data.get("node") or {}).get("articles") or {}
        stop = False
        for edge in conn.get("edges", []):
            node = dict(edge["node"])
            node["_pinned"] = bool(edge.get("pinned"))
            if cutoff is not None and _parse_dt(node["createdAt"]) < cutoff:
                stop = True
                continue
            out.append(node)
        if stop or not conn.get("pageInfo", {}).get("hasNextPage"):
            break
        after = conn["pageInfo"]["endCursor"]
    return out


# ---- weekly: transparent interaction ranking over the channel union ----

def _score(node: dict) -> int:
    return node["appreciationsReceivedTotal"] + node["commentCount"]


def fetch_weekly_top(days: int = 7, limit: int = 10, *, max_pages: int = 6) -> list[dict]:
    """Union all topic channels, keep articles created within `days`, rank by
    (claps + comments) desc, cap to MAX_PER_AUTHOR_WEEKLY per author, take `limit`.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    pool: dict[str, dict] = {}
    for ch in WEEKLY_CHANNELS:
        for node in _fetch_channel_articles(ch, cutoff=cutoff, max_pages=max_pages):
            pool[node["shortHash"]] = node  # dedupe across channels
    ranked = sorted(pool.values(), key=_score, reverse=True)

    out: list[dict] = []
    per_author: dict[str, int] = {}
    for n in ranked:
        uname = (n.get("author") or {}).get("userName") or "?"
        if per_author.get(uname, 0) >= MAX_PER_AUTHOR_WEEKLY:
            continue
        per_author[uname] = per_author.get(uname, 0) + 1
        out.append(n)
        if len(out) >= limit:
            break
    log.info("weekly: pooled %d articles in %dd, picked top %d (≤%d/author)",
             len(pool), days, len(out), MAX_PER_AUTHOR_WEEKLY)
    return out


# ---- pin snapshot state (accumulates a month of channel pins) ----

def load_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(path: str, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
                 encoding="utf-8")


def snapshot_pins(state: dict, *, today: str) -> dict:
    """Record today's currently-pinned articles per channel into `state`.

    State shape: { channel_id: { shortHash: {title, author, first_seen, last_seen} } }.
    Marks first_seen on first sighting, refreshes last_seen each run, and prunes
    entries not seen pinned within PIN_RETENTION_DAYS.
    """
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=PIN_RETENTION_DAYS))
    for ch in CHANNELS:
        bucket = state.setdefault(ch["id"], {})
        nodes = _fetch_channel_articles(ch, cutoff=None, max_pages=2)
        pinned = [n for n in nodes if n.get("_pinned")]
        log.info("snapshot %s: %d pinned today", ch["name"], len(pinned))
        for n in pinned:
            entry = bucket.get(n["shortHash"])
            if entry is None:
                bucket[n["shortHash"]] = {
                    "title": n["title"],
                    "author": n["author"],
                    "first_seen": today,
                    "last_seen": today,
                }
            else:
                entry["last_seen"] = today
                entry["title"] = n["title"]      # refresh in case of edits
                entry["author"] = n["author"]
        # prune stale
        for sh in list(bucket.keys()):
            if dt.date.fromisoformat(bucket[sh]["last_seen"]) < cutoff:
                del bucket[sh]
    return state


def pinned_within(state: dict, channel: dict, *, days: int, today: str) -> list[dict]:
    """All articles pinned in `channel` whose pin was seen within the last `days`,
    newest pin first."""
    cutoff = dt.date.fromisoformat(today) - dt.timedelta(days=days)
    bucket = state.get(channel["id"], {})
    rows = [
        {"shortHash": sh, **meta}
        for sh, meta in bucket.items()
        if dt.date.fromisoformat(meta["last_seen"]) >= cutoff
    ]
    rows.sort(key=lambda r: r["last_seen"], reverse=True)
    return rows


# ---- HTML composition (no images → no putDraft figure gotchas) ----

def _mention(author: dict) -> str:
    uname = author.get("userName") or ""
    disp = author.get("displayName") or uname
    uid = author.get("id") or ""
    return (
        f'<a class="mention" href="/@{escape(uname)}" data-id="{escape(uid)}" '
        f'data-user-name="{escape(uname)}" data-display-name="{escape(disp)}" '
        f'rel="noopener noreferrer nofollow"><span>@{escape(disp)}</span></a>'
    )


def _article_link(short_hash: str, title: str) -> str:
    url = f"{MATTERS_SITE}/a/{short_hash}"
    return f'<a href="{escape(url)}">{escape(title)}</a>'


def render_weekly_html(articles: list[dict], *, days: int) -> str:
    parts = [
        f"<p>過去 {days} 日 Matters 各頻道互動最高的 {len(articles)} 篇文章"
        f"（按拍手＋留言總數排序，每位作者最多 {MAX_PER_AUTHOR_WEEKLY} 篇）。感謝各位作者：</p>"
    ]
    for i, n in enumerate(articles, 1):
        stats = f'👏 {n["appreciationsReceivedTotal"]} ・ 💬 {n["commentCount"]}'
        parts.append(
            f"<p>{i}. {_article_link(n['shortHash'], n['title'])}<br>"
            f"by {_mention(n['author'])}　{stats}</p>"
        )
    return "".join(parts)


def render_monthly_html(by_channel: list[tuple[dict, list[dict]]], *, days: int) -> str:
    parts = [f"<p>過去 {days} 日內各頻道曾被置頂（精選）的文章，感謝各位作者：</p>"]
    for channel, rows in by_channel:
        parts.append(f"<h2>{escape(channel['name'])}</h2>")
        if not rows:
            parts.append("<p>（暫無精選）</p>")
            continue
        for r in rows:
            parts.append(
                f"<p>{_article_link(r['shortHash'], r['title'])}<br>"
                f"by {_mention(r['author'])}</p>"
            )
    return "".join(parts)


# ---- run ----

def _login_client() -> MattersClient:
    if not config.MATTERS_EMAIL or not config.MATTERS_PASSWORD:
        raise SystemExit("MATTERS_EMAIL / MATTERS_PASSWORD not set.")
    client = MattersClient()
    client.login(config.MATTERS_EMAIL, config.MATTERS_PASSWORD)
    return client


def _post_draft(title: str, content: str, tags: list[str], *, dry_run: bool) -> None:
    if dry_run:
        log.info("[DRY-RUN] title: %s", title)
        log.info("[DRY-RUN] tags: %s", tags)
        log.info("[DRY-RUN] content (%d chars):\n%s", len(content), content)
        return
    client = _login_client()
    draft_id = client.create_empty_draft(title=title)
    log.info("created draft %s", draft_id)
    client.update_draft(draft_id, title=title, content=content, tags=tags[:3], license="arr")
    log.info("draft saved (left UNPUBLISHED in draft box): %s", title)


def run_weekly(*, dry_run: bool, days: int = 7, limit: int = 10) -> int:
    articles = fetch_weekly_top(days=days, limit=limit)
    if not articles:
        log.warning("no articles in window; nothing to do")
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    title = f"Matters 一周熱門文章 ｜ {today}"
    content = render_weekly_html(articles, days=days)
    _post_draft(title, content, WEEKLY_TAGS, dry_run=dry_run)
    return 0


def run_snapshot(*, state_path: str) -> int:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    state = snapshot_pins(load_state(state_path), today=today)
    save_state(state_path, state)
    log.info("snapshot saved to %s", state_path)
    return 0


def run_monthly(*, dry_run: bool, state_path: str, days: int = 30) -> int:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    # Always fold today's pins in first, so even a fresh state isn't empty.
    state = snapshot_pins(load_state(state_path), today=today)
    save_state(state_path, state)
    by_channel = [(c, pinned_within(state, c, days=days, today=today)) for c in CHANNELS]
    now = dt.datetime.now(dt.timezone.utc)
    title = f"Matters 各頻道精選 ｜ {now.year}年{now.month}月"
    content = render_monthly_html(by_channel, days=days)
    _post_draft(title, content, MONTHLY_TAGS, dry_run=dry_run)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a Matters digest draft.")
    parser.add_argument("--type", required=True, choices=["weekly", "monthly", "snapshot"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the composed draft instead of posting.")
    parser.add_argument("--days", type=int, default=None,
                        help="weekly lookback (default 7) / monthly pin window (default 30).")
    parser.add_argument("--limit", type=int, default=10, help="Weekly: max articles.")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Pin-snapshot state JSON path.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    dry_run = args.dry_run or config.DRY_RUN
    if args.type == "weekly":
        return run_weekly(dry_run=dry_run, days=args.days or 7, limit=args.limit)
    if args.type == "snapshot":
        return run_snapshot(state_path=args.state)
    return run_monthly(dry_run=dry_run, state_path=args.state, days=args.days or 30)


if __name__ == "__main__":
    sys.exit(main())

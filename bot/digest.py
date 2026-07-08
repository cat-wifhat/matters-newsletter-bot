"""Weekly / biweekly Matters digest — compiles one draft from many articles.

Reads Matters' public GraphQL API and assembles a *single* draft listing many
articles with @mentions of their authors. It stops at the draft stage — nothing
is published; the human reviews the draft box and publishes manually.

Three modes:
  weekly   — site-wide top articles of the past 7 days, ranked transparently by
             (claps + comments) over the union of all topic channels, top 10,
             max 2 per author.
  snapshot — record today's channel-pinned ("精選" green pin) articles into the
             state file. Run daily so we accumulate pins over time even though
             Matters' API exposes only the *current* pin (no history).
  biweekly — site-wide hot (past 14 days, same logic as weekly) PLUS every
             article pinned in the last 14 days (from the accumulated state),
             grouped by channel. Two columns in one draft.

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
from itertools import zip_longest
from pathlib import Path
from typing import Optional

import requests

from . import config
from .matters_client import MattersClient

log = logging.getLogger("digest")

DEFAULT_STATE = "state/channel_pins.json"
PIN_RETENTION_DAYS = 35  # prune state entries not seen pinned within this window

# Six channels for the biweekly 精選 (pinned) column (base64 GraphQL node ids;
# decode to "TopicChannel:<n>"). "創作・小說" is intentionally excluded here.
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
BIWEEKLY_TAGS = ["Matters雙周報", "全站熱門", "頻道精選"]

# 回應（civic.ai #3）：把「廣播」變「對話」，邀請社群提名／補充／糾正下一期。
CTA_HTML = '<p>覺得有遺珠？歡迎在這篇留言或標註～</p>'

MAX_PER_AUTHOR_WEEKLY = 2  # diversify: cap any one author in the weekly top list


# ---- API reads (anonymous) ----

def _gql(query: str, variables: Optional[dict] = None) -> dict:
    resp = requests.post(
        config.MATTERS_READ_ENDPOINT,
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
    # 中性時序：按首次被置頂的時間排，不代表重要程度（置頂時長非品質訊號）。
    rows.sort(key=lambda r: r["first_seen"])
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
    url = f"{config.MATTERS_SITE}/a/{short_hash}"
    return f'<a href="{escape(url)}">{escape(title)}</a>'


def render_weekly_html(articles: list[dict], *, days: int) -> str:
    intro = (
        "<p>這是一份以 AI 製作的 Matters「全站熱門周報」，綜合數據算法，"
        "轉化為一份社群清單。但 AI 不替你決定什麼重要——它只負責把社群的"
        "拍手與留言，忠實地記錄、整理出來。</p>"
        "<blockquote><p>「文字的迴聲，由你的每一次拍手與留言決定。」</p></blockquote>"
        "<p>這份周報的誕生，是為了記錄過去 7 天內在 Matters 社群中互動最熱烈、最能引起"
        "共鳴的 10 篇文章。周報打破了頻道的邊界，將「生活事」、「書音影」、「旅・居」、「性別／愛」、"
        "「時事・趨勢」、「身心靈」、「創作・小說」這七大頻道的數據合併，為大家打包精選。</p>"
        "<p><strong>📊 周報是怎麼挑選的？</strong></p>"
        "<ul>"
        "<li>時間限定：只計算過去 7 天內發表的新鮮文章。</li>"
        "<li>社區迴響：周報看到的是文友之間的走動。你給的每一記拍手（👏）"
        "和留下的每一則留言（💬）都是 1 次紀錄。</li>"
        "<li>百花齊放：為了讓更多創作者被看見，每位作者每週最多僅保留 "
        f"{MAX_PER_AUTHOR_WEEKLY} 篇作品入榜。</li>"
        "</ul>"
        "<p>我們相信：好的演算法應該透明、可核對、向社群負責，是社群這一周互動的鏡子。</p>"
        "<p>這是一份由讀者互動紀錄催生的「全站熱門榜」，感謝每一位用文字點燃思考的創作者，"
        "以及用互動支持好文的你。</p>"
        + CTA_HTML +
        "<hr>"
    )
    parts = [intro]
    for i, n in enumerate(articles, 1):
        stats = f'👏 {n["appreciationsReceivedTotal"]} ・ 💬 {n["commentCount"]}'
        parts.append(
            f"<p>{i}. {_article_link(n['shortHash'], n['title'])}<br>"
            f"by {_mention(n['author'])}　{stats}</p>"
        )
    return "".join(parts)


def render_biweekly_html(hot_articles: list[dict],
                         by_channel: list[tuple[dict, list[dict]]], *, days: int) -> str:
    intro = (
        "<p>這是一份以 AI 製作的 Matters 雙周總結，分為「全站熱門雙周報」與「置頂文章雙周報」"
        "兩個欄目，為大家留下這兩周的閱讀清單。但 AI 不替你決定什麼重要——它只負責把社群的"
        "互動，忠實地記錄、整理出來。</p>"
        "<blockquote><p>「留下一份清單，記住這兩周大家留下的閱讀與思想。」</p></blockquote>"
        "<p>這份雙周報的誕生，是為了記錄過去 14 天內在 Matters 社群中聊得最熱烈，以及在各頻道"
        "曾被推薦過的文章。雙周報將數據與頻道分類呈現，方便大家按圖索驥，回顧這兩周留下來的文字。</p>"
        "<p><strong>📊 欄目一：全站熱門雙周報是怎麼挑選的？</strong></p>"
        "<ul>"
        "<li>時間限定：只計算過去 14 天內發表的文章。</li>"
        "<li>社區迴響：雙周報看到的是文友之間的走動。你給的每一記拍手（👏）和留下的每一則留言"
        "（💬）都是 1 次紀錄。</li>"
        "<li>百花齊放：為了讓更多創作者被看見，每位作者最多僅保留 2 篇作品入榜。</li>"
        "</ul>"
        "<p><strong>📊 欄目二：置頂文章雙周報是怎麼挑選的？</strong></p>"
        "<ul>"
        "<li>時間限定：收集過去 14 天內在各大頻道被推薦過的文章。</li>"
        "<li>精選定義：這裡不看互動數據的高低，只記錄各頻道內被置頂（綠色 pin 📌）的文章。</li>"
        "<li>時光快照：由於網站只會顯示「目前置頂」，沒有歷史紀錄，所以數據 AI 每天都會自動拍下"
        "各頻道的快照，把這兩周內曾出現過的所有置頂文章記下來，累積成這份雙周清單。</li>"
        "</ul>"
        "<p>我們相信：好的演算法應該透明、可核對、向社群負責，是社群這兩周互動的鏡子。</p>"
        + CTA_HTML +
        "<hr>"
    )
    parts = [intro]

    # 欄目一：全站熱門雙周報（過去 14 天，拍手＋留言）
    parts.append("<p><strong>🔥 全站熱門雙周報</strong></p>")
    if not hot_articles:
        parts.append("<p>（暫無資料）</p>")
    for i, n in enumerate(hot_articles, 1):
        stats = f'👏 {n["appreciationsReceivedTotal"]} ・ 💬 {n["commentCount"]}'
        parts.append(
            f"<p>{i}. {_article_link(n['shortHash'], n['title'])}<br>"
            f"by {_mention(n['author'])}　{stats}</p>"
        )

    parts.append("<hr>")

    # 欄目二：置頂文章雙周報（依累積快照，按頻道分組）
    parts.append("<p><strong>📌 置頂文章雙周報</strong></p>")
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


def _today_hkt() -> str:
    """封面顯示用日期：香港時間（UTC+8），讀者所在時區。內部計分／快照仍用 UTC。"""
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()


# 防重複：GitHub 排程不可靠（延遲/丟棄），故每個 workflow 排「主＋備」兩個時段。
# 發佈成功後記下當日 HKT 日期；備用時段見「當日已發過同類」就跳過，確保每次只出一份。
# 每種各記各的檔（published-weekly.json / published-biweekly.json），避免週報／雙週報
# 同時跑時爭寫同一檔造成 git push 衝突（rebase 撞 JSON）。
def _marker_path(kind: str) -> str:
    return f"state/published-{kind}.json"


def _already_published_today(kind: str) -> bool:
    try:
        data = json.loads(Path(_marker_path(kind)).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return False
    return data.get("date") == _today_hkt()


def _mark_published(kind: str) -> None:
    p = Path(_marker_path(kind))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"date": _today_hkt()}, ensure_ascii=False, indent=2),
                 encoding="utf-8")


def _make_cover(kicker: str, today_iso: str, titles: list[str], theme: str = "riso") -> Optional[bytes]:
    """Auto-extract keywords and render the collage cover PNG. Never blocks the draft."""
    try:
        from .cover import keywords
        from .collage import generate
        kws = keywords(titles)[:10]
        return generate(kicker, today_iso.replace("-", " · "), kws, theme)
    except Exception as e:  # noqa: BLE001 — cover is best-effort
        log.warning("cover generation failed (%s); posting without cover", e)
        return None


def _post_draft(title: str, content: str, tags: list[str], *,
                summary: Optional[str] = None, cover_png: Optional[bytes] = None,
                caption: str = "", dry_run: bool) -> None:
    if dry_run:
        log.info("[DRY-RUN] title: %s", title)
        if summary:
            log.info("[DRY-RUN] summary: %s", summary)
        if cover_png:
            log.info("[DRY-RUN] cover image generated (%d bytes)", len(cover_png))
        log.info("[DRY-RUN] tags: %s", tags)
        log.info("[DRY-RUN] content (%d chars):\n%s", len(content), content)
        return
    client = _login_client()
    draft_id = client.create_empty_draft(title=title)
    log.info("created draft %s", draft_id)
    cover_id = None
    if cover_png:
        cover = client.upload_asset(cover_png, "cover.png", "cover", draft_id)
        embed = client.upload_asset(cover_png, "embed.png", "embed", draft_id)
        cover_id = cover["id"]
        content = (f'<figure class="image"><img src="{escape(embed["path"])}" '
                   f'data-asset-id="{escape(embed["id"])}" alt="">'
                   f'<figcaption><span>{escape(caption)}</span></figcaption></figure>'
                   + content)
        log.info("uploaded cover=%s embed=%s", cover["id"], embed["id"])
    client.update_draft(draft_id, title=title, content=content, summary=summary,
                        cover=cover_id, tags=tags[:3], license="arr")
    log.info("draft saved (left UNPUBLISHED in draft box): %s", title)


def run_weekly(*, dry_run: bool, days: int = 7, limit: int = 10) -> int:
    if not dry_run and _already_published_today("weekly"):
        log.info("weekly already published today (%s); skipping (backup run)", _today_hkt())
        return 0
    articles = fetch_weekly_top(days=days, limit=limit)
    if not articles:
        log.warning("no articles in window; nothing to do")
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    title = "週報：Matters 一週速報 ｜ 社群熱門文章"
    summary = (f"由社群的拍手與留言長成——過去 {days} 日 Matters 各頻道互動最高的 "
               f"{len(articles)} 篇。")
    content = render_weekly_html(articles, days=days)
    cover_png = _make_cover("一週速報 ｜ 社群熱門文章", _today_hkt(), [a["title"] for a in articles], theme="riso")
    _post_draft(title, content, WEEKLY_TAGS, summary=summary, cover_png=cover_png,
                caption="圖中關鍵字由過去七日熱門文章自動擷取", dry_run=dry_run)
    if not dry_run:
        _mark_published("weekly")
    return 0


def run_snapshot(*, state_path: str) -> int:
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    state = snapshot_pins(load_state(state_path), today=today)
    save_state(state_path, state)
    log.info("snapshot saved to %s", state_path)
    return 0


def run_biweekly(*, dry_run: bool, state_path: str, days: int = 14) -> int:
    if not dry_run and _already_published_today("biweekly"):
        log.info("biweekly already published today (%s); skipping (backup run)", _today_hkt())
        return 0
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    # 欄目二：先把今日置頂併入累積狀態（即使狀態空也不會全空），再列兩周置頂。
    state = snapshot_pins(load_state(state_path), today=today)
    save_state(state_path, state)
    by_channel = [(c, pinned_within(state, c, days=days, today=today)) for c in CHANNELS]
    # 欄目一：過去 14 天全站熱門（與周報同邏輯，僅天數不同）。
    hot_articles = fetch_weekly_top(days=days, limit=10)
    title = "雙週報：Matters 雙週回顧 ｜ 熱門文章 ＋ 編輯精選"
    summary = (f"由社群互動長成——過去 {days} 日 Matters 全站熱門 {len(hot_articles)} 篇，"
               "加各頻道編輯置頂過的文章。")
    content = render_biweekly_html(hot_articles, by_channel, days=days)
    # 封面關鍵字：熱門（欄目一）＋置頂（欄目二）交錯，讓兩欄都被代表到。
    pinned_titles = [r["title"] for _, rows in by_channel for r in rows]
    mixed_titles = [t for pair in zip_longest([a["title"] for a in hot_articles], pinned_titles)
                    for t in pair if t]
    cover_png = _make_cover("雙週回顧 ｜ 熱門文章 ＋ 編輯精選", _today_hkt(), mixed_titles, theme="coral")
    _post_draft(title, content, BIWEEKLY_TAGS, summary=summary, cover_png=cover_png,
                caption="圖中關鍵字由過去十四日熱門及置頂文章自動擷取", dry_run=dry_run)
    if not dry_run:
        _mark_published("biweekly")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile a Matters digest draft.")
    parser.add_argument("--type", required=True, choices=["weekly", "biweekly", "snapshot"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the composed draft instead of posting.")
    parser.add_argument("--days", type=int, default=None,
                        help="weekly lookback (default 7) / biweekly window (default 14).")
    parser.add_argument("--limit", type=int, default=10, help="Weekly: max articles.")
    parser.add_argument("--state", default=DEFAULT_STATE, help="Pin-snapshot state JSON path.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config.validate_endpoints()
    log.info("READ %s (%s)  →  WRITE %s (%s)  | links→%s",
             config.env_label(config.MATTERS_READ_ENDPOINT), config.MATTERS_READ_ENDPOINT,
             config.env_label(config.MATTERS_WRITE_ENDPOINT), config.MATTERS_WRITE_ENDPOINT,
             config.MATTERS_SITE)
    dry_run = args.dry_run or config.DRY_RUN
    if args.type == "weekly":
        return run_weekly(dry_run=dry_run, days=args.days or 7, limit=args.limit)
    if args.type == "snapshot":
        return run_snapshot(state_path=args.state)
    return run_biweekly(dry_run=dry_run, state_path=args.state, days=args.days or 14)


if __name__ == "__main__":
    sys.exit(main())

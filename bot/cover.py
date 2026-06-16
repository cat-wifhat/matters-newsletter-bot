"""Generate a 1200x1200 cover image (keyword word-cloud) for a digest.

Matches the locked design: purple bg, lime/white/lilac keyword cloud, four-point
stars, official white Matters logo (Lab cropped) + date on the bottom baseline.
Fonts: Noto Sans TC (vendored). Keywords are auto-extracted from article titles.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import jieba.analyse as _ana
import jieba.posseg as pseg
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from zhconv import convert as _zh

ASSETS = Path(__file__).parent / "assets"
FONT = str(ASSETS / "NotoSansTC.ttf")
LOGO_WHITE = str(ASSETS / "matters-logo-white.png")

# Glyph coverage of the cover font — any keyword with a char outside this set
# would render as a tofu box, so we drop it (never show undisplayable text).
_CMAP = set(TTFont(FONT).getBestCmap().keys())
def _covered(w: str) -> bool:
    return all(ord(c) in _CMAP for c in w)

PURPLE = (114, 88, 255, 255)   # #7258ff
LIME = (195, 244, 50, 255)     # #c3f432
WHITE = (255, 255, 255, 255)
LILAC = (207, 198, 255, 255)   # #cfc6ff
CYAN = (111, 227, 227, 255)    # #6fe3e3

# Pre-tuned word-cloud slots (x, y centre, tier). 3 big / 5 mid / 4 small.
SLOTS = [
    (396, 450, "L"), (882, 486, "L"), (612, 708, "L"),
    (228, 552, "M"), (942, 672, "M"), (528, 546, "M"), (456, 840, "M"), (924, 840, "M"),
    (552, 330, "S"), (276, 726, "S"), (792, 348, "S"), (1002, 552, "S"),
]
STARS = [(1015, 325, 30, WHITE), (295, 845, 26, CYAN), (985, 940, 20, WHITE)]

_STOP = set("一個我們你們他們這個那個就是這樣可以已經沒有什麼以及之後之前關於還有因為所以但是如果不過然後其實這些那些".split())
_CJK = re.compile(r"[一-鿿]")


_FONT_CACHE: dict = {}
def _font(size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = _FONT_CACHE.get((size, weight))
    if f is None:
        f = ImageFont.truetype(FONT, size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        _FONT_CACHE[(size, weight)] = f
    return f


# POS tags kept as keyword candidates (nouns, place/person/proper names, idioms…).
_NOUN_POS = ("ns", "nr", "nz", "nt", "n", "nl", "ng", "vn", "l", "i", "j", "s")


def _title_terms(title: str) -> list[str]:
    """Salient terms for one title. jieba works best on Simplified, so segment in
    Simplified then convert the chosen terms back to Traditional for display."""
    simp = _zh(title, "zh-hans")
    terms = [_zh(t, "zh-hant") for t in _ana.extract_tags(simp, topK=5, allowPOS=_NOUN_POS)]
    if not terms:  # fallback: longest noun-ish tokens
        toks = [_zh(w, "zh-hant") for w, f in pseg.cut(simp) if f and f[0] in "nivls"]
        terms = sorted(set(toks), key=len, reverse=True)
    return terms


def keywords(titles: list[str], k: int = 12) -> list[str]:
    """Extract up to k clean word-cloud keywords (Traditional, font-safe, ≤2/title).

    - Always Traditional (避免簡體缺字顯示成豆腐).
    - TF-IDF salient terms (避免「龍山寺」被斷成「山寺」之類的破碎語意).
    - Drop any term with a glyph the cover font can't render (零豆腐字).
    """
    out: list[str] = []
    for title in titles:
        added = 0
        for w in _title_terms(title):
            w = w.strip()
            if not (2 <= len(w) <= 4) or not _CJK.search(w):
                continue
            if w in _STOP or w in out or not _covered(w):
                continue
            out.append(w)
            added += 1
            if added >= 2 or len(out) >= k:
                break
        if len(out) >= k:
            break
    return out[:k]


def _star(d: ImageDraw.ImageDraw, cx: int, cy: int, s: int, color) -> None:
    pts = [(0, -1), (.22, -.22), (1, 0), (.22, .22), (0, 1), (-.22, .22), (-1, 0), (-.22, -.22)]
    d.polygon([(cx + a * s, cy + b * s) for a, b in pts], fill=color)


def _logo_no_lab() -> Image.Image:
    """White Matters logo with the trailing 'Lab' word cropped off."""
    im = Image.open(LOGO_WHITE).convert("RGBA")
    a = im.split()[3].load()
    w, h = im.size
    colmax = [max(a[x, y] for y in range(0, h, 3)) for x in range(w)]
    cols = [x for x, v in enumerate(colmax) if v > 12]
    c0, c1 = cols[0], cols[-1]
    gaps, run = [], None
    for x in range(c0, c1 + 1):
        if colmax[x] <= 12:
            run = run if run is not None else x
        elif run is not None:
            gaps.append((run, x - run))
            run = None
    top2 = sorted(gaps, key=lambda g: g[1], reverse=True)[:2]  # mark|Matters, Matters|Lab
    cut = max(g[0] for g in top2) if top2 else c1 + 1
    rows = [y for y in range(h) if max(a[x, y] for x in range(c0, cut)) > 12]
    return im.crop((c0, rows[0], cut, rows[-1] + 1))


def generate(kicker: str, date_str: str, words: list[str]) -> bytes:
    """Render the cover and return PNG bytes."""
    img = Image.new("RGBA", (1200, 1200), PURPLE)
    d = ImageDraw.Draw(img)

    for cx, cy, s, color in STARS:
        _star(d, cx, cy, s, color)

    d.text((80, 150), kicker, font=_font(38, 700), fill=LIME, anchor="ls")

    base = {"L": 125, "M": 84, "S": 58}
    weight = {"L": 900, "M": 700, "S": 700}
    color = {"L": LIME, "M": WHITE, "S": LILAC}
    slots = {t: [s for s in SLOTS if s[2] == t] for t in "LMS"}

    pool = list(words)
    def _take(maxlen: int, strict: bool):
        for i, w in enumerate(pool):
            if len(w) <= maxlen:
                return pool.pop(i)
        return None if strict else (pool.pop(0) if pool else None)

    plan = []
    for s in slots["L"]:                       # 大字槽只放 ≤3 字，避免太寬相撞
        w = _take(3, strict=True)
        if w:
            plan.append((w, s))
    for s in slots["M"] + slots["S"]:          # 4 字詞放中／小槽，空間足夠
        w = _take(4, strict=False)
        if w:
            plan.append((w, s))
    for w, (x, y, tier) in plan:
        # 4 字詞自動縮窄，佔寬 ≈ 3 字詞，避免與鄰詞相撞。
        size = base[tier] if len(w) <= 3 else round(base[tier] * 3 / len(w))
        d.text((x, y), w, font=_font(size, weight[tier]), fill=color[tier], anchor="ms")

    logo = _logo_no_lab()
    th = 48
    logo = logo.resize((round(logo.width * th / logo.height), th), Image.LANCZOS)
    img.alpha_composite(logo, (70, 1108 - th // 2))

    d.text((1120, 1122), date_str, font=_font(36, 500), fill=LILAC, anchor="rs")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()

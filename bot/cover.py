"""Generate a 1200x1200 cover image (keyword word-cloud) for a digest.

Matches the locked design: purple bg, lime/white/lilac keyword cloud, four-point
stars, official white Matters logo (Lab cropped) + date on the bottom baseline.
Fonts: Noto Sans TC (vendored). Keywords are auto-extracted from article titles.
"""
from __future__ import annotations

import io
import math
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
# Star positions (x, y, size); colours come from the theme.
STAR_POS = [(1015, 325, 30), (295, 845, 26), (985, 940, 20)]

# Two locked colour themes. "purple" = 周報（原版）; "lime" = 雙周報（鮮色版）。
THEMES = {
    "purple": {
        "bg": PURPLE, "L": LIME, "M": WHITE, "S": LILAC,
        "kicker": LIME, "date": LILAC, "logo": WHITE,
        "stars": [WHITE, CYAN, WHITE],
    },
    "lime": {
        "bg": LIME,
        "L": (90, 67, 229, 255),     # #5a43e5 鮮紫
        "M": (36, 25, 83, 255),      # #241953 深紫近黑
        "S": (124, 92, 240, 255),    # #7c5cf0 中紫
        "kicker": (90, 67, 229, 255), "date": (90, 67, 229, 255),
        "logo": (30, 18, 64, 255),   # #1e1240 深紫 logo（萊姆底用深色才看得到）
        "stars": [(90, 67, 229, 255), (47, 207, 208, 255), (90, 67, 229, 255)],
    },
    "greengold": {                   # 經典綠金（legacy 品牌色）
        "bg": (13, 103, 99, 255),    # #0d6763 經典綠
        "L": (192, 164, 107, 255),   # #c0a46b 金
        "M": (255, 255, 255, 255),   # white
        "S": (159, 225, 203, 255),   # #9fe1cb 淺青
        "kicker": (192, 164, 107, 255), "date": (159, 225, 203, 255),
        "logo": (255, 255, 255, 255),  # 白 logo（深綠底）
        "stars": [(192, 164, 107, 255), (255, 255, 255, 255), (159, 225, 203, 255)],
    },
}

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


def _decor(img: Image.Image, th: dict) -> None:
    """線條裝飾（細內框 + 雙角放射細線），畫在文字下層。各主題色通用。"""
    o = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    d.rounded_rectangle([56, 56, 1144, 1144], radius=30, outline=th["S"][:3] + (130,), width=3)
    ray = th["L"][:3] + (60,)
    for a in range(98, 176, 11):    # 右上角扇形
        d.line([1200, 0, 1200 + 520 * math.cos(math.radians(a)), 520 * math.sin(math.radians(a))],
               fill=ray, width=4)
    for a in range(278, 356, 11):   # 左下角扇形
        d.line([0, 1200, 520 * math.cos(math.radians(a)), 1200 + 520 * math.sin(math.radians(a))],
               fill=ray, width=4)
    img.alpha_composite(o)


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


def generate(kicker: str, date_str: str, words: list[str], theme: str = "purple",
             decor=None) -> bytes:
    """Render the cover and return PNG bytes. theme: 'purple' / 'lime' / 'greengold'.
    decor: optional callable(img, theme_dict) drawn under the words (e.g. 線條)."""
    th = THEMES[theme]
    img = Image.new("RGBA", (1200, 1200), th["bg"])
    deco = _decor if decor is None else decor  # 預設套用線條裝飾；decor=False 可關閉
    if deco:
        deco(img, th)
    d = ImageDraw.Draw(img)

    for (cx, cy, s), col in zip(STAR_POS, th["stars"]):
        _star(d, cx, cy, s, col)

    d.text((80, 150), kicker, font=_font(38, 700), fill=th["kicker"], anchor="ls")

    base = {"L": 125, "M": 84, "S": 58}
    weight = {"L": 900, "M": 700, "S": 700}
    color = {"L": th["L"], "M": th["M"], "S": th["S"]}
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
    tint = Image.new("RGBA", logo.size, th["logo"])  # 依主題上色（白／深紫）
    tint.putalpha(logo.split()[3])
    lh = 48
    tint = tint.resize((round(tint.width * lh / tint.height), lh), Image.LANCZOS)
    img.alpha_composite(tint, (70, 1108 - lh // 2))

    d.text((1120, 1122), date_str, font=_font(36, 500), fill=th["date"], anchor="rs")

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()

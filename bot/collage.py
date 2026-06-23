"""關鍵字拼貼封面（程式自動生成）。撕貼卡片＋輕質感＋顆粒噪點，限定色盤。
主題：riso（週報·孔版紅藍）/ earthy（雙週·土系）/ coral / vintage。非 Matters 品牌色。
每期只換 words，版式自動排版；長短詞皆可。
"""
from __future__ import annotations

import io
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
FONT = str(ASSETS / "NotoSansTC.ttf")
LOGO = str(ASSETS / "matters-logo-white.png")

THEMES = {
    "riso": {     # 週報·孔版：米紙底＋番茄紅／鈷藍／墨黑
        "bg": (243, 234, 212),
        "accent": [(232, 85, 47), (31, 58, 138)],
        "chips": [((232, 85, 47), (243, 234, 212)), ((31, 58, 138), (243, 234, 212)),
                  ((243, 234, 212), (31, 58, 138)), ((26, 26, 26), (243, 234, 212)),
                  ((232, 85, 47), (26, 26, 26))],
        "title": (26, 26, 26), "sub": (31, 58, 138), "logo": (26, 26, 26),
    },
    "earthy": {   # 雙週·土系：青綠／芥末／鏽紅
        "bg": (232, 226, 207),
        "accent": [(63, 114, 105), (207, 158, 59)],
        "chips": [((63, 114, 105), (239, 233, 214)), ((207, 158, 59), (42, 32, 16)),
                  ((177, 90, 58), (255, 247, 238)), ((239, 233, 214), (38, 48, 43)),
                  ((38, 48, 43), (239, 233, 214))],
        "title": (38, 48, 43), "sub": (177, 90, 58), "logo": (38, 48, 43),
    },
    "coral": {    # 暖珊瑚／粉／金黃
        "bg": (247, 238, 221),
        "accent": [(239, 111, 83), (231, 169, 58)],
        "chips": [((239, 111, 83), (255, 247, 238)), ((231, 169, 58), (90, 42, 30)),
                  ((232, 88, 138), (255, 247, 238)), ((251, 243, 226), (194, 59, 42)),
                  ((42, 20, 16), (251, 243, 226))],
        "title": (42, 20, 16), "sub": (194, 59, 42), "logo": (42, 20, 16),
    },
    "vintage": {  # 復古：牛皮棕／鼠尾草綠／灰玫瑰
        "bg": (239, 230, 210),
        "accent": [(176, 141, 87), (127, 143, 94)],
        "chips": [((176, 141, 87), (40, 30, 18)), ((127, 143, 94), (244, 239, 224)),
                  ((185, 129, 127), (40, 30, 18)), ((244, 239, 224), (90, 70, 45)),
                  ((90, 70, 45), (244, 239, 224))],
        "title": (74, 56, 36), "sub": (127, 143, 94), "logo": (74, 56, 36),
    },
}


def _font(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _logo_no_lab() -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    a = im.split()[3].load(); w, h = im.size
    colmax = [max(a[x, y] for y in range(0, h, 3)) for x in range(w)]
    cols = [x for x, v in enumerate(colmax) if v > 12]; c0, c1 = cols[0], cols[-1]
    gaps, run = [], None
    for x in range(c0, c1 + 1):
        if colmax[x] <= 12:
            run = run if run is not None else x
        elif run is not None:
            gaps.append((run, x - run)); run = None
    top2 = sorted(gaps, key=lambda g: g[1], reverse=True)[:2]
    cut = max(g[0] for g in top2) if top2 else c1 + 1
    rows = [y for y in range(h) if max(a[x, y] for x in range(c0, cut)) > 12]
    return im.crop((c0, rows[0], cut, rows[-1] + 1))


def _torn(w, h, rng, jit=7, seg=9):
    p = []
    for i in range(seg): p.append((w * i / seg, rng.uniform(0, jit)))
    for i in range(seg): p.append((w - rng.uniform(0, jit), h * i / seg))
    for i in range(seg): p.append((w - w * i / seg, h - rng.uniform(0, jit)))
    for i in range(seg): p.append((rng.uniform(0, jit), h - h * i / seg))
    return p


def _confetti(img, th, rng):
    W, H = img.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cols = [c + (210,) for c in th["accent"]] + [th["title"] + (170,)]
    for _ in range(10):
        x, y = rng.randint(40, W - 60), rng.randint(150, H - 130)
        col = rng.choice(cols); s = rng.randint(8, 16)
        shape = rng.choice(["o", "c", "t", "p", "x"])
        if shape == "o":
            d.ellipse([x, y, x + s, y + s], fill=col)
        elif shape == "c":
            d.ellipse([x, y, x + s, y + s], outline=col, width=3)
        elif shape == "t":
            d.polygon([(x, y + s), (x + s, y + s), (x + s / 2, y)], fill=col)
        elif shape == "p":
            r = Image.new("RGBA", (s * 3, s), col)
            layer.alpha_composite(r.rotate(rng.uniform(-30, 30), expand=True), (x, y))
        elif shape == "x":
            d.rectangle([x, y + s / 2 - 2, x + s, y + s / 2 + 2], fill=col)
            d.rectangle([x + s / 2 - 2, y, x + s / 2 + 2, y + s], fill=col)
    img.alpha_composite(layer)


def generate(kicker: str, date_str: str, words: list[str], theme: str = "riso") -> bytes:
    """渲染拼貼封面，回傳 PNG bytes。theme: riso/earthy/coral/vintage。"""
    th = THEMES[theme]
    W = H = 1200
    img = Image.new("RGBA", (W, H), th["bg"] + (255,))
    d = ImageDraw.Draw(img)
    rng = random.Random(3)

    # 背景撕紙色塊 ＋ 半調網點（孔版）
    for k, col in enumerate(th["accent"]):
        bw, bh = rng.randint(520, 660), rng.randint(360, 460)
        ox, oy = (60 if k == 0 else W - bw - 60), (150 if k == 0 else H - bh - 170)
        poly = [(ox + x, oy + y) for x, y in _torn(bw, bh, rng, jit=14, seg=10)]
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(poly, fill=col + (40,))
        img.alpha_composite(layer)
        if theme == "riso":
            dcol = tuple(int(c * 0.5) for c in col) + (80,)
            dots = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dd = ImageDraw.Draw(dots)
            for yy in range(oy, oy + bh, 18):
                for xx in range(ox, ox + bw, 18):
                    dd.ellipse([xx, yy, xx + 4, yy + 4], fill=dcol)
            mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).polygon(poly, fill=255)
            img.alpha_composite(Image.composite(dots, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))
    _confetti(img, th, rng)

    d.text((86, 96), kicker, font=_font(50, 800), fill=th["title"] + (255,), anchor="ls")

    margin, gap, padx, pady = 86, 22, 32, 18
    maxw = W - 2 * margin

    def size_for(i):
        return 88 if i < 2 else (62 if i < 5 else 50)

    chips = []
    for i, w in enumerate(words):
        s = size_for(i)
        f = _font(s, 800 if i < 2 else 700)
        tw = d.textlength(w, font=f)
        while tw + 2 * padx > maxw and s > 34:
            s -= 6; f = _font(s, 700); tw = d.textlength(w, font=f)
        cw, ch = int(tw + 2 * padx), int(s * 1.3 + 2 * pady)
        bg, tc = th["chips"][i % len(th["chips"])]
        chip = Image.new("RGBA", (cw + 16, ch + 16), (0, 0, 0, 0))
        cd = ImageDraw.Draw(chip)
        cd.polygon([(8 + x, 8 + y) for x, y in _torn(cw, ch, rng, jit=7, seg=8)], fill=bg + (255,))
        cd.text(((cw + 16) / 2, (ch + 16) / 2), w, font=f, fill=tc + (255,), anchor="mm")
        chips.append(chip)

    rows, cur, curw = [], [], 0
    for chip in chips:
        if cur and curw + gap + chip.width > maxw:
            rows.append((cur, curw)); cur, curw = [], 0
        if cur:
            curw += gap
        cur.append(chip); curw += chip.width
    if cur:
        rows.append((cur, curw))

    rowh = int(max(c.height for c in chips) * 0.94)
    y = (H - len(rows) * rowh) // 2 + 24
    for row, roww in rows:
        x = (W - roww) // 2
        for chip in row:
            rc = chip.rotate(rng.uniform(-6, 6), expand=True, resample=Image.BICUBIC)
            cy = y + (rowh - chip.height) // 2 + rng.randint(-7, 7)
            img.alpha_composite(rc, (int(x - (rc.width - chip.width) / 2),
                                     int(cy - (rc.height - chip.height) / 2)))
            x += chip.width + gap
        y += rowh

    # Matters logo（左下）＋ 日期（右下，與 logo 中線對齊）
    logo = _logo_no_lab()
    tint = Image.new("RGBA", logo.size, th["logo"] + (255,)); tint.putalpha(logo.split()[3])
    lh = 48; tint = tint.resize((round(tint.width * lh / tint.height), lh), Image.LANCZOS)
    logo_y = H - 100
    img.alpha_composite(tint, (86, logo_y))
    d.text((1114, logo_y + lh // 2), date_str, font=_font(32, 600),
           fill=th["sub"] + (255,), anchor="rm")

    n = Image.effect_noise((W, H), 64).convert("L")
    img.alpha_composite(Image.merge("RGBA", (n, n, n, Image.new("L", (W, H), 20))))

    out = io.BytesIO()
    img.convert("RGB").save(out, "PNG")
    return out.getvalue()

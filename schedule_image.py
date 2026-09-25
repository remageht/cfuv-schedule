# -*- coding: utf-8 -*-
"""Рендер расписания КФУ в PNG-картинку (Telegram sendPhoto).

Требует Pillow (`pip install Pillow`). Шрифты: Windows — Arial,
Linux — DejaVu Sans. Без Pillow бот просто работает только текстом.

Использование:
    import schedule_image, parser
    idx = parser.get_index()
    g = parser.get_group("ПИ-б-о-241")
    png: bytes = schedule_image.render_day(
        code=g["код"], day_name="Понедельник", parity="чёт",
        lessons=parser.lessons_of_day(g, 1, "чёт"),
        bells=parser.bells_map(idx), subtitle="Физтех · Программная инженерия")
"""
import io
import math
import os
import threading

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:  # бот переживёт и без картинок
    _HAS_PIL = False

BORDO = (109, 31, 44)
GOLD = (197, 162, 83)
GOLD_LIGHT = (232, 207, 143)
GREEN = (28, 124, 58)
BROWN = (181, 101, 29)

THEMES = {
    "day": {
        "BG": (255, 255, 255),
        "CARD": (250, 247, 241),
        "LINE": (232, 226, 214),
        "INK": (31, 27, 26),
        "MUT": (119, 119, 119),
        "NUM": BORDO,          # номер пары
        "DAYNAME": BORDO,      # заголовок дня
        "HEAD": BORDO,         # шапка
        "STARS": False,
    },
    "night": {
        "BG": (10, 15, 36),
        "CARD": (26, 33, 64),
        "LINE": (48, 60, 105),
        "INK": (236, 239, 252),
        "MUT": (163, 171, 208),
        "NUM": GOLD_LIGHT,
        "DAYNAME": GOLD_LIGHT,
        "HEAD": (58, 16, 26),
        "STARS": True,
    },
}
THEME_NAMES = {"day": "день ☀️", "night": "ночь 🌙"}

W = 1000
MARGIN = 44


def _font_path(bold=False):
    if os.name == "nt":
        return (r"C:\Windows\Fonts\arialbd.ttf" if bold
                else r"C:\Windows\Fonts\arial.ttf")
    return ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


class _Fonts:
    def __init__(self):
        if not _HAS_PIL:
            raise RuntimeError("Нет Pillow: pip install Pillow")
        bp, rp = _font_path(True), _font_path(False)
        try:
            self.title = ImageFont.truetype(bp if os.path.exists(bp) else rp, 48)
            self.sub = ImageFont.truetype(rp, 27)
            self.day = ImageFont.truetype(bp, 36)
            self.num = ImageFont.truetype(bp, 46)
            self.time = ImageFont.truetype(rp, 23)
            self.subj = ImageFont.truetype(bp, 31)
            self.meta = ImageFont.truetype(rp, 25)
            self.tag = ImageFont.truetype(bp, 22)
            self.foot = ImageFont.truetype(rp, 22)
        except OSError:
            # запасной встроенный шрифт (без кириллицы, но не падаем)
            self.title = self.sub = self.day = self.num = self.time = \
                self.subj = self.meta = self.tag = self.foot = ImageFont.load_default()


_FONTS = None
_FONTS_LOCK = threading.Lock()


def _fonts():
    global _FONTS
    # бот многопоточный (polling + рассылка): инициализируем шрифты один раз под lock
    if _FONTS is None:
        with _FONTS_LOCK:
            if _FONTS is None:
                _FONTS = _Fonts()
    return _FONTS


def _measure():
    return ImageDraw.Draw(Image.new("RGB", (10, 10)))


def _wrap(draw, text, font, max_w, first_max=None):
    """Разбить текст на строки по ширине. Возвращает [str].

    first_max — лимит первой строки (там справа висят теги).
    """
    words = str(text).split()
    if not words:
        return [""]
    # режем слишком длинные single-слова по буквам заранее
    cut = []
    for w_ in words:
        lim = first_max if not cut and first_max else max_w
        while draw.textlength(w_, font=font) > lim and len(w_) > 1:
            k = len(w_)
            while k > 1 and draw.textlength(w_[:k], font=font) > lim:
                k -= 1
            cut.append(w_[:k])
            w_ = w_[k:]
            lim = max_w
        cut.append(w_)
    lines_out, cur, first = [], "", True
    for w_ in cut:
        lim = (first_max if first and first_max else max_w)
        trial = (cur + " " + w_).strip()
        if draw.textlength(trial, font=font) <= lim or not cur:
            cur = trial
        else:
            lines_out.append(cur)
            cur, first = w_, False
    if cur:
        lines_out.append(cur)
    return lines_out or [""]


def _fit(draw, text, font, max_w, tail="…"):
    text = str(text)
    if draw.textlength(text, font=font) <= max_w:
        return text
    while len(text) > 1 and draw.textlength(text + tail, font=font) > max_w:
        text = text[:-1]
    return text + tail if text else text


def _lesson_blocks(draw, lessons, bells, f, max_w):
    """Замер карточек: [{'h': int, 'subj_lines': [...], 'meta': str, ...}]."""
    blocks = []
    for r in lessons:
        n = r.get("пара")
        t = ""
        if n in bells and any(bells[n]):
            t = f"{bells[n][0]}–{bells[n][1]}"
        subj = (r.get("предмет") or "").strip() or "—"
        kind = (r.get("вид") or "").strip()
        tags = []
        par = (r.get("чётность") or "").strip()
        if par == "чёт":
            tags.append(("чёт", GREEN))
        elif par == "нечёт":
            tags.append(("нечет", BROWN))
        if r.get("подгруппа") in (1, 2):
            tags.append((f"п/г {r.get('подгруппа')}", BORDO))
        tags_w = sum(draw.textlength(t, font=f.tag) + 28 + 10 for t, _c in tags)
        first_max = max_w - (tags_w + 16 if tags else 0)
        subj_lines = _wrap(draw, subj, f.subj, max_w, first_max)
        meta = ", ".join(x for x in
                         [", ".join(r.get("преподаватели") or []),
                          ", ".join(x for x in (r.get("аудитория"), r.get("корпус")) if x)]
                         if x)
        note = (r.get("примечание") or "").strip()
        if r.get("онлайн"):
            note = ((note + " ") if note else "") + f"онлайн: {r.get('онлайн')}"
        meta_full = meta + (f" — {note}" if note else "")
        if kind:
            meta_full = f"{kind}" + (f" · {meta_full}" if meta_full else "")
        meta_lines = _wrap(draw, meta_full, f.meta, max_w) if meta_full else []
        h = (24 + max(len(subj_lines) * 40 + 8 + len(meta_lines) * 32 + 24, 96))
        blocks.append({"n": n, "t": t, "subj": subj_lines, "meta": meta_lines,
                       "tags": tags, "h": h})
    return blocks


def _tag_w(draw, text, f):
    return draw.textlength(text, font=f.tag) + 28


def _stars(d, w, y0, y1, seed=7, n=150):
    """Россыпь звёзд (детерминированная — картинка стабильна)."""
    import random
    rnd = random.Random(seed)
    for _ in range(n):
        x = rnd.uniform(0, w)
        y = rnd.uniform(y0, y1)
        r = rnd.choice([1, 1, 1, 1.5, 1.5, 2, 2.5])
        b = rnd.randint(150, 255)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(b, b, min(255, b + 10)))


def _constellation(d, w):
    """Мини-герб в правом углу ночной шапки: полумесяц + восьмиконечная звезда."""
    cx, cy, r = w - 150, 66, 44
    # полумесяц: золотой круг минус круг цвета шапки со сдвигом
    head = THEMES["night"]["HEAD"]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GOLD_LIGHT)
    d.ellipse([cx - r * 0.25, cy - r * 0.72, cx + r * 1.19, cy + r * 0.72], fill=head)
    # восьмиконечная звезда
    sx, sy, ro, ri = cx - 2 * r - 26, cy - 6, 20, 8
    pts = []
    for i in range(16):
        rr = ro if i % 2 == 0 else ri
        a = math.pi / 8 * i - math.pi / 2
        pts += [sx + rr * math.cos(a), sy + rr * math.sin(a)]
    d.polygon(pts, fill=(255, 255, 255), outline=GOLD_LIGHT)


def render(title, subtitle, days, bells, theme="day"):
    """Общая отрисовка.

    days: [(day_name, lessons_rows, parity_label_or_None)].
    theme: 'day' | 'night' (звёздное небо + созвездие).
    Возвращает PNG как bytes.
    """
    T = THEMES.get(theme) or THEMES["day"]
    night = bool(T["STARS"])
    reserve = 280 if night else 0  # справа в шапке — созвездие
    f = _fonts()
    draw = _measure()
    right_w = W - MARGIN * 2 - 190  # правая колонка карточки
    measured = []
    for day_name, lessons, _par in days:
        measured.append((day_name, _lesson_blocks(draw, lessons, bells, f, right_w)))

    # высота
    h = 40 + 96 + 40 + 6  # отступ + шапка + отступ + золотая полоса
    for day_name, blocks in measured:
        if len(days) > 1:
            h += 20 + 52  # заголовок дня
        for b in blocks:
            h += b["h"] + 16
        h += 8
    h += 40 + 30  # подвал

    img = Image.new("RGB", (W, h), T["BG"])
    d = ImageDraw.Draw(img)
    y = 0
    # шапка
    d.rectangle([0, 0, W, 136], fill=T["HEAD"])
    if night:
        _stars(d, W, 0, 136, seed=21, n=60)
        _constellation(d, W)
    d.text((MARGIN, 26), _fit(d, title, f.title, W - MARGIN * 2 - reserve),
           font=f.title, fill=(255, 255, 255))
    if subtitle:
        d.text((MARGIN, 88), _fit(d, subtitle, f.sub, W - MARGIN * 2 - reserve),
               font=f.sub, fill=GOLD_LIGHT)
    d.rectangle([0, 136, W, 142], fill=GOLD)
    y = 142 + 28
    if night:
        _stars(d, W, y, h, seed=7, n=max(60, h // 12))

    for day_name, blocks in measured:
        if len(days) > 1:
            d.text((MARGIN, y), day_name, font=f.day, fill=T["DAYNAME"])
            tw = d.textlength(day_name, font=f.day)
            d.rectangle([MARGIN, y + 46, MARGIN + max(tw, 60), y + 49], fill=GOLD)
            y += 62
        if not blocks:
            d.text((MARGIN, y + 6), "Пар нет 🎉", font=f.meta, fill=T["MUT"])
            y += 44
        for b in blocks:
            x0, y0 = MARGIN, y
            x1, y1 = W - MARGIN, y + b["h"]
            d.rounded_rectangle([x0, y0, x1, y1], radius=26,
                                fill=T["CARD"], outline=T["LINE"], width=2)
            # левая колонка: номер пары + время
            d.text((x0 + 30, y0 + 18), str(b["n"]), font=f.num, fill=T["NUM"])
            if b["t"]:
                d.text((x0 + 30, y0 + 74), b["t"], font=f.time, fill=T["MUT"])
            # правая колонка
            tx = x0 + 190
            ty = y0 + 20
            for line in b["subj"]:
                d.text((tx, ty), line, font=f.subj, fill=T["INK"])
                ty += 40
            ty += 6
            for line in b["meta"]:
                d.text((tx, ty), line, font=f.meta, fill=T["MUT"])
                ty += 32
            # теги справа сверху
            tag_x = x1 - 24
            for text, color in b["tags"]:
                tw_ = _tag_w(d, text, f)
                tag_x -= tw_
                d.rounded_rectangle([tag_x, y0 + 18, tag_x + tw_, y0 + 52],
                                    radius=17, fill=color)
                d.text((tag_x + 14, y0 + 23), text, font=f.tag, fill=(255, 255, 255))
                tag_x -= 10
            y = y1 + 16
        y += 8

    d.text((MARGIN, h - 52), "Расписание КФУ · cfuv.ru/raspisanie",
           font=f.foot, fill=T["MUT"])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def render_day(code, day_name, parity, lessons, bells, subtitle="", theme="day"):
    title = f"{code} · {day_name}"
    sub = (subtitle + (f" · {parity} неделя" if parity in ("чёт", "нечёт") else "")).strip(" ·")
    return render(title, sub, [(day_name, lessons, parity)], bells, theme)


def render_week(code, day_lessons, bells, subtitle="", parity="", theme="day"):
    """day_lessons: [(day_name, rows)]."""
    sub = (subtitle + (f" · {parity} неделя" if parity in ("чёт", "нечёт") else "")).strip(" ·")
    return render(f"{code} · неделя", sub, [(d, r, parity) for d, r in day_lessons],
                  bells, theme)

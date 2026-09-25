# -*- coding: utf-8 -*-
"""Telegram-бот расписания КФУ. Только стандартная библиотека.

Запуск:
    set KFU_BOT_TOKEN=123:ABC   (Windows)
    python bot.py
Токен взять у @BotFather. Зависимостей нет.
"""
import datetime
import hashlib
import io
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser  # noqa: E402

MSK = datetime.timezone(datetime.timedelta(hours=3), "MSK")
DIGEST_HOUR, DIGEST_MIN = 7, 0  # утренняя рассылка — 07:00 по Москве/Крыму

TOKEN = os.environ.get("KFU_BOT_TOKEN", "").strip()
if not TOKEN:
    # Запасной вариант для новичков: файл token.txt рядом с bot.py
    # (только токен, без лишнего текста). В git его коммитить нельзя.
    # utf-8-sig: Блокнот/PowerShell пишут UTF-8 с BOM, его надо отрезать.
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.txt"),
                  encoding="utf-8-sig") as f:
            TOKEN = f.read().strip().strip("\ufeff")
    except OSError:
        pass
API = f"https://api.telegram.org/bot{TOKEN}/" if TOKEN else ""
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot_state.json")

HELP = (
    "Расписание КФУ им. Вернадского 📚\n\n"
    "Выбери факультет кнопками ниже или просто пришли код группы, например:\n"
    "ПИ-б-о-241\n\n"
    "Фамилию преподавателя (например, Парменов) — тоже можно просто прислать.\n\n"
    "Команды:\n"
    "/my — моя группа на сегодня ⭐\n"
    "/now — что идёт сейчас и следующая пара 🟢\n"
    "/today — пары сегодня\n"
    "/tomorrow — пары завтра\n"
    "/week — вся неделя\n"
    "/even — чётная неделя\n"
    "/odd — нечётная неделя\n"
    "/sess — сессия и экзамены 📝\n"
    "/pic — сегодня картинкой 🖼\n"
    "/picweek — неделя картинкой 🖼\n"
    "/ics — файл календаря для телефона 📅\n"
    "/teacher ФАМИЛИЯ — расписание преподавателя 👤\n"
    "/theme — переключить день ☀️ / ночь 🌙\n"
    "/notify on|off — слать расписание утром в 07:00 ⏰\n"
    "/changes on|off — сообщать об изменениях расписания 🔄\n"
    "/group КОД — сменить группу\n"
    "/help — эта подсказка\n\n"
    "Подгруппа выбирается кнопками «п/г» под расписанием."
)


def tg(method, params=None, timeout=40):
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(
        API + method, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read().decode("utf-8"))
    if not res.get("ok"):
        raise RuntimeError(f"Telegram API: {res}")
    return res["result"]


def send(chat_id, text, reply_markup=None):
    chunks = parser.split_long(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk}
        # клавиатуру цепляем только к последнему сообщению, иначе она дублируется
        if reply_markup and i == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        tg("sendMessage", payload, timeout=20)


def send_photo(chat_id, png, caption=None, reply_markup=None, timeout=30):
    return _send_file(chat_id, "photo", "rasp.png", png, "image/png",
                      caption, reply_markup, timeout)


def send_document(chat_id, filename, data, caption=None, reply_markup=None,
                  ctype="text/calendar", timeout=30):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return _send_file(chat_id, "document", filename, data, ctype,
                      caption, reply_markup, timeout)


def _send_file(chat_id, field_name, filename, data, ctype, caption=None,
               reply_markup=None, timeout=30):
    """Отправка файла через multipart (всё на стандартной библиотеке)."""
    boundary = "KfuImgBoundary7xQ2v9"
    buf = io.BytesIO()

    def field(name, value):
        buf.write(f"--{boundary}\r\n".encode("ascii"))
        buf.write(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        buf.write(f"{value}\r\n".encode("utf-8"))

    field("chat_id", chat_id)
    if caption:
        field("caption", caption[:1000])
    if reply_markup is not None:
        field("reply_markup", json.dumps(reply_markup, ensure_ascii=False))
    buf.write(f"--{boundary}\r\n".encode("ascii"))
    buf.write(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode("ascii"))
    buf.write(f"Content-Type: {ctype}\r\n\r\n".encode("ascii"))
    buf.write(data)
    buf.write(f"\r\n--{boundary}--\r\n".encode("ascii"))

    method = "sendPhoto" if field_name == "photo" else "sendDocument"
    req = urllib.request.Request(
        API + method, data=buf.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.loads(r.read().decode("utf-8"))
    if not res.get("ok"):
        raise RuntimeError(f"Telegram API: {res}")
    return res["result"]


def kb(rows):
    return {"inline_keyboard": rows}


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


STATE_LOCK = threading.Lock()


def user_prefs(state, user_id):
    """Памятка пользователя: group / theme(day|night) / notify / changes / sub(0|1|2)."""
    u = state.get(str(user_id)) or {}
    theme = u.get("theme") if u.get("theme") in ("day", "night") else "day"
    sub = u.get("sub") if u.get("sub") in (1, 2) else 0
    return {"group": u.get("group"), "theme": theme, "notify": bool(u.get("notify")),
            "changes": bool(u.get("changes")), "sub": sub}


def set_user(state, user_id, **kw):
    with STATE_LOCK:
        u = dict(state.get(str(user_id)) or {})
        u.update(kw)
        state[str(user_id)] = u
        save_state(state)


def short(text, n=40):
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------- Кэш выбора тёзок: ФИО целиком не влезет в лимит callback 64 байта ----------

_TEACHER_CACHE = {}
_TEACHER_CACHE_LOCK = threading.Lock()


def teacher_token(query, name):
    """Короткий id для кнопки-тёзки: полное ФИО храним в памяти, в callback — токен."""
    tok = hashlib.sha1(f"{query}|{name}".encode("utf-8")).hexdigest()[:12]
    with _TEACHER_CACHE_LOCK:
        _TEACHER_CACHE[tok] = (query, name)
        while len(_TEACHER_CACHE) > 200:  # не расти без bounds
            _TEACHER_CACHE.pop(next(iter(_TEACHER_CACHE)))
    return tok


def teacher_lookup(tok):
    with _TEACHER_CACHE_LOCK:
        return _TEACHER_CACHE.get(tok)


# ---------- Экраны выбора (индексы вместо длинных названий: лимит callback 64 байта) ----------

def show_subs(chat_id, idx):
    subs = parser.subdivisions(idx)
    rows = [[{"text": short(s, 45), "callback_data": f"s:{i}"}] for i, s in enumerate(subs)]
    send(chat_id, "Выбери институт / факультет 👇", kb(rows))


def show_dirs(chat_id, idx, si):
    subs = parser.subdivisions(idx)
    sub = subs[si]
    dirs = parser.directions(sub, idx)
    rows = [[{"text": short(d, 45), "callback_data": f"d:{si}:{di}"}] for di, d in enumerate(dirs)]
    rows.append([{"text": "⬅ Назад", "callback_data": "home"}])
    send(chat_id, f"{sub}\nВыбери направление 👇", kb(rows))


def show_courses(chat_id, idx, si, di):
    subs = parser.subdivisions(idx)
    sub = subs[si]
    dirs = parser.directions(sub, idx)
    direction = dirs[di]
    crs = parser.courses(sub, direction, idx)
    rows = [[{"text": f"{c} курс", "callback_data": f"c:{si}:{di}:{c}"}] for c in crs]
    rows.append([{"text": "⬅ Назад", "callback_data": f"s:{si}"}])
    send(chat_id, f"{sub}\n{direction}\nВыбери курс 👇", kb(rows))


def show_groups(chat_id, idx, si, di, course):
    subs = parser.subdivisions(idx)
    sub = subs[si]
    dirs = parser.directions(sub, idx)
    direction = dirs[di]
    groups = parser.groups_of(sub, direction, course, idx)
    rows = [[{"text": g, "callback_data": f"g:{g}"}] for g in groups]
    rows.append([{"text": "⬅ Назад", "callback_data": f"d:{si}:{di}"}])
    send(chat_id, f"{sub}\n{direction}, {course} курс\nВыбери группу 👇", kb(rows))


def theme_btn(theme):
    return {"text": "☀️ День" if theme == "night" else "🌙 Ночь", }


def sub_row(code, sub, ret):
    """Кнопки подгруппы. ret — callback_data вида, куда вернуться (без потери экрана)."""
    def b(n, label):
        t = f"{label} ✓" if sub == n else label
        return {"text": t, "callback_data": f"sv:{code}:{n}:{ret}"}
    return [b(0, "п/г: все"), b(1, "1"), b(2, "2")]


def group_menu(group_code, theme="day", sub=0):
    rows = [
        [{"text": "📅 Сегодня", "callback_data": f"t:{group_code}"},
         {"text": "➡ Завтра", "callback_data": f"w:{group_code}"}],
        [{"text": "🗓 Неделя", "callback_data": f"a:{group_code}"},
         {"text": "🟢 Сейчас", "callback_data": f"y:{group_code}"}],
        [{"text": "Чётная", "callback_data": f"e:{group_code}"},
         {"text": "Нечётная", "callback_data": f"o:{group_code}"}],
        [{"text": "🖼 Сегодня картинкой", "callback_data": f"i:{group_code}"},
         {"text": "🖼 Неделя картинкой", "callback_data": f"j:{group_code}"}],
        sub_row(group_code, sub, f"a:{group_code}"),
        [{"text": "📝 Сессия", "callback_data": f"x:{group_code}"},
         {"text": "📅 .ics", "callback_data": f"k:{group_code}"}],
        [{**theme_btn(theme), "callback_data": f"m:{group_code}"},
         {"text": "⏰ Утром", "callback_data": f"u:{group_code}"}],
        [{"text": "⬅ Сменить группу", "callback_data": "home"}],
    ]
    return kb(rows)


# чётность в callback — латиницей (лимит 64 байта на callback_data)
P2C = {"a": "обе", "c": "чёт", "n": "нечёт"}
C2P = {v: k for k, v in P2C.items()}


def _subtitle(code, idx):
    info = parser.group_info(code, idx) or {}
    return " · ".join(x for x in (info.get("sub"), info.get("dir")) if x)


def _need_images():
    try:
        import schedule_image  # noqa: F401
        return None
    except ImportError:
        return ("Картинки недоступны: на сервере нет Pillow "
                "(pip install Pillow). Показываю текстом 👇")


def day_menu(code, day, pc, theme="day", sub=0):
    prev_d = day - 1 if day > 1 else 7
    next_d = day + 1 if day < 7 else 1
    return kb([
        [{"text": "◀", "callback_data": f"p:{code}:{prev_d}:{pc}"},
         {"text": "🖼 Картинка", "callback_data": f"q:{code}:{day}:{pc}"},
         {"text": "▶", "callback_data": f"p:{code}:{next_d}:{pc}"}],
        [{"text": "📅 Сегодня", "callback_data": f"t:{code}"},
         {"text": "🗓 Неделя", "callback_data": f"a:{code}"}],
        [{"text": "🖼 Неделя картинкой", "callback_data": f"j:{code}"}],
        sub_row(code, sub, f"p:{code}:{day}:{pc}"),
        [{**theme_btn(theme), "callback_data": f"m:{code}"}],
        [{"text": "⬅ Сменить группу", "callback_data": "home"}],
    ])


def photo_day_menu(code, day, pc, theme="day", sub=0):
    prev_d = day - 1 if day > 1 else 7
    next_d = day + 1 if day < 7 else 1
    return kb([
        [{"text": "◀", "callback_data": f"q:{code}:{prev_d}:{pc}"},
         {"text": "📝 Текстом", "callback_data": f"p:{code}:{day}:{pc}"},
         {"text": "▶", "callback_data": f"q:{code}:{next_d}:{pc}"}],
        [{"text": "🗓 Неделя картинкой", "callback_data": f"j:{code}"}],
        sub_row(code, sub, f"q:{code}:{day}:{pc}"),
        [{**theme_btn(theme), "callback_data": f"m:{code}"}],
        [{"text": "⬅ Сменить группу", "callback_data": "home"}],
    ])


def show_week(chat_id, code, parity="обе", theme="day", sub=0):
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    text = parser.format_week(g, bells, parity, sub)
    info = parser.group_info(code, idx)
    head = f"{code}"
    if info:
        head += f" · {info.get('sub', '')}\n{info.get('dir', '')}"
    send(chat_id, head + "\n\n" + text, group_menu(code, theme, sub))


def show_day(chat_id, code, day, parity="обе", theme="day", sub=0):
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    send(chat_id, parser.format_day(g, day, bells, parity, sub),
         day_menu(code, day, C2P.get(parity, "a"), theme, sub))


def show_now(chat_id, code, theme="day", sub=0, now=None):
    """Что идёт сейчас + следующая пара (время — московское)."""
    now = now or datetime.datetime.now(MSK)
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    parity = current_parity(idx)
    day = (now.weekday() % 7) + 1
    mins = now.hour * 60 + now.minute

    def bounds(lesson):
        b = bells.get(lesson.get("пара"), ("", ""))
        try:
            s = int(b[0][:2]) * 60 + int(b[0][3:5])
            e = int(b[1][:2]) * 60 + int(b[1][3:5])
            return s, e
        except (ValueError, IndexError, TypeError):
            return None

    lessons = [r for r in parser.lessons_of_day(g, day, parity, sub)
               if bounds(r)]
    cur = nxt = None
    for r in sorted(lessons, key=lambda x: bounds(x)[0]):
        s, e = bounds(r)
        if s <= mins <= e:
            cur = (r, e - mins)
        elif s > mins and nxt is None:
            nxt = (r, s - mins)
    head = f"🟢 Сейчас · {parser.DAY_NAMES.get(day)} · {code}"
    if sub in (1, 2):
        head += f" · подгруппа {sub}"
    if cur:
        r, left = cur
        text = head + f"\nИдёт {r.get('пара')}-я пара, до конца ~{left} мин:\n" \
            + parser.format_lesson(r, bells)
    else:
        text = head + "\nСейчас пар нет 🎉"
    if nxt:
        r, soon = nxt
        text += f"\n\nСледующая через ~{soon} мин:\n" + parser.format_lesson(r, bells)
    elif not cur:
        text += "\n\nНа сегодня пар больше нет."
    send(chat_id, text, group_menu(code, theme, sub))


def show_session(chat_id, code, theme="day", sub=0):
    idx = parser.get_index()
    g = parser.get_group(code)
    send(chat_id, parser.format_session(g), group_menu(code, theme, sub))


def send_ics(chat_id, code, theme="day", sub=0):
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    body = parser.to_ics(code, g.get("занятия", []), bells, idx.get("weeks", {}), sub)
    n = body.count("BEGIN:VEVENT")
    cap = f"📅 {code} — календарь ({n} пар)"
    if sub in (1, 2):
        cap += f", подгруппа {sub}"
    cap += ". Открой файл — телефон предложит добавить в календарь."
    send_document(chat_id, f"{code}.ics", body, cap, group_menu(code, theme, sub))


def send_day_image(chat_id, code, day, parity="обе", theme="day", sub=0):
    noimg = _need_images()
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    pc = C2P.get(parity, "a")
    menu = photo_day_menu(code, day, pc, theme, sub)
    if noimg:
        send(chat_id, noimg)
        send(chat_id, parser.format_day(g, day, bells, parity, sub),
             day_menu(code, day, pc, theme, sub))
        return
    import schedule_image
    png = schedule_image.render_day(
        code, parser.DAY_NAMES.get(day, f"День {day}"), parity,
        parser.lessons_of_day(g, day, parity, sub), bells, _subtitle(code, idx),
        theme=theme)
    send_photo(chat_id, png, f"{code} · {parser.DAY_NAMES.get(day, '')}", menu)


def send_week_image(chat_id, code, parity="обе", theme="day", sub=0):
    noimg = _need_images()
    idx = parser.get_index()
    bells = parser.bells_map(idx)
    g = parser.get_group(code)
    if noimg:
        send(chat_id, noimg)
        send(chat_id, parser.format_week(g, bells, parity, sub),
             group_menu(code, theme, sub))
        return
    import schedule_image
    days = [(parser.DAY_NAMES[d], parser.lessons_of_day(g, d, parity, sub))
            for d in range(1, 7)]
    days = [(n, r) for n, r in days if r]
    if not days:
        send(chat_id, f"{code}: занятий нет", group_menu(code, theme, sub))
        return
    png = schedule_image.render_week(code, days, bells, _subtitle(code, idx), parity,
                                     theme=theme)
    send_photo(chat_id, png, f"{code} · неделя", group_menu(code, theme, sub))


def today_tomorrow(now=None):
    # Всё время в боте — московское (MSK): иначе на сервере в другом часовом
    # поясе /today и кнопки покажут не тот день, что /now и /my.
    now = now or datetime.datetime.now(MSK)
    today = (now.weekday() % 7) + 1  # Пн=1..Вс=7
    tomorrow = today + 1 if today < 7 else 1
    return today, tomorrow


def msk_today():
    return today_tomorrow(datetime.datetime.now(MSK))[0]


def current_parity(idx):
    try:
        return idx.get("now", {}).get("parity") or "обе"
    except Exception:
        return "обе"


def show_teacher(chat_id, query, idx):
    """Расписание преподавателя. Несколько тёзок — кнопками на выбор."""
    bells = parser.bells_map(idx)
    try:
        rows = parser.find("teacher", query)
    except (ValueError, RuntimeError) as e:
        send(chat_id, str(e))
        return
    if not rows:
        send(chat_id, f"Преподавателя «{query}» не нашёл 😕 "
                      f"Попробуй только фамилию: /teacher Парменов")
        return
    names = sorted({", ".join(r.get("преподаватели") or []) for r in rows} - {""})
    if len(names) > 1:
        shortlist = names[:8]
        kb_rows = [[{"text": n, "callback_data": f"h:{teacher_token(query, n)}"}]
                   for n in shortlist]
        send(chat_id, f"Нашёл {len(names)} преподавателей, уточни 👇"
             + ("" if len(names) <= 8 else f" (первые {len(shortlist)})"),
             kb(kb_rows))
        return
    name = names[0] if names else query
    mine = [r for r in rows
            if name in ", ".join(r.get("преподаватели") or [])] or rows
    if len(mine) > 80:
        extra = f"\n\n…и ещё {len(mine) - 80} пар — сузь запрос"
        mine = mine[:80]
    else:
        extra = ""
    text = parser.format_found(mine, bells, f"👤 {name}", current_parity(idx)) + extra
    send(chat_id, text, kb([[ {"text": "⬅ К группам", "callback_data": "home"} ]]))


def handle_text(chat_id, user_id, text, state, idx):
    text = (text or "").strip()
    if not text:
        return
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        prefs = user_prefs(state, user_id)
        code, theme, sub = prefs["group"], prefs["theme"], prefs["sub"]
        if cmd == "/start":
            send(chat_id, HELP)
            show_subs(chat_id, idx)
        elif cmd == "/help":
            send(chat_id, HELP)
        elif cmd == "/my":
            if not code:
                send(chat_id, "У тебя ещё нет сохранённой группы — выбери 👇")
                show_subs(chat_id, idx)
            else:
                show_day(chat_id, code, msk_today(), current_parity(idx), theme, sub)
        elif cmd == "/theme":
            new = "night" if theme == "day" else "day"
            set_user(state, user_id, theme=new)
            send(chat_id, "🌙 Ночная тема со звёздами" if new == "night"
                 else "☀️ Дневная тема")
            if code:
                show_week(chat_id, code, current_parity(idx), new)
        elif cmd == "/notify":
            a = arg.strip().lower()
            if a in ("on", "вкл", "да", "1"):
                if not code:
                    send(chat_id, "Сначала выбери группу 👇")
                    show_subs(chat_id, idx)
                else:
                    set_user(state, user_id, notify=True)
                    send(chat_id, f"⏰ Включил: каждое утро в {DIGEST_HOUR:02d}:{DIGEST_MIN:02d} "
                                  f"по Москве буду слать пары группы {code} на сегодня.")
            elif a in ("off", "выкл", "нет", "0"):
                set_user(state, user_id, notify=False)
                send(chat_id, "⏰ Утреннюю рассылку выключил.")
            else:
                on = "включена ✅" if prefs["notify"] else "выключена ❌"
                send(chat_id, f"⏰ Рассылка {on} (группа: {code or 'не выбрана'}).\n"
                              f"/notify on — включить, /notify off — выключить.")
        elif cmd == "/teacher":
            if not arg.strip():
                send(chat_id, "Пришли фамилию: /teacher Парменов")
            else:
                show_teacher(chat_id, arg.strip(), idx)
        elif cmd == "/group":
            if arg:
                pick_group(chat_id, user_id, arg.strip(), state, idx)
            else:
                show_subs(chat_id, idx)
        elif cmd in ("/today", "/tomorrow", "/week", "/even", "/odd", "/pic", "/picweek",
                     "/now", "/sess", "/ics"):
            if not code:
                send(chat_id, "Сначала выбери группу 👇")
                show_subs(chat_id, idx)
                return
            try:
                parity = current_parity(idx)
                if cmd == "/today":
                    d, _ = today_tomorrow()
                    show_day(chat_id, code, d, parity, theme, sub)
                elif cmd == "/tomorrow":
                    _, d = today_tomorrow()
                    show_day(chat_id, code, d, parity, theme, sub)
                elif cmd == "/week":
                    show_week(chat_id, code, parity, theme, sub)
                elif cmd == "/even":
                    show_week(chat_id, code, "чёт", theme, sub)
                elif cmd == "/odd":
                    show_week(chat_id, code, "нечёт", theme, sub)
                elif cmd == "/pic":
                    d, _ = today_tomorrow()
                    send_day_image(chat_id, code, d, parity, theme, sub)
                elif cmd == "/picweek":
                    send_week_image(chat_id, code, parity, theme, sub)
                elif cmd == "/now":
                    show_now(chat_id, code, theme, sub)
                elif cmd == "/sess":
                    show_session(chat_id, code, theme, sub)
                elif cmd == "/ics":
                    send_ics(chat_id, code, theme, sub)
            except (LookupError, RuntimeError) as e:
                # cfuv.ru лёг или группу удалили — отвечаем человеку, а не молчим
                send(chat_id, f"Не получилось загрузить {code} 😕\n{e}\nПопробуй позже.")
        elif cmd == "/changes":
            a = arg.strip().lower()
            if a in ("on", "вкл", "да", "1"):
                if not code:
                    send(chat_id, "Сначала выбери группу 👇")
                    show_subs(chat_id, idx)
                else:
                    set_user(state, user_id, changes=True)
                    send(chat_id, f"🔄 Включил слежку за {code}: если расписание "
                                  f"на сайте поменяется — напишу, что именно.")
            elif a in ("off", "выкл", "нет", "0"):
                set_user(state, user_id, changes=False)
                send(chat_id, "🔄 Слежку за изменениями выключил.")
            else:
                on = "включена ✅" if prefs["changes"] else "выключена ❌"
                send(chat_id, f"🔄 Слежка {on} (группа: {code or 'не выбрана'}).\n"
                              f"/changes on — включить, /changes off — выключить.")
        else:
            send(chat_id, "Не знаю такую команду. " + HELP)
        return
    # без цифр — похоже на фамилию преподавателя, иначе код группы
    if any(ch.isdigit() for ch in text):
        pick_group(chat_id, user_id, text, state, idx)
    else:
        try:
            rows = parser.find("teacher", text)
        except (ValueError, RuntimeError):
            rows = []
        if rows:
            show_teacher(chat_id, text, idx)
        else:
            pick_group(chat_id, user_id, text, state, idx)


def pick_group(chat_id, user_id, query, state, idx):
    found = parser.find_groups(query, idx)
    exact = [c for c in found if c.lower() == query.lower()]
    if exact:
        code = exact[0]
    elif len(found) == 1:
        code = found[0]
    elif found:
        rows = [[{"text": c, "callback_data": f"g:{c}"}] for c in found[:10]]
        send(chat_id, f"Нашёл {len(found)} групп, выбери 👇", kb(rows))
        return
    else:
        send(chat_id, f"Группу «{query}» не нашёл 😕 Проверь код, например ПИ-б-о-241, или выбери факультет кнопками:")
        show_subs(chat_id, idx)
        return
    set_user(state, user_id, group=code)
    try:
        prefs = user_prefs(state, user_id)
        show_week(chat_id, code, current_parity(idx), prefs["theme"], prefs["sub"])
    except LookupError as e:
        send(chat_id, str(e))
    except RuntimeError as e:
        send(chat_id, str(e))


def handle_callback(chat_id, user_id, data, state, idx):
    if data == "home":
        show_subs(chat_id, idx)
        return
    kind, _, rest = data.partition(":")
    prefs = user_prefs(state, user_id)
    theme, sub = prefs["theme"], prefs["sub"]
    try:
        if kind == "s":
            show_dirs(chat_id, idx, int(rest))
        elif kind == "d":
            si, di = rest.split(":")
            show_courses(chat_id, idx, int(si), int(di))
        elif kind == "c":
            si, di, course = rest.split(":")
            show_groups(chat_id, idx, int(si), int(di), course)
        elif kind == "g":
            set_user(state, user_id, group=rest)
            show_week(chat_id, rest, current_parity(idx), theme, sub)
        elif kind == "t":
            d, _ = today_tomorrow()
            show_day(chat_id, rest, d, current_parity(idx), theme, sub)
        elif kind == "w":
            _, d = today_tomorrow()
            show_day(chat_id, rest, d, current_parity(idx), theme, sub)
        elif kind == "a":
            show_week(chat_id, rest, current_parity(idx), theme, sub)
        elif kind == "e":
            show_week(chat_id, rest, "чёт", theme, sub)
        elif kind == "o":
            show_week(chat_id, rest, "нечёт", theme, sub)
        elif kind == "i":
            d, _ = today_tomorrow()
            send_day_image(chat_id, rest, d, current_parity(idx), theme, sub)
        elif kind == "j":
            send_week_image(chat_id, rest, current_parity(idx), theme, sub)
        elif kind == "y":
            show_now(chat_id, rest, theme, sub)
        elif kind == "x":
            show_session(chat_id, rest, theme, sub)
        elif kind == "k":
            send_ics(chat_id, rest, theme, sub)
        elif kind == "v":
            code, n = rest.rsplit(":", 1)
            set_user(state, user_id, sub=int(n))
            show_week(chat_id, code, current_parity(idx), theme, int(n))
        elif kind == "sv":
            # смена подгруппы с возвратом на тот же экран (день/картинка/неделя)
            code, n, ret = rest.split(":", 2)
            set_user(state, user_id, sub=int(n))
            handle_callback(chat_id, user_id, ret, state, idx)
        elif kind == "m":
            new = "night" if theme == "day" else "day"
            set_user(state, user_id, theme=new)
            send(chat_id, "🌙 Ночная тема со звёздами" if new == "night"
                 else "☀️ Дневная тема")
            show_week(chat_id, rest, current_parity(idx), new, sub)
        elif kind == "u":
            cur = user_prefs(state, user_id)
            if cur["notify"]:
                set_user(state, user_id, notify=False)
                send(chat_id, "⏰ Утреннюю рассылку выключил.")
            else:
                set_user(state, user_id, notify=True)
                send(chat_id, f"⏰ Включил: каждое утро в {DIGEST_HOUR:02d}:{DIGEST_MIN:02d} "
                              f"по Москве буду слать пары группы {rest} на сегодня.")
        elif kind == "h":
            hit = teacher_lookup(rest)
            if hit is None:
                send(chat_id, "Кнопка устарела (бот перезапускался) — пришли фамилию ещё раз 👇")
            else:
                show_teacher(chat_id, hit[1], idx)
        elif kind in ("p", "q"):
            code, day, pc = rest.split(":")
            day, parity = int(day), P2C.get(pc, "обе")
            if kind == "p":
                idx = parser.get_index()
                bells = parser.bells_map(idx)
                g = parser.get_group(code)
                send(chat_id, parser.format_day(g, day, bells, parity, sub),
                     day_menu(code, day, pc, theme, sub))
            else:
                send_day_image(chat_id, code, day, parity, theme, sub)
    except (LookupError, RuntimeError) as e:
        send(chat_id, str(e))
    except (ValueError, IndexError):
        show_subs(chat_id, idx)


def digest_loop(state):
    """Фоновая утренняя рассылка: в 07:00 МСК шлём пары на сегодня."""
    while True:
        try:
            now = datetime.datetime.now(MSK)
            today = now.strftime("%Y-%m-%d")
            if (now.hour, now.minute) == (DIGEST_HOUR, DIGEST_MIN):
                with STATE_LOCK:
                    sent = state.get("_digest_sent")
                    snapshot = [(uid, dict(u)) for uid, u in state.items()
                                if not str(uid).startswith("_") and isinstance(u, dict)]
                if sent != today:
                    try:
                        idx = parser.get_index()
                        parity = current_parity(idx)
                    except Exception as e:
                        print("digest index:", e)
                        idx, parity = None, "обе"
                    if idx is not None:
                        # одну и ту же группу качаем и рисуем один раз,
                        # а не по разу на пользователя
                        by_code = {}
                        for uid, u in snapshot:
                            if u.get("notify") and u.get("group"):
                                by_code.setdefault(u["group"], []).append(
                                    (uid, u.get("theme", "day"), u.get("sub", 0)))
                        day = msk_today()
                        bells = parser.bells_map(idx)
                        for code, targets in by_code.items():
                            try:
                                g = parser.get_group(code)
                            except Exception as e:
                                print("digest fetch:", code, e)
                                continue
                            noimg = _need_images()
                            png_cache = {}
                            for uid, theme, sub in targets:
                                try:
                                    if noimg:
                                        send(int(uid),
                                             f"⏰ Пары на сегодня · {code}\n\n"
                                             + parser.format_day(g, day, bells, parity, sub))
                                        continue
                                    key = (theme, sub)
                                    if key not in png_cache:
                                        import schedule_image
                                        png_cache[key] = schedule_image.render_day(
                                            code, parser.DAY_NAMES.get(day, ""),
                                            parity, parser.lessons_of_day(g, day, parity, sub),
                                            bells, _subtitle(code, idx), theme=theme)
                                    send_photo(int(uid), png_cache[key],
                                               f"⏰ {code} · пары на сегодня")
                                except Exception as e:
                                    print("digest:", uid, e)
                    with STATE_LOCK:
                        state["_digest_sent"] = today
                        save_state(state)
        except Exception as e:
            print("digest loop:", e)
        time.sleep(30)


def _diff_lines(old_keys, new_keys, bells):
    """Человекочитаемый дифф пар: что добавилось / пропало."""
    old_s, new_s = set(old_keys), set(new_keys)
    lines = []

    def fmt(k, sign):
        day, para = k[0], k[1]
        name = parser.DAY_NAMES.get(day, f"День {day}")
        subj = k[4] or "—"
        extra = []
        if k[3] and k[3] != "обе":
            extra.append(k[3])
        if k[2] in (1, 2):
            extra.append(f"п/г {k[2]}")
        b = bells.get(para, ("", ""))
        when = f"{b[0]}–{b[1]} " if all(b) else ""
        room = k[7] or ""
        return f"{sign} {name}, {para}-я ({when}{subj})" \
            + (f" [{', '.join(extra)}]" if extra else "") \
            + (f" — {room}" if room else "")

    added = sorted(new_s - old_s, key=lambda k: (k[0] or 0, k[1] or 0))
    removed = sorted(old_s - new_s, key=lambda k: (k[0] or 0, k[1] or 0))
    for k in removed[:8]:
        lines.append(fmt(k, "➖"))
    if len(removed) > 8:
        lines.append(f"➖ …и ещё {len(removed) - 8}")
    for k in added[:8]:
        lines.append(fmt(k, "➕"))
    if len(added) > 8:
        lines.append(f"➕ …и ещё {len(added) - 8}")
    return lines


def changes_loop(state, interval=1800):
    """Фоновая слежка: раз в полчаса сверяем расписание с сайтом."""
    while True:
        try:
            with STATE_LOCK:
                codes = sorted({u.get("group") for uid, u in state.items()
                                if not str(uid).startswith("_")
                                and isinstance(u, dict)
                                and u.get("changes") and u.get("group")})
            if codes:
                try:
                    idx = parser.get_index()
                    bells = parser.bells_map(idx)
                except Exception as e:
                    print("changes index:", e)
                    bells = {}
                for code in codes:
                    try:
                        fresh = parser.get_group(code, force=True)
                    except Exception as e:
                        print("changes fetch:", code, e)
                        continue
                    new_keys = sorted((parser.lesson_key(r)
                                       for r in fresh.get("занятия", [])),
                                      key=lambda k: json.dumps(k, ensure_ascii=False,
                                                               default=str))
                    skey = f"_sig_{code}"
                    with STATE_LOCK:
                        old = state.get(skey)
                        state[skey] = new_keys
                        save_state(state)
                    if old is None:
                        continue  # первый замер — baseline, не спамим
                    if old != new_keys:
                        lines = _diff_lines(old, new_keys, bells)
                        if not lines:
                            continue
                        text = f"🔄 Расписание {code} изменилось:\n" + "\n".join(lines)
                        with STATE_LOCK:
                            targets = [uid for uid, u in state.items()
                                       if not str(uid).startswith("_")
                                       and isinstance(u, dict)
                                       and u.get("changes") and u.get("group") == code]
                        for uid in targets:
                            try:
                                send(int(uid), text)
                            except Exception as e:
                                print("changes send:", uid, e)
        except Exception as e:
            print("changes loop:", e)
        time.sleep(interval)


def main():
    if not TOKEN:
        print("Нет токена. Два способа:")
        print("  1) Положи токен от @BotFather в файл token.txt рядом с bot.py (только токен, без лишнего).")
        print("  2) Или задай переменную окружения в ТОМ ЖЕ окне перед запуском:")
        print("     PowerShell:  $env:KFU_BOT_TOKEN='123:ABC'; python bot.py")
        sys.exit(1)
    print("Бот запущен. Остановка: Ctrl+C")
    idx = parser.get_index()
    print(f"Групп в расписании: {len(idx.get('groups', {}))}, подразделений: {len(idx.get('tree', {}))}")
    state = load_state()
    threading.Thread(target=digest_loop, args=(state,), daemon=True).start()
    print(f"Утренняя рассылка: {DIGEST_HOUR:02d}:{DIGEST_MIN:02d} МСК")
    threading.Thread(target=changes_loop, args=(state,), daemon=True).start()
    print("Слежка за изменениями: каждые 30 мин")
    offset = 0
    fails = 0
    while True:
        try:
            updates = tg("getUpdates", {"offset": offset, "timeout": 25}, timeout=35)
            fails = 0
        except Exception as e:
            fails += 1
            print("getUpdates:", e)
            # при дохлом токене/без сети не hammerим API: пауза с ростом до 60 c
            time.sleep(min(5 * fails, 60))
            continue
        for u in updates:
            offset = max(offset, u["update_id"] + 1)
            try:
                if "callback_query" in u:
                    cq = u["callback_query"]
                    tg("answerCallbackQuery", {"callback_query_id": cq["id"]}, timeout=10)
                    chat_id = cq["message"]["chat"]["id"]
                    user_id = cq["from"]["id"]
                    idx = parser.get_index()
                    handle_callback(chat_id, user_id, cq.get("data", ""), state, idx)
                elif "message" in u and "text" in u["message"]:
                    m = u["message"]
                    idx = parser.get_index()
                    handle_text(m["chat"]["id"], m["from"]["id"], m["text"], state, idx)
            except Exception as e:
                print("update error:", e)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Общий парсер расписания КФУ им. Вернадского.

Использует официальный JSON-API сайта (тот же, что дёргает страница
https://cfuv.ru/raspisanie/ из JS), а не HTML-скрейпинг:
    GET https://cfuv.ru/wp-json/cfu/v1/sched/index          — дерево факультет→направление→курс→группы, звонки, недели
    GET https://cfuv.ru/wp-json/cfu/v1/sched/group?code=XX  — занятия группы
    GET https://cfuv.ru/wp-json/cfu/v1/sched/find?by=teacher|room|subject&q=... — поиск

Только стандартная библиотека Python (urllib + json), без зависимостей.
Кэш — файлы в .cache/ рядом с этим модулем.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://cfuv.ru/wp-json/cfu/v1/sched/"
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

INDEX_TTL = 6 * 3600    # дерево групп меняется редко
GROUP_TTL = 3600        # расписание — раз в час
FIND_TTL = 3600         # результаты поиска — раз в час
FIND_BY = ("teacher", "room", "subject")

DAY_NAMES = {
    1: "Понедельник",
    2: "Вторник",
    3: "Среда",
    4: "Четверг",
    5: "Пятница",
    6: "Суббота",
    7: "Воскресенье",
}


def _http_get_json(url: str, timeout: int = 20, retries: int = 2):
    """GET + JSON с ретраями: cfuv.ru иногда отдаёт 502/обрыв на первом запросе."""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kfu-schedule/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(0.5 * (i + 1))
    raise last


def _cache_read(name: str, ttl: int):
    p = CACHE_DIR / name
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > ttl:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _cache_write(name: str, data) -> None:
    """Атомарная запись (tmp + replace): потоки бота не прочитают полфайла."""
    try:
        tmp = CACHE_DIR / f"{name}.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, CACHE_DIR / name)
    except Exception:
        pass


def get_index(force: bool = False):
    """Всё дерево: {'bells': [...], 'weeks': {...}, 'now': {...}, 'tree': {...}, 'groups': {...}}"""
    if not force:
        cached = _cache_read("index.json", INDEX_TTL)
        if cached is not None:
            return cached
    data = _http_get_json(BASE + "index")
    _cache_write("index.json", data)
    return data


def safe_filename(code: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in code)


def get_group(code: str, force: bool = False):
    """Занятия одной группы. Возвращает dict: {'код','занятия':[...],'fak','sess','gek'}."""
    code = (code or "").strip()
    if not code:
        raise ValueError("Пустой код группы")
    name = f"group_{safe_filename(code)}.json"
    if not force:
        cached = _cache_read(name, GROUP_TTL)
        if cached is not None:
            return cached
    url = BASE + "group?code=" + urllib.parse.quote(code)
    try:
        data = _http_get_json(url)
    except Exception as e:
        raise RuntimeError(f"Не получилось загрузить расписание {code}: {e}")
    if not data or "занятия" not in data:
        raise LookupError(f"Группа {code} не найдена на cfuv.ru")
    _cache_write(name, data)
    return data


# ---------- Красивые списки для выбора «факультет → группа» ----------

def subdivisions(index=None):
    idx = index or get_index()
    return sorted(idx.get("tree", {}).keys())


def directions(sub: str, index=None):
    idx = index or get_index()
    return sorted(idx.get("tree", {}).get(sub, {}).keys())


def courses(sub: str, direction: str, index=None):
    idx = index or get_index()
    d = idx.get("tree", {}).get(sub, {}).get(direction, {})
    def key(c):
        try:
            return int(c)
        except ValueError:
            return 99
    return sorted(d.keys(), key=key)


def groups_of(sub: str, direction: str, course: str, index=None):
    idx = index or get_index()
    return idx.get("tree", {}).get(sub, {}).get(direction, {}).get(str(course), [])


def group_info(code: str, index=None):
    idx = index or get_index()
    return idx.get("groups", {}).get(code)


def find_groups(query: str, index=None, limit: int = 20):
    """Поиск по коду группы: 'пи-241', 'ПИ-б-о-241', '241'."""
    idx = index or get_index()
    q = (query or "").strip().lower().replace(" ", "").replace("_", "-")
    if not q:
        return []
    out = []
    for code in idx.get("groups", {}):
        if q in code.lower().replace(" ", ""):
            out.append(code)
    # точное совпадение — первым
    out.sort(key=lambda c: (c.lower() != q, c))
    return out[:limit]


def find(by: str, query: str, force: bool = False):
    """Поиск пар: by='teacher'|'room'|'subject'. Возвращает [row] (у строк есть 'группа')."""
    if by not in FIND_BY:
        raise ValueError(f"by должен быть одним из {FIND_BY}")
    query = (query or "").strip()
    if len(query) < 2:
        raise ValueError("Запрос слишком короткий (минимум 2 буквы)")
    name = f"find_{by}_{safe_filename(query).lower()}.json"
    if not force:
        cached = _cache_read(name, FIND_TTL)
        if cached is not None:
            return cached
    url = BASE + "find?by=" + by + "&q=" + urllib.parse.quote(query)
    try:
        data = _http_get_json(url)
    except Exception as e:
        raise RuntimeError(f"Поиск не удался: {e}")
    rows = data if isinstance(data, list) else []
    _cache_write(name, rows)
    return rows


def format_found(rows, bells: dict, title: str, parity: str = "обе",
                 show_group: bool = True) -> str:
    """Пары из find(): группируем по дням. parity фильтрует чёт/нечёт (+'обе')."""
    if parity in ("чёт", "нечёт"):
        rows = [r for r in rows if r.get("чётность") in ("обе", parity)]
    by_day = {}
    for r in rows:
        by_day.setdefault(r.get("день"), []).append(r)
    if not by_day:
        return f"{title}\nНичего не найдено 😕"
    parts = [title]
    for day in sorted(by_day):
        parts.append(f"\n{DAY_NAMES.get(day, f'День {day}')}")
        for r in sorted(by_day[day], key=lambda x: (x.get("пара") or 0)):
            line = format_lesson(r, bells)
            if show_group and r.get("группа"):
                line += f"\n   👥 {r.get('группа')}"
            parts.append(line)
    return "\n".join(parts)


# ---------- Форматирование ----------

def bells_map(index=None):
    idx = index or get_index()
    m = {}
    for b in idx.get("bells", []):
        try:
            m[int(b.get("пара"))] = (b.get("начало", ""), b.get("конец", ""))
        except (TypeError, ValueError):
            continue
    return m


def format_lesson(row: dict, bells: dict) -> str:
    n = row.get("пара")
    t = ""
    if n in bells and any(bells[n]):
        t = f"{bells[n][0]}–{bells[n][1]} "
    subj = (row.get("предмет") or "").strip() or "—"
    kind = (row.get("вид") or "").strip()
    head = f"{n}. {t}{subj}"
    if kind:
        head += f" ({kind})"
    parity = (row.get("чётность") or "").strip()
    if parity and parity != "обе":
        head += f" [{parity}]"
    sub = row.get("подгруппа")
    if sub in (1, 2):
        head += f" · подгр. {sub}"
    teachers = ", ".join(row.get("преподаватели") or [])
    room = ", ".join(x for x in (row.get("аудитория"), row.get("корпус")) if x)
    extra = "; ".join(x for x in (teachers, room) if x)
    note = (row.get("примечание") or "").strip()
    if row.get("онлайн"):
        note = ((note + " ") if note else "") + f"онлайн: {row.get('онлайн')}"
    if note:
        extra = (extra + f" — {note}") if extra else note
    return head + (f"\n   {extra}" if extra else "")


def lessons_of_day(group_data: dict, day: int, parity: str = "обе", subgroup: int = 0):
    """Занятия дня. parity='обе' — всё; 'чёт'/'нечёт' — только своя неделя + 'обе'.

    subgroup=0 — вся группа; 1/2 — общие пары (подгруппа 0) + своя.
    """
    rows = group_data.get("занятия", [])
    out = [r for r in rows if r.get("день") == day]
    if parity in ("чёт", "нечёт"):
        out = [r for r in out if r.get("чётность") in ("обе", parity)]
    if subgroup in (1, 2):
        out = [r for r in out if r.get("подгруппа", 0) in (0, subgroup)]
    out.sort(key=lambda r: (r.get("пара") or 0, r.get("подгруппа") or 0))
    return out


def format_day(group_data: dict, day: int, bells: dict, parity: str = "обе",
               subgroup: int = 0) -> str:
    code = group_data.get("код", "")
    lessons = lessons_of_day(group_data, day, parity, subgroup)
    title = f"{DAY_NAMES.get(day, f'День {day}')} · {code}"
    if parity in ("чёт", "нечёт"):
        title += f" · {parity} неделя"
    if subgroup in (1, 2):
        title += f" · подгруппа {subgroup}"
    if not lessons:
        return title + "\nПар нет 🎉"
    return title + "\n" + "\n".join(format_lesson(r, bells) for r in lessons)


def format_week(group_data: dict, bells: dict, parity: str = "обе",
                subgroup: int = 0) -> str:
    parts = []
    for day in range(1, 7):
        lessons = lessons_of_day(group_data, day, parity, subgroup)
        if lessons:
            parts.append(format_day(group_data, day, bells, parity, subgroup))
    if not parts:
        return f"{group_data.get('код', '')}: занятий нет"
    return "\n\n".join(parts)


def format_session(group_data: dict) -> str:
    """Сессия (sess) + ГИА (gek). Поля у вуза меняются — рендерим всё, что есть."""
    code = group_data.get("код", "")
    is_asp = "-а-" in f"-{code}-".replace("--", "-").lower()
    parts = []
    sess = group_data.get("sess") or []
    if sess:
        lines = [f"📝 Сессия · {code}"]
        for z in sess:
            bits = []
            if z.get("дата"):
                bits.append(f"📅 {z.get('дата')}")
            if z.get("время"):
                bits.append(str(z.get("время")))
            head = " ".join(bits)
            subj = (z.get("предмет") or z.get("дисциплина") or "").strip()
            if z.get("вид"):
                subj += f" ({z.get('вид')})"
            teachers = ", ".join(z.get("преподаватели") or ([z.get("преподаватель")] if z.get("преподаватель") else []))
            room = ", ".join(str(x) for x in (z.get("аудитория"), z.get("место") or z.get("корпус")) if x)
            tail = "; ".join(x for x in (teachers, room) if x)
            note = (z.get("примечание") or "").strip()
            if note:
                tail = (tail + f" — {note}") if tail else note
            lines.append((head + "\n" if head else "") + subj + (f"\n   {tail}" if tail else ""))
        parts.append("\n".join(lines))
    else:
        parts.append("Кандидатские экзамены для группы ещё не опубликованы." if is_asp
                     else f"Расписание сессии для группы {code} ещё не опубликовано.")
    gek = group_data.get("gek") or []
    if gek:
        lines = ["🎓 ГИА · защита ВКР"]
        for z in gek:
            head = str(z.get("направление") or z.get("код") or "Защита ВКР")
            info = " ".join(x for x in
                            ([f"📅 {z.get('дата')} {z.get('время') or ''}".strip()]
                             if z.get("дата") else []) +
                            [f"{z.get('аудитория') or ''} {z.get('место') or ''}".strip()])
            tail = f"председатель: {z.get('председатель') or '—'}"
            lines.append(head + (f"\n   {info}" if info else "") + f"\n   {tail}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def lesson_key(row: dict):
    """Стабильный ключ пары для детектора изменений."""
    return (row.get("день"), row.get("пара"), row.get("подгруппа", 0),
            row.get("чётность"), row.get("предмет"), row.get("вид"),
            tuple(row.get("преподаватели") or []),
            row.get("аудитория"), row.get("корпус"),
            row.get("примечание"), row.get("дата"), row.get("онлайн"))


def group_signature(group_data: dict) -> str:
    keys = sorted((lesson_key(r) for r in group_data.get("занятия", [])),
                  key=lambda k: json.dumps(k, ensure_ascii=False, default=str))
    return json.dumps(keys, ensure_ascii=False, default=str)


def _ics_escape(s) -> str:
    return str(s or "").replace("\\", "\\\\").replace(",", "\\,") \
        .replace(";", "\\;").replace("\r", " ").replace("\n", " ")


def to_ics(code: str, lessons, bells: dict, weeks: dict, subgroup: int = 0) -> str:
    """Занятия × даты недель → календарь ICS (формат как у cfuv.ru)."""
    from datetime import date as _date, datetime as _dt, timedelta as _td, timezone as _tz
    if subgroup in (1, 2):
        lessons = [r for r in lessons if r.get("подгруппа", 0) in (0, subgroup)]
    ch, nch = weeks.get("ch", []), weeks.get("nch", [])
    stamp = _dt.now(_tz.utc).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0",
           "PRODID:-//KFU-schedule-bot//RU", "CALSCALE:GREGORIAN"]

    def add_days(s, n):
        d = _date.fromisoformat(s) + _td(days=n)
        return d.isoformat()

    def dt(day, hm):
        return day.replace("-", "") + "T" + str(hm).replace(":", "") + "00"

    for z in lessons:
        if "электив" in str(z.get("предмет") or "").lower():
            continue
        bell = bells.get(z.get("пара"))
        if not bell or not all(bell):
            continue
        if z.get("дата"):
            days = [z["дата"]]
        else:
            mons = []
            if z.get("чётность") in ("чёт", "обе"):
                mons += ch
            if z.get("чётность") in ("нечёт", "обе"):
                mons += nch
            days = sorted({add_days(m, (z.get("день") or 1) - 1) for m in mons})
        subj = str(z.get("предмет") or "").strip()
        if z.get("подгруппа") in (1, 2):
            subj += f" (п/гр {z.get('подгруппа')})"
        room = ", ".join(str(x) for x in (z.get("аудитория"), z.get("корпус")) if x)
        desc = " · ".join(x for x in
                          [str(z.get("вид") or ""), str(code),
                           ", ".join(z.get("преподаватели") or [])] if x)
        for day in days:
            out += ["BEGIN:VEVENT",
                    f"UID:{_ics_escape(code)}-{z.get('день')}-{z.get('пара')}-{day}@kfu-schedule",
                    f"DTSTAMP:{stamp}",
                    f"DTSTART:{dt(day, bell[0])}", f"DTEND:{dt(day, bell[1])}",
                    f"SUMMARY:{_ics_escape(subj)}",
                    f"LOCATION:{_ics_escape(room)}",
                    f"DESCRIPTION:{_ics_escape(desc)}",
                    "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out)


def split_long(text: str, limit: int = 3900):
    """Режем длинный текст для лимита Telegram (~4096 символов).

    Режем по строкам; строку длиннее лимита (без переносов) — жёстко кусками,
    иначе sendMessage упадёт с 'message is too long'.
    """
    if len(text) <= limit:
        return [text]
    chunks, cur = [], []
    size = 0

    def flush():
        nonlocal cur, size
        if cur:
            chunks.append("\n".join(cur))
            cur, size = [], 0

    for line in text.split("\n"):
        while len(line) > limit:
            flush()
            chunks.append(line[:limit])
            line = line[limit:]
        if size + len(line) + 1 > limit and cur:
            flush()
        cur.append(line)
        size += len(line) + 1
    flush()
    return chunks or [text]

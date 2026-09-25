# -*- coding: utf-8 -*-
"""Мини-сайт расписания КФУ. Только стандартная библиотека.

Запуск:
    python web.py            → http://localhost:8000
    python web.py 8080       → другой порт

Эндпоинты:
    /                        — страница выбора факультет → группа
    /api/index               — дерево групп + звонки (прокси cfuv.ru с кэшем)
    /api/group?code=ПИ-б-о-241 — занятия группы (прокси с кэшем)
    /api/find?by=teacher&q=Парменов — поиск пар (by: teacher|room|subject)
    /api/ics?code=ПИ-б-о-241&sub=1 — файл календаря (скачивание)
"""
import json
import os
import sys
import urllib.parse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser  # noqa: E402

SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=SITE_DIR, **kw)

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # API — живые данные: запрещаем браузеру кэшировать ответы
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/index":
            try:
                self._json(parser.get_index())
            except Exception as e:
                self._json({"error": str(e)}, 502)
            return
        if parsed.path == "/api/group":
            code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0]
            if not code.strip():
                self._json({"error": "Нужен ?code=ПИ-б-о-241"}, 400)
                return
            try:
                self._json(parser.get_group(code))
            except LookupError as e:
                self._json({"error": str(e)}, 404)
            except Exception as e:
                self._json({"error": str(e)}, 502)
            return
        if parsed.path == "/api/find":
            qs = urllib.parse.parse_qs(parsed.query)
            by = qs.get("by", ["teacher"])[0]
            q = qs.get("q", [""])[0]
            if by not in parser.FIND_BY:
                self._json({"error": "by должен быть teacher|room|subject"}, 400)
                return
            try:
                self._json(parser.find(by, q))
            except ValueError as e:
                self._json({"error": str(e)}, 400)
            except Exception as e:
                self._json({"error": str(e)}, 502)
            return
        if parsed.path == "/api/ics":
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [""])[0]
            try:
                sub = int(qs.get("sub", ["0"])[0])
            except ValueError:
                sub = 0
            if not code.strip():
                self._json({"error": "Нужен ?code=ПИ-б-о-241"}, 400)
                return
            try:
                idx = parser.get_index()
                g = parser.get_group(code)
                body = parser.to_ics(g.get("код", code), g.get("занятия", []),
                                     parser.bells_map(idx), idx.get("weeks", {}),
                                     sub if sub in (1, 2) else 0).encode("utf-8")
            except LookupError as e:
                self._json({"error": str(e)}, 404)
                return
            except Exception as e:
                self._json({"error": str(e)}, 502)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/calendar; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition",
                             f"attachment; filename*=UTF-8''{urllib.parse.quote(code)}.ics")
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Открыть: http://localhost:{port}")
    print("Остановка: Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

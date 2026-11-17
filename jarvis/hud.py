"""Le HUD : interface Iron Man dans le navigateur (http://localhost:7777), mise à jour en direct."""
import json
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML = Path(__file__).with_name("hud.html")


class HUD:
    def __init__(self, cfg, command_queue):
        self.cfg = cfg
        self.commands = command_queue
        self.clients = []
        self.lock = threading.Lock()
        self.last_state = {"type": "state", "state": "idle", "detail": ""}
        self.status = None  # objet Status, branché par jarvis_main
        self.on_refresh = None

    def emit(self, type_, **data):
        msg = {"type": type_, **data}
        if type_ == "state":
            self.last_state = msg
        line = json.dumps(msg, ensure_ascii=False)
        with self.lock:
            for q in list(self.clients):
                q.put(line)

    def _stats_loop(self):
        try:
            import psutil
        except ImportError:
            return
        while True:
            bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            self.emit("stats", cpu=psutil.cpu_percent(interval=None), ram=psutil.virtual_memory().percent,
                      battery=round(bat.percent) if bat else None)
            time.sleep(2)

    def start(self):
        hud = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if self.path == "/":
                    body = HTML.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    q = queue.Queue()
                    q.put(json.dumps(hud.last_state, ensure_ascii=False))
                    q.put(json.dumps({"type": "config", "user": hud.cfg.user_name, "model": hud.cfg.model}, ensure_ascii=False))
                    if hud.status:
                        for item in hud.status.snapshot():
                            q.put(json.dumps({"type": "connection", **item}, ensure_ascii=False))
                    with hud.lock:
                        hud.clients.append(q)
                    try:
                        while True:
                            try:
                                self.wfile.write(f"data: {q.get(timeout=15)}\n\n".encode())
                            except queue.Empty:
                                self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        with hud.lock:
                            if q in hud.clients:
                                hud.clients.remove(q)
                else:
                    self.send_error(404)

            def do_POST(self):
                if self.path == "/refresh":
                    if hud.on_refresh:
                        hud.on_refresh()
                    self.send_response(204)
                    self.end_headers()
                    return
                if self.path != "/command":
                    return self.send_error(404)
                n = int(self.headers.get("Content-Length", 0))
                try:
                    text = json.loads(self.rfile.read(n) or b"{}").get("text", "").strip()
                except Exception:
                    text = ""
                if text:
                    hud.commands.put(("hud", text))
                self.send_response(204)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", self.cfg.hud_port), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Thread(target=self._stats_loop, daemon=True).start()
        url = f"http://localhost:{self.cfg.hud_port}"
        print(f"[HUD] Interface disponible sur {url}")
        if self.cfg.hud_open_browser:
            webbrowser.open(url)

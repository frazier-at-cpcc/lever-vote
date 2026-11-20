"""Live poll server for "Would You Pull the Lever?". Python stdlib only.

Pages:  /        audience (phones)       /screen  projector view
        /admin   presenter controls (needs VOTE_ADMIN_KEY)
Env:    VOTE_ADMIN_KEY (required), VOTE_PORT (8080), VOTE_STATE (state.json), VOTE_POLLS (polls.json)
"""
import hashlib, hmac, json, os, secrets, threading, time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADMIN_KEY = os.environ.get("VOTE_ADMIN_KEY", "")
PORT = int(os.environ.get("VOTE_PORT", "8080"))
STATE_PATH = Path(os.environ.get("VOTE_STATE", HERE / "state.json"))
POLLS = json.loads(Path(os.environ.get("VOTE_POLLS", HERE / "polls.json")).read_text())
ADMIN_TOKEN = hmac.new(ADMIN_KEY.encode(), b"lever-admin", hashlib.sha256).hexdigest()
PAGES = {p: (HERE / "static" / f).read_bytes() for p, f in
         {"/": "audience.html", "/screen": "screen.html", "/admin": "admin.html"}.items()}
QR = (HERE / "static" / "qr.png").read_bytes() if (HERE / "static" / "qr.png").exists() else b""
ART = {f"/art/{f.name}": f.read_bytes() for f in (HERE / "static" / "art").glob("*.jpg")}
# Changes whenever pages, polls, or art change; open pages reload when it differs from what they loaded with.
BUILD = hashlib.sha256(b"".join(PAGES.values()) + json.dumps(POLLS).encode() + b"".join(ART.values())).hexdigest()[:12]

lock = threading.Lock()
# current: index into POLLS, or -1 for the lobby. votes: poll id -> voter id -> option index.
state = {"current": -1, "open": False, "results": False, "votes": {}}
if STATE_PATH.exists():
    state.update(json.loads(STATE_PATH.read_text()))
dirty = threading.Event()


def saver():
    """Write state at most once a second, atomically, so a burst of votes is one disk write."""
    while True:
        dirty.wait(); time.sleep(1); dirty.clear()
        with lock:
            data = json.dumps(state)
        tmp = STATE_PATH.with_suffix(".tmp")
        tmp.write_text(data); tmp.replace(STATE_PATH)


def counts(poll):
    c = [0] * len(poll["options"])
    for opt in state["votes"].get(poll["id"], {}).values():
        c[opt] += 1
    return c


def public_state(vid):
    with lock:
        i = state["current"]
        if i < 0:
            return {"poll": None, "build": BUILD}
        p = POLLS[i]
        out = {"poll": {k: p.get(k) for k in ("id", "title", "question", "options", "image", "alt")},
               "open": state["open"], "results": state["results"],
               "my_vote": state["votes"].get(p["id"], {}).get(vid),
               "total": len(state["votes"].get(p["id"], {})), "build": BUILD}
        if state["results"]:
            out["counts"] = counts(p)
        return out


def admin_state():
    with lock:
        i = state["current"]
        return {"current": i, "open": state["open"], "results": state["results"], "build": BUILD,
                "polls": [{"title": p["title"], "slide": p["slide"], "question": p["question"], "image": p.get("image"),
                           "options": p["options"], "counts": counts(p),
                           "total": len(state["votes"].get(p["id"], {}))} for p in POLLS]}


def admin_action(body):
    a = body.get("action")
    with lock:
        n = len(POLLS)
        if a in ("next", "prev", "goto"):
            target = {"next": state["current"] + 1, "prev": state["current"] - 1}.get(a, body.get("index"))
            if not isinstance(target, int) or not -1 <= target < n:
                return False
            # Moving to a poll opens voting and hides results: one click per slide.
            state.update(current=target, open=target >= 0, results=False)
        elif a == "open":   state["open"] = state["current"] >= 0
        elif a == "close":  state["open"] = False
        elif a == "results": state.update(open=False, results=True)
        elif a == "hide":   state["results"] = False
        elif a == "lobby":  state.update(current=-1, open=False, results=False)
        elif a == "reset" and state["current"] >= 0:
            state["votes"].pop(POLLS[state["current"]]["id"], None)
        elif a == "reset_all":
            state.update(current=-1, open=False, results=False, votes={})
        else:
            return False
    dirty.set()
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "lever-vote"

    def log_message(self, fmt, *args):  # quiet: one line per non-poll request
        if not self.path.startswith("/api/state"):
            super().log_message(fmt, *args)

    def cookies(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return {k: v.value for k, v in c.items()}

    def send(self, code, body=b"", ctype="application/json", headers=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not any(k == "Cache-Control" for k, _ in headers):
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 4096:
            return None
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None

    def is_admin(self):
        return bool(ADMIN_KEY) and hmac.compare_digest(self.cookies().get("adm", ""), ADMIN_TOKEN)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in PAGES:
            hdrs = []
            if path == "/" and "vid" not in self.cookies():
                hdrs.append(("Set-Cookie", f"vid={secrets.token_urlsafe(12)}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax; Secure"))
            return self.send(200, PAGES[path], "text/html; charset=utf-8", hdrs)
        if path in ART:
            return self.send(200, ART[path], "image/jpeg", [("Cache-Control", "public, max-age=3600")])
        if path == "/qr.png" and QR:
            return self.send(200, QR, "image/png")
        if path == "/api/state":
            return self.send(200, public_state(self.cookies().get("vid")))
        if path == "/api/admin/state":
            return self.send(200, admin_state()) if self.is_admin() else self.send(401, {"error": "login"})
        if path == "/healthz":
            return self.send(200, {"ok": True})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        path, b = self.path, self.body()
        if b is None:
            return self.send(400, {"error": "bad body"})
        if path == "/api/vote":
            vid, opt = self.cookies().get("vid"), b.get("option")
            with lock:
                i = state["current"]
                ok = (vid and i >= 0 and state["open"] and isinstance(opt, int)
                      and 0 <= opt < len(POLLS[i]["options"]))
                if ok:
                    state["votes"].setdefault(POLLS[i]["id"], {})[vid] = opt
            if not ok:
                return self.send(409, {"error": "voting is closed"})
            dirty.set()
            return self.send(200, {"ok": True})
        if path == "/api/admin/login":
            if ADMIN_KEY and hmac.compare_digest(str(b.get("key", "")), ADMIN_KEY):
                return self.send(200, {"ok": True}, headers=[("Set-Cookie",
                    f"adm={ADMIN_TOKEN}; Path=/; Max-Age=43200; HttpOnly; SameSite=Strict; Secure")])
            time.sleep(1)  # ponytail: crude brute-force brake; Cloudflare rate limiting if it ever matters
            return self.send(403, {"error": "wrong key"})
        if path == "/api/admin/action":
            if not self.is_admin():
                return self.send(401, {"error": "login"})
            return self.send(200, admin_state()) if admin_action(b) else self.send(400, {"error": "bad action"})
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    if not ADMIN_KEY:
        raise SystemExit("set VOTE_ADMIN_KEY")
    threading.Thread(target=saver, daemon=True).start()
    ThreadingHTTPServer.daemon_threads = True
    print(f"lever-vote on :{PORT}, {len(POLLS)} polls", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

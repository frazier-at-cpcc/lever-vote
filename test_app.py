"""One end-to-end check: lobby, admin auth, voting rules, results, persistence."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error

def call(port, path, body=None, cookie=""):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Cookie": cookie})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}") if "json" in r.headers["Content-Type"] else None, r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), ""

def main():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    state = os.path.join(tempfile.mkdtemp(), "state.json")
    env = dict(os.environ, VOTE_ADMIN_KEY="k3y", VOTE_PORT=str(port), VOTE_STATE=state)
    srv = subprocess.Popen([sys.executable, "app.py"], env=env, cwd=os.path.dirname(os.path.abspath(__file__)))
    try:
        for _ in range(50):
            try: call(port, "/healthz"); break
            except OSError: time.sleep(0.1)
        lobby = call(port, "/api/state")[1]
        assert lobby["poll"] is None and len(lobby["build"]) == 12, "starts in lobby with a build id"
        assert call(port, "/api/vote", {"option": 0}, "vid=a")[0] == 409, "no voting in lobby"
        assert call(port, "/api/admin/action", {"action": "next"})[0] == 401, "admin needs auth"
        assert call(port, "/api/admin/login", {"key": "nope"})[0] == 403
        code, _, setc = call(port, "/api/admin/login", {"key": "k3y"}); assert code == 200
        adm = setc.split(";")[0]
        _, st, _ = call(port, "/api/admin/action", {"action": "next"}, adm)
        assert st["current"] == 0 and st["open"] and not st["results"], "next opens poll 1"
        assert call(port, "/api/vote", {"option": 1}, "vid=a")[0] == 200
        assert call(port, "/api/vote", {"option": 0}, "vid=a")[0] == 200, "vote can change"
        assert call(port, "/api/vote", {"option": 0}, "vid=b")[0] == 200
        assert call(port, "/api/vote", {"option": 9}, "vid=c")[0] == 409, "bad option rejected"
        assert call(port, "/api/vote", {"option": 0})[0] == 409, "no cookie rejected"
        pub = call(port, "/api/state", cookie="vid=a")[1]
        assert pub["my_vote"] == 0 and pub["total"] == 2 and "counts" not in pub, "counts hidden until results"
        _, st, _ = call(port, "/api/admin/action", {"action": "results"}, adm)
        assert not st["open"] and st["results"] and st["polls"][0]["counts"] == [2, 0]
        assert call(port, "/api/state")[1]["counts"] == [2, 0]
        assert call(port, "/api/vote", {"option": 1}, "vid=d")[0] == 409, "closed after results"
        assert call(port, "/api/admin/action", {"action": "goto", "index": 99}, adm)[0] == 400
        time.sleep(1.5)
        assert json.load(open(state))["votes"]["p1"] == {"a": 0, "b": 0}, "state persisted"
        print("ok")
    finally:
        srv.terminate()

if __name__ == "__main__":
    main()

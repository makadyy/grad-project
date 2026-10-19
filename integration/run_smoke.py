"""Offline integration smoke: A2 telemetry -> A3 safe policy, grounded by A4 world artifacts.

A1 is an offline network-flow benchmark, deliberately kept separate from session telemetry;
this smoke reports whether real A1 outputs exist rather than fabricating them.
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A4 = ROOT / "genai"
sys.path.insert(0, str(ROOT / "profiler" / "src"))
sys.path.insert(0, str(ROOT / "maze"))
sys.path.insert(0, str(A4))

from profiler_xai.feature_extractor import FeatureExtractor  # noqa: E402
from maze_env import MazeEnv, MazeState  # noqa: E402
from policy import choose_action  # noqa: E402
import world_model  # noqa: E402
from knowledge_base import build_chunks  # noqa: E402


def run_smoke() -> dict:
    # Small deterministic fixture exercises all four accepted A2 event sources.
    events = [
        {"session_id":"demo-1","event_id":"e1","timestamp":"2025-01-14T10:00:00Z","source":"cowrie","event_type":"command","command":"wget example.invalid","resource":"/tmp/payload"},
        {"session_id":"demo-1","event_id":"e2","timestamp":"2025-01-14T10:00:03Z","source":"portal","event_type":"portal_auth_failure","resource":"/login"},
        {"session_id":"demo-1","event_id":"e3","timestamp":"2025-01-14T10:00:04Z","source":"database","event_type":"db_write","resource":"orders"},
        {"session_id":"demo-1","event_id":"e4","timestamp":"2025-01-14T10:00:05Z","source":"wazuh","event_type":"alert","severity":"critical","resource":"sys-db"},
    ]
    extractor = FeatureExtractor()
    extractor.add_events(events)
    features = extractor.features_for("demo-1")

    world = world_model.build_world()
    world_errors = world_model.validate(world)
    if world_errors:
        raise RuntimeError(f"A4 world validation failed: {world_errors}")
    chunks = build_chunks(world)

    # Generate a small A4 offline set using FakeLLM; no Ollama or database required.
    with tempfile.TemporaryDirectory(prefix="gatekeeper-a4-smoke-") as td:
        subprocess.run([
            sys.executable, str(A4 / "build_artifacts.py"), "--dry-run", "--n", "20",
            "--world", str(A4 / "world_model.json"), "--out", td,
        ], cwd=A4, check=True, capture_output=True, text=True)
        artifact_path = Path(td) / "artifacts.jsonl"
        artifacts = [json.loads(line) for line in artifact_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(artifacts) != 20:
        raise AssertionError(f"A4 smoke expected 20 accepted artifacts, got {len(artifacts)}")
    lure_ids = sorted({
        item["meta"]["honey_id"] for item in artifacts
        if item.get("meta", {}).get("honey_id")
    })
    # A4's H04 planted-email reference is the abstract lure context supplied to A3.
    if "H04" not in lure_ids:
        raise AssertionError(f"A4 generated set did not include planted H04 lure: {lure_ids}")

    # Explicit, versioned adapter from A2 session metrics into A3's typed initial state.
    initial = MazeState(
        intel=min(3, int(features["distinct_resource_count"])),
        exposure=min(3, int(features["suspicious_command_count"])),
        alert=min(3, int(features["portal_auth_failure_count"] + features["wazuh_critical_severity_count"])),
        progress=min(3, int(features["database_write_count"] + features["database_delete_count"])),
    )
    scenario = {
        "company": world_model.COMPANY_NAME,
        "world_sha256": world["meta"]["content_sha256"],
        "knowledge_chunks": len(chunks),
        "generated_artifacts": len(artifacts),
        "available_honey_lures": lure_ids,
        "a1_role": "offline_network_flow_benchmark; not fused with session telemetry",
    }
    env = MazeEnv()
    obs, info = env.reset(options={"state": initial, "scenario": scenario})
    action = choose_action(obs, info["action_mask"])
    next_obs, reward, terminated, truncated, step_info = env.step(action)

    a1_out = ROOT / "gatekeeper" / "out"
    a1_ready = all((a1_out / name).exists() for name in (
        "train.parquet", "val.parquet", "test.parquet", "unseen_day.parquet", "baseline_results.json"))
    return {
        "status": "PASS",
        "a1": "real_outputs_present" if a1_ready else "offline_pipeline_available_but_real_dataset_outputs_missing",
        "a2_session_features": {k: features[k] for k in (
            "event_count", "suspicious_command_count", "portal_auth_failure_count",
            "database_write_count", "wazuh_critical_severity_count")},
        "a3": {"initial_state": info["state"], "requested_action": action.name,
               "executed_action": step_info["executed_action"], "shielded": step_info["shielded"],
               "reward": reward, "terminated": terminated, "truncated": truncated,
               "next_observation": next_obs.tolist()},
        "a4": {"world_sha256": scenario["world_sha256"], "knowledge_chunks": len(chunks),
               "generated_artifacts": len(artifacts), "honey_lures": lure_ids},
    }


if __name__ == "__main__":
    print(json.dumps(run_smoke(), indent=2, ensure_ascii=False))

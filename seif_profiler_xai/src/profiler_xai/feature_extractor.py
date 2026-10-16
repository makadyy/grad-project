"""Incremental, deterministic session-level feature extraction."""
import argparse, json, math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from .schemas import NormalizedEvent

FEATURE_NAMES = [
"event_count","duration_seconds","events_per_minute","cowrie_event_count","portal_event_count",
"database_event_count","wazuh_alert_count","login_attempt_count","login_failure_count",
"login_success_count","login_failure_rate","command_event_count","unique_command_count",
"suspicious_command_count","file_download_event_count","file_upload_event_count",
"network_connection_count","bytes_in_total","bytes_out_total","bytes_total",
"distinct_resource_count","portal_auth_failure_count","portal_admin_action_count",
"database_read_count","database_write_count","database_delete_count",
"wazuh_high_severity_count","wazuh_critical_severity_count",
"inter_event_seconds_mean","inter_event_seconds_max"]
SUSPICIOUS_TERMS = ("wget","curl","chmod","sudo","passwd","useradd","nc ","netcat",
                    "bash -i","powershell","certutil","rm -rf","/etc/shadow","ssh-keygen")

def parse_time(value):
    try: dt = datetime.fromisoformat(value.strip().replace("Z","+00:00"))
    except ValueError as exc: raise ValueError(f"Invalid ISO-8601 timestamp: {value!r}") from exc
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()

@dataclass
class _Session:
    session_id: str
    timestamps: list[float] = field(default_factory=list)
    sources: Counter = field(default_factory=Counter)
    event_types: Counter = field(default_factory=Counter)
    statuses: Counter = field(default_factory=Counter)
    severities: Counter = field(default_factory=Counter)
    resources: set[str] = field(default_factory=set)
    commands: set[str] = field(default_factory=set)
    suspicious_commands: set[str] = field(default_factory=set)
    bytes_in_total: float = 0.0
    bytes_out_total: float = 0.0
    seen_event_ids: set[str] = field(default_factory=set)
    event_count: int = 0

class FeatureExtractor:
    """Accept events in batches; snapshot/restore supports checkpointing."""
    def __init__(self): self._sessions = {}
    def add_event(self, event: Mapping[str, Any] | Any):
        obj = asdict(event) if hasattr(event, "__dataclass_fields__") else dict(event)
        e = NormalizedEvent.from_mapping(obj)
        s = self._sessions.setdefault(e.session_id, _Session(e.session_id))
        if e.event_id and e.event_id in s.seen_event_ids: return
        if e.event_id: s.seen_event_ids.add(e.event_id)
        s.timestamps.append(parse_time(e.timestamp)); s.sources[e.source] += 1
        s.event_types[e.event_type] += 1
        if e.status: s.statuses[e.status] += 1
        if e.severity: s.severities[e.severity] += 1
        if e.resource: s.resources.add(e.resource)
        if e.command.strip():
            cmd = " ".join(e.command.lower().split()); s.commands.add(cmd)
            if any(term in cmd for term in SUSPICIOUS_TERMS): s.suspicious_commands.add(cmd)
        s.bytes_in_total += e.bytes_in; s.bytes_out_total += e.bytes_out; s.event_count += 1
    def add_events(self, events: Iterable[Mapping[str, Any] | Any]):
        for e in events: self.add_event(e)
    def session_ids(self): return sorted(self._sessions)
    def features_for(self, session_id):
        if session_id not in self._sessions: raise KeyError(f"Unknown session_id: {session_id}")
        s = self._sessions[session_id]; times = sorted(s.timestamps)
        duration = max(0.0, times[-1]-times[0]) if times else 0.0
        gaps = [b-a for a,b in zip(times,times[1:])]
        count_types = lambda names: sum(s.event_types[n] for n in names)
        attempts = count_types(("login_attempt","auth_attempt","cowrie.login_attempt"))
        failures = count_types(("login_failure","auth_failure","cowrie.login_failed"))
        successes = count_types(("login_success","auth_success","cowrie.login_success"))
        failures = max(failures, s.statuses["failed"]); successes = max(successes, s.statuses["success"])
        command_count = sum(n for k,n in s.event_types.items() if "command" in k)
        downloads = sum(n for k,n in s.event_types.items() if "download" in k)
        uploads = sum(n for k,n in s.event_types.items() if "upload" in k)
        connections = sum(n for k,n in s.event_types.items() if "connection" in k or "connect" in k)
        vals = {
          "session_id":session_id, "event_count":s.event_count, "duration_seconds":duration,
          "events_per_minute":s.event_count/(duration/60) if duration else 0.0,
          "cowrie_event_count":s.sources["cowrie"], "portal_event_count":s.sources["portal"],
          "database_event_count":s.sources["database"], "wazuh_alert_count":s.sources["wazuh"],
          "login_attempt_count":attempts, "login_failure_count":failures, "login_success_count":successes,
          "login_failure_rate":failures/max(attempts,failures+successes,1),
          "command_event_count":command_count, "unique_command_count":len(s.commands),
          "suspicious_command_count":len(s.suspicious_commands),
          "file_download_event_count":downloads, "file_upload_event_count":uploads,
          "network_connection_count":connections, "bytes_in_total":s.bytes_in_total,
          "bytes_out_total":s.bytes_out_total, "bytes_total":s.bytes_in_total+s.bytes_out_total,
          "distinct_resource_count":len(s.resources),
          "portal_auth_failure_count":count_types(("portal_auth_failure","auth_failure")),
          "portal_admin_action_count":sum(n for k,n in s.event_types.items() if k.startswith("portal_admin_") or k=="admin_action"),
          "database_read_count":count_types(("db_read","database_read","select")),
          "database_write_count":count_types(("db_write","database_write","insert","update")),
          "database_delete_count":count_types(("db_delete","database_delete","delete")),
          "wazuh_high_severity_count":sum(n for k,n in s.severities.items() if k in {"high","4","level 12","level 13","level 14"}),
          "wazuh_critical_severity_count":sum(n for k,n in s.severities.items() if k in {"critical","5","level 15"}),
          "inter_event_seconds_mean":sum(gaps)/len(gaps) if gaps else 0.0,
          "inter_event_seconds_max":max(gaps) if gaps else 0.0}
        for k,v in vals.items():
            if isinstance(v,float) and not math.isfinite(v): vals[k]=0.0
        return vals
    def all_features(self): return [self.features_for(sid) for sid in self.session_ids()]
    def snapshot(self):
        out={}
        for sid,s in self._sessions.items():
            out[sid]={"timestamps":s.timestamps,"sources":dict(s.sources),"event_types":dict(s.event_types),
            "statuses":dict(s.statuses),"severities":dict(s.severities),"resources":sorted(s.resources),
            "commands":sorted(s.commands),"suspicious_commands":sorted(s.suspicious_commands),
            "bytes_in_total":s.bytes_in_total,"bytes_out_total":s.bytes_out_total,
            "seen_event_ids":sorted(s.seen_event_ids),"event_count":s.event_count}
        return {"sessions":out}
    @classmethod
    def from_snapshot(cls,snapshot):
        x=cls()
        for sid,d in snapshot.get("sessions",{}).items():
            s=_Session(sid); s.timestamps=list(d.get("timestamps",[]))
            for name in ("sources","event_types","statuses","severities"): getattr(s,name).update(d.get(name,{}))
            for name in ("resources","commands","suspicious_commands","seen_event_ids"): setattr(s,name,set(d.get(name,[])))
            s.bytes_in_total=float(d.get("bytes_in_total",0)); s.bytes_out_total=float(d.get("bytes_out_total",0))
            s.event_count=int(d.get("event_count",0)); x._sessions[sid]=s
        return x

def extract_features(events):
    x=FeatureExtractor(); x.add_events(events); return x.all_features()

def main():
    p=argparse.ArgumentParser(); p.add_argument("input"); p.add_argument("--out",required=True); p.add_argument("--checkpoint")
    a=p.parse_args(); x=FeatureExtractor(); src=Path(a.input)
    with src.open(encoding="utf-8") as f:
        for line_no,line in enumerate(f,1):
            if line.strip():
                try: x.add_event(json.loads(line))
                except Exception as exc: raise SystemExit(f"{src}:{line_no}: {exc}") from exc
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8") as f:
        for row in x.all_features(): f.write(json.dumps(row)+"\n")
    if a.checkpoint:
        cp=Path(a.checkpoint); cp.parent.mkdir(parents=True,exist_ok=True); cp.write_text(json.dumps(x.snapshot()),encoding="utf-8")
    print(f"Wrote {len(x.session_ids())} sessions to {out}")
if __name__=="__main__": main()

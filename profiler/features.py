"""Incremental, deterministic session-level feature extraction."""
import argparse, json, math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from events import NormalizedEvent

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

# Centralized normalized aliases. Keys are canonical source names; values map
# accepted event_type spellings to metric categories. Unknown types are ignored.
EVENT_ALIASES = {
    "cowrie": {
        "login_attempt": "login_attempt", "auth_attempt": "login_attempt",
        "login_failure": "login_failure", "auth_failure": "login_failure",
        "login_success": "login_success", "auth_success": "login_success",
        "command": "command", "command_executed": "command",
        "file_download": "download", "download": "download",
        "file_upload": "upload", "upload": "upload",
        "connection": "connection", "connect": "connection",
        "connection_open": "connection", "connection_attempt": "connection",
    },
    "portal": {
        "portal_auth_attempt": "login_attempt", "portal_login_attempt": "login_attempt",
        "auth_attempt": "login_attempt", "portal_auth_failure": "login_failure",
        "portal_login_failure": "login_failure", "auth_failure": "login_failure",
        "portal_auth_success": "login_success", "portal_login_success": "login_success",
        "auth_success": "login_success", "portal_admin_action": "admin",
        "admin_action": "admin", "portal_admin_create": "admin",
        "portal_admin_update": "admin", "portal_admin_delete": "admin",
    },
    "database": {
        "db_read": "read", "database_read": "read", "select": "read",
        "db_write": "write", "database_write": "write", "insert": "write", "update": "write",
        "db_delete": "delete", "database_delete": "delete", "delete": "delete",
    },
}

# Overflow policy: byte counters SATURATE at MAX_BYTES (never wrap to 0, never inf).
# 1e18 bytes (~1 EB) is far above any real session and safe for float32 models.
MAX_BYTES = 1e18


def _sat(value):
    return MAX_BYTES if value >= MAX_BYTES else value


def _category(source, event_type):
    """Return a documented category for a source-scoped, case-normalized alias."""
    return EVENT_ALIASES.get(source, {}).get(event_type.strip().lower())

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
    source_event_types: dict = field(default_factory=dict)
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
        if not e.event_id: raise ValueError("event_id is required for reliable deduplication")
        s = self._sessions.setdefault(e.session_id, _Session(e.session_id))
        dedup_key = f"{e.source}:{e.event_id}"
        if dedup_key in s.seen_event_ids: return
        s.seen_event_ids.add(dedup_key)
        s.timestamps.append(parse_time(e.timestamp)); s.sources[e.source] += 1
        s.event_types[e.event_type] += 1
        s.source_event_types.setdefault(e.source, Counter())[e.event_type] += 1
        if e.status: s.statuses[e.status] += 1
        if e.severity: s.severities[e.severity] += 1
        if e.resource: s.resources.add(e.resource)
        if e.command.strip():
            cmd = " ".join(e.command.lower().split()); s.commands.add(cmd)
            if any(term in cmd for term in SUSPICIOUS_TERMS): s.suspicious_commands.add(cmd)
        s.bytes_in_total = _sat(s.bytes_in_total + _sat(e.bytes_in)); s.bytes_out_total = _sat(s.bytes_out_total + _sat(e.bytes_out)); s.event_count += 1
    def add_events(self, events: Iterable[Mapping[str, Any] | Any]):
        for e in events: self.add_event(e)
    def session_ids(self): return sorted(self._sessions)
    def features_for(self, session_id):
        if session_id not in self._sessions: raise KeyError(f"Unknown session_id: {session_id}")
        s = self._sessions[session_id]; times = sorted(s.timestamps)
        duration = max(0.0, times[-1]-times[0]) if times else 0.0
        gaps = [b-a for a,b in zip(times,times[1:])]
        categories = Counter()
        for source, event_types in s.source_event_types.items():
            for event_type, n in event_types.items():
                category = _category(source, event_type)
                if category: categories[(source, category)] += n
        def metric(source, category): return categories[(source, category)]
        # Auth aggregates are portal-scoped, matching the portal-specific auth contract.
        attempts = metric("portal", "login_attempt")
        failures = metric("portal", "login_failure")
        successes = metric("portal", "login_success")
        command_count = metric("cowrie", "command")
        downloads, uploads = metric("cowrie", "download"), metric("cowrie", "upload")
        connections = metric("cowrie", "connection")
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
          "bytes_out_total":s.bytes_out_total, "bytes_total":_sat(s.bytes_in_total+s.bytes_out_total),
          "distinct_resource_count":len(s.resources),
          "portal_auth_failure_count":metric("portal", "login_failure"),
          "portal_admin_action_count":metric("portal", "admin"),
          "database_read_count":metric("database", "read"),
          "database_write_count":metric("database", "write"),
          "database_delete_count":metric("database", "delete"),
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
            "source_event_types":{source:dict(types) for source,types in s.source_event_types.items()},
            "statuses":dict(s.statuses),"severities":dict(s.severities),"resources":sorted(s.resources),
            "commands":sorted(s.commands),"suspicious_commands":sorted(s.suspicious_commands),
            "bytes_in_total":s.bytes_in_total,"bytes_out_total":s.bytes_out_total,
            "seen_event_ids":sorted(s.seen_event_ids),"event_count":s.event_count}
        return {"sessions":out}
    @classmethod
    def from_snapshot(cls,snapshot):
        if not isinstance(snapshot, Mapping) or set(snapshot)!={"sessions"} or not isinstance(snapshot["sessions"],Mapping):
            raise ValueError("Invalid snapshot: expected a sessions mapping")
        x=cls()
        for sid,d in snapshot["sessions"].items():
            if not isinstance(sid,str) or not sid or not isinstance(d,Mapping): raise ValueError("Invalid snapshot session")
            try:
                s=_Session(sid); s.timestamps=[float(v) for v in d["timestamps"]]
                if any(not math.isfinite(v) for v in s.timestamps): raise ValueError("non-finite timestamp")
                for name in ("sources","event_types","statuses","severities"):
                    data=d[name]
                    if not isinstance(data,Mapping) or any(not isinstance(k,str) or isinstance(v,bool) or not isinstance(v,int) or v<0 for k,v in data.items()): raise ValueError(f"invalid {name}")
                    getattr(s,name).update(data)
                source_types=d.get("source_event_types")
                if source_types is None:
                    raise ValueError("missing source_event_types; restore snapshot by replaying events")
                if not isinstance(source_types,Mapping): raise ValueError("invalid source_event_types")
                for source,types in source_types.items():
                    if not isinstance(source,str) or not isinstance(types,Mapping) or any(not isinstance(k,str) or isinstance(v,bool) or not isinstance(v,int) or v<0 for k,v in types.items()): raise ValueError("invalid source_event_types")
                    s.source_event_types[source]=Counter(types)
                if sum(sum(types.values()) for types in s.source_event_types.values()) != sum(s.event_types.values()): raise ValueError("inconsistent source_event_types")
                for name in ("resources","commands","suspicious_commands","seen_event_ids"):
                    values=d[name]
                    if not isinstance(values,list) or any(not isinstance(v,str) for v in values): raise ValueError(f"invalid {name}")
                    setattr(s,name,set(values))
                for name in ("bytes_in_total","bytes_out_total"):
                    v=d[name]
                    if isinstance(v,bool) or not math.isfinite(float(v)) or float(v)<0: raise ValueError(f"invalid {name}")
                    setattr(s,name,float(v))
                n=d["event_count"]
                if isinstance(n,bool) or not isinstance(n,int) or n<0 or n!=sum(s.sources.values()) or n!=sum(s.event_types.values()): raise ValueError("inconsistent event_count")
                s.event_count=n
            except (KeyError,TypeError,ValueError,OverflowError) as exc: raise ValueError(f"Invalid snapshot for session {sid!r}: {exc}") from exc
            x._sessions[sid]=s
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

"""Normalized event contract shared by source adapters and feature extractor."""
from dataclasses import dataclass
from typing import Any, Mapping

@dataclass(frozen=True)
class NormalizedEvent:
    session_id: str
    timestamp: str
    source: str
    event_type: str
    event_id: str = ""
    src_ip: str = ""
    username: str = ""
    command: str = ""
    bytes_in: float = 0.0
    bytes_out: float = 0.0
    duration_seconds: float = 0.0
    status: str = ""
    severity: str = ""
    resource: str = ""
    metadata: Mapping[str, Any] | None = None

    @classmethod
    def from_mapping(cls, obj: Mapping[str, Any]) -> "NormalizedEvent":
        required = ("session_id", "timestamp", "source", "event_type")
        missing = [k for k in required if not obj.get(k)]
        if missing:
            raise ValueError(f"Missing required event fields: {', '.join(missing)}")
        source = str(obj["source"]).strip().lower()
        if source not in {"cowrie", "portal", "database", "wazuh"}:
            raise ValueError(f"Unsupported source {source!r}")
        def nonnegative(k):
            value = float(obj.get(k, 0) or 0)
            if value < 0: raise ValueError(f"{k} must be >= 0")
            return value
        return cls(
            session_id=str(obj["session_id"]).strip(),
            timestamp=str(obj["timestamp"]).strip(), source=source,
            event_type=str(obj["event_type"]).strip().lower(),
            event_id=str(obj.get("event_id", "") or ""),
            src_ip=str(obj.get("src_ip", "") or ""), username=str(obj.get("username", "") or ""),
            command=str(obj.get("command", "") or ""), bytes_in=nonnegative("bytes_in"),
            bytes_out=nonnegative("bytes_out"), duration_seconds=nonnegative("duration_seconds"),
            status=str(obj.get("status", "") or "").strip().lower(),
            severity=str(obj.get("severity", "") or "").strip().lower(),
            resource=str(obj.get("resource", "") or "").strip().lower(),
            metadata=obj.get("metadata") or {})

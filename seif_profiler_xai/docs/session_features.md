# Session Feature Dictionary — Profiler & XAI

Owner: Seif Mohamed · Version: v0.1

## Normalized input contract

Every source adapter must emit `session_id`, `timestamp` (ISO-8601; UTC preferred), `source` (`cowrie`, `portal`, `database`, `wazuh`), and `event_type`. `event_id` should be stable for deduplication. Source formats vary by deployment, so this is an adapter contract—not a claim that every native log uses these exact names.

| Normalized field | Cowrie mapping | Portal mapping | Database mapping | Wazuh mapping |
|---|---|---|---|---|
| `session_id` | session identifier | request/session correlation ID | application correlation ID | correlated session if available |
| `timestamp` | event timestamp | request timestamp | audit timestamp | alert timestamp |
| `event_id` | stable event ID | request/event ID | audit ID | alert ID |
| `event_type` | normalized login/command/file/connection event | auth/admin/API action | read/write/delete | alert |
| `src_ip` | remote IP | trusted-proxy-aware client IP | audit context if available | source/agent IP if relevant |
| `username` | attempted/accepted user | account ID/role | service account/role | user field if relevant |
| `command` | Cowrie command text for transient pattern counting | usually empty | empty | usually empty |
| `bytes_in/out` | transfer bytes | request/response size | bytes read/written if available | event/network byte counts |
| `status` | auth outcome | request/auth outcome | operation result | mapped outcome |
| `severity` | empty | empty | empty | normalized Wazuh level |
| `resource` | file/service category | route/action category | table/operation category | agent/rule category |

Do not put raw IPs, usernames, commands, tokens, or payloads in the model matrix. Aggregated features are emitted instead.

## Feature dictionary (30)

| # | Feature | Definition | Sources |
|---:|---|---|---|
| 1 | `event_count` | Unique normalized events in session | all |
| 2 | `duration_seconds` | Last timestamp minus first | all |
| 3 | `events_per_minute` | Event count / duration in minutes; 0 for zero duration | all |
| 4 | `cowrie_event_count` | Cowrie events | Cowrie |
| 5 | `portal_event_count` | Portal events | portal |
| 6 | `database_event_count` | Database audit events | DB |
| 7 | `wazuh_alert_count` | Wazuh events | Wazuh |
| 8 | `login_attempt_count` | Normalized auth-attempt events | Cowrie/portal |
| 9 | `login_failure_count` | Normalized auth failures | Cowrie/portal |
| 10 | `login_success_count` | Normalized auth successes | Cowrie/portal |
| 11 | `login_failure_rate` | Failures / max(attempts, failures + successes, 1) | Cowrie/portal |
| 12 | `command_event_count` | Event types containing `command` | Cowrie |
| 13 | `unique_command_count` | Distinct normalized command strings | Cowrie |
| 14 | `suspicious_command_count` | Distinct commands matching documented heuristic terms | Cowrie |
| 15 | `file_download_event_count` | Event types containing `download` | Cowrie |
| 16 | `file_upload_event_count` | Event types containing `upload` | Cowrie |
| 17 | `network_connection_count` | Event types containing `connection` or `connect` | Cowrie/Wazuh |
| 18 | `bytes_in_total` | Incoming byte sum | all with telemetry |
| 19 | `bytes_out_total` | Outgoing byte sum | all with telemetry |
| 20 | `bytes_total` | Incoming + outgoing bytes | all with telemetry |
| 21 | `distinct_resource_count` | Distinct normalized resource categories | portal/DB/Wazuh |
| 22 | `portal_auth_failure_count` | Portal/auth failure event types | portal |
| 23 | `portal_admin_action_count` | Portal admin-action events | portal |
| 24 | `database_read_count` | Read/select events | DB |
| 25 | `database_write_count` | Write/insert/update events | DB |
| 26 | `database_delete_count` | Delete events | DB |
| 27 | `wazuh_high_severity_count` | High / configured high severity count | Wazuh |
| 28 | `wazuh_critical_severity_count` | Critical / configured critical severity count | Wazuh |
| 29 | `inter_event_seconds_mean` | Mean gap between sorted timestamps | all |
| 30 | `inter_event_seconds_max` | Maximum gap between sorted timestamps | all |

## Canonical event examples
- Cowrie login failure: `source=cowrie`, `event_type=login_failure`, `status=failed`.
- Cowrie command: `source=cowrie`, `event_type=command`, `command=<text>`.
- Portal failed login: `source=portal`, `event_type=portal_auth_failure`, `status=failed`.
- Database update: `source=database`, `event_type=db_write`, `resource=<table category>`.
- Wazuh level 15: `source=wazuh`, `event_type=alert`, `severity=critical`.

`Suspicious command` is a heuristic, not a verdict. Feature names/event mappings must be frozen before final test evaluation. Session-level features are not directly interchangeable with per-flow CSE-CIC-IDS2018 features without an explicit aggregation strategy.

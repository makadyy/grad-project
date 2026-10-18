# A3 — Abstract Deception Investigation Maze

Standalone, deterministic Gymnasium environment plus a tested rule-policy module. It models an abstract investigation as a small finite-state maze; it does **not** connect to or act on real systems. No A3 source was supplied, so this implementation is a new v0 interpretation of the brief, not a project-wide integration.

The implementation contract is documented in [`maze_spec.md`](maze_spec.md). It records the state/action/termination contracts, reward arithmetic, shield fallback, regression expectations, and the **temporary** team decisions that must be revisited before the final freeze.

## State (`MazeState`)

| Field | Type/range | Meaning |
|---|---|---|
| `turn` | integer, `0..max_turns` | Number of actions taken |
| `intel` | integer, `0..3` | Abstract evidence accumulated |
| `exposure` | integer, `0..3` | Investigator/operation exposure risk |
| `alert` | integer, `0..3` | Adversary suspicion/alertness |
| `progress` | integer, `0..3` | Progress toward actionable attribution |
| `contained` | binary integer | Successful containment achieved |

Observation vector ordering is `[intel, exposure, alert, progress, turn, contained]`; Gymnasium observation space is `MultiDiscrete`. `MazeState` fields are frozen, validated by the transition rules, and fully represented by the observation.

## Actions and v0 transition/rule table

Action indices are stable and exact: `0 OBSERVE`, `1 DEEPEN`, `2 LURE`, `3 SLOW`, `4 CONTAIN`.

| Action | Transition and intent |
|---|---|
| OBSERVE | Intel +1 (cap 3); low-risk evidence gathering. Reward bonus only if intel actually increased. |
| DEEPEN | If intel >=1, progress +1 (cap 3); exposure +1 and alert +1. |
| LURE | If intel >=2, progress +1 (cap 3); alert +1. |
| SLOW | Alert -1 and exposure -1 (floor 0); defensive risk reduction. |
| CONTAIN | Succeeds if intel >=2 and progress >=2, setting `contained=1`; otherwise alert +1. |

### Shield rules

`action_mask()` returns a five-entry integer boolean mask in action-index order. The shield disallows DEEPEN at exposure >=2; disallows LURE at alert >=2 or exposure >=2; and disallows repeat CONTAIN after success. `step()` is fail-safe: a masked requested action is converted to OBSERVE, recorded as `executed_action`, and identified by `shielded=True`. Successful containment terminates; exposure >=3 or alert >=3 terminates as failure. Otherwise turn limit truncates the episode. Stepping after an episode ends raises `RuntimeError`.

## Reward draft (abstract points per transition)

Rewards are **abstract points**, not monetary amounts or calibrated utility. Each step starts at -0.1. OBSERVE adds +0.5 only when intel actually increases (no bonus once intel is capped at 3); progress gained adds +1.0; each exposure increment costs -0.8; each alert increment costs -0.5; successful containment adds +3.0; failed containment adds -1.0; terminal success adds +5.0; terminal failure adds -5.0; time-limit truncation adds 0.0. Consequently, a failed containment also incurs its alert penalty. No reward is intended as an operational cyber utility metric.

## Assumptions and limitations

- “Maze” is interpreted as a finite-horizon abstract decision process, not a spatial grid: the brief supplied no map, adversary model, or telemetry contract.
- Dynamics are deterministic; no hidden state, stochastic transitions, external tools, or real-world side effects exist.
- Evidence is sufficient for containment at intel/progress thresholds 2/2. A risk meter reaching 3 is catastrophic; the shield only blocks specified unsafe actions, and does not guarantee survival from every state.
- `reset(seed=...)` honors Gymnasium API but seed has no effect because dynamics are deterministic.
- The rule table and reward magnitudes are explicit v0 design choices; they should be reviewed against any eventual authoritative A3 source.

## Install, run, test

```bash
python -m pip install -e '.[test]'
pytest
```

```python
from maze_env import MazeEnv, Action
from policy import choose_action

env = MazeEnv()
obs, info = env.reset(seed=7)
action = choose_action(obs, info['action_mask'])
obs, reward, terminated, truncated, info = env.step(action)
```

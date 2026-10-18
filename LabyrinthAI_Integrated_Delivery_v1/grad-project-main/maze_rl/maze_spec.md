# A3 Maze Specification v0

**Status:** **PROVISIONAL / TEMPORARY APPROVAL.** The state machine is implemented and tested. The values below are temporary working values so the team can proceed; the A3 owner may revise them later without treating this file as the final frozen specification.

## 1. Scope

A3 is a deterministic, abstract cyber-deception investigation environment. It does not perform network activity, call external services, or model a real attacker. It consumes a typed initial state (optionally produced by an A2 adapter) and an optional scenario context (for example, A4 lure identifiers).

## 2. State

`MazeState` is the immutable state record:

| Field | Meaning | Valid range |
|---|---|---|
| `turn` | Number of transitions already executed | `0 <= turn <= max_turns`; reset requires `< max_turns` |
| `intel` | Investigation intelligence/evidence level | integer `0..3` |
| `exposure` | Exposure/risk meter | integer `0..3` |
| `alert` | Adversary alert meter | integer `0..3` |
| `progress` | Investigation/containment progress | integer `0..3` |
| `contained` | Successful containment flag | integer `0..1` |

Boolean values are not accepted as substitutes for integer state values. A reset state must be live: `turn < max_turns`, `contained == 0`, `exposure < 3`, and `alert < 3`.

## 3. Observation contract

The observation is an `int64` NumPy vector in this fixed order:

```text
[intel, exposure, alert, progress, turn, contained]
```

The Gymnasium observation space is:

```python
MultiDiscrete([4, 4, 4, 4, max_turns + 1, 2])
```

Every returned observation must satisfy `observation_space.contains(observation)`, including the last live turn.

## 4. Actions

The action space is `Discrete(5)` in this fixed order:

| ID | Action | Intended effect |
|---:|---|---|
| 0 | `OBSERVE` | Increase `intel` by one, capped at 3 |
| 1 | `DEEPEN` | Increase `progress` only when intel is available; increase exposure and alert |
| 2 | `LURE` | Increase alert; increase progress only when intel is at least 2 |
| 3 | `SLOW` | Reduce alert and exposure by one, floored at zero |
| 4 | `CONTAIN` | Succeed only when `intel >= 2` and `progress >= 2`; otherwise increase alert |

All meters are capped/floored by the transition function and never leave their declared ranges.

## 5. Action shield

The shield returns a five-element binary mask in action order:

- `DEEPEN` is disallowed when `exposure >= 2`.
- `LURE` is disallowed when `alert >= 2` or `exposure >= 2`.
- `CONTAIN` is disallowed after containment (`contained == 1`).
- Other actions remain allowed for a live state.

If a caller requests a masked action, the environment executes `OBSERVE`, sets `info["shielded"] = True`, and records both `requested_action` and `executed_action`. This fallback is the **temporary v0 policy** and may be revised later.

## 6. Rewards

The implementation currently uses these additive terms:

```python
{
    "step": -0.1,
    "intel": 0.5,
    "progress": 1.0,
    "exposure": -0.8,
    "alert": -0.5,
    "contain_success": 3.0,
    "contain_failure": -1.0,
    "success_terminal": 5.0,
    "failure_terminal": -5.0,
    "truncation": 0.0,
}
```

`OBSERVE` receives the `intel` bonus only when it increases intel. **Temporary values:** from the default state its reward is `-0.1 + 0.5 = 0.4`; when intel is already capped it is `-0.1`. The tested successful containment route has a total reward of `8.7`. These values are intentionally provisional and can be changed in a later reward-tuning pass; when they change, update `REWARDS`, this section, and the regression tests together.

## 7. Termination and truncation

After each transition:

- `terminated=True` for successful containment (`contained == 1`).
- `terminated=True` for failure when `exposure >= 3` or `alert >= 3`.
- `truncated=True` when the turn limit is reached without termination.
- A terminal/truncated episode rejects another `step()` and requires `reset()`.

A reset with a terminal or exhausted initial state is rejected rather than returning an already-ended episode.

## 8. Reset and scenario input

`reset(options=...)` accepts only a dictionary with optional `state` and `scenario` keys. `state` is a mapping of `MazeState` fields or a `MazeState` instance. `scenario` must be a dictionary and is copied at the top level. Unknown keys, wrong types, out-of-range values, terminal states, and exhausted states are rejected.

## 9. Temporary team decision

For the current integration milestone, the team is using the following temporary decisions:

1. The state fields and their ranges are accepted provisionally.
2. The five action meanings and shield fallback to `OBSERVE` are accepted provisionally.
3. Terminal/truncation semantics are accepted provisionally.
4. The current reward constants and the `8.7` successful route total are accepted provisionally. The previously discussed `OBSERVE=0.3` target is **not** applied yet because it would require a coordinated reward retuning.
5. Shallow top-level scenario copying is accepted provisionally; deep immutability can be introduced later if the adapter contract requires it.

These are working assumptions, not a permanent signature. Replace this section with the owner's final approval and freeze the reward table before the final field submission.

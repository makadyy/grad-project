"""Deterministic abstract cyber-deception investigation maze (A3)."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Any
import gymnasium as gym
from gymnasium import spaces
import numpy as np


class Action(IntEnum):
    OBSERVE = 0
    DEEPEN = 1
    LURE = 2
    SLOW = 3
    CONTAIN = 4


@dataclass(frozen=True)
class MazeState:
    """Compact Markov state; all meters except turn are integers in [0, 3]."""
    turn: int = 0
    intel: int = 0
    exposure: int = 0
    alert: int = 0
    progress: int = 0
    contained: int = 0


# Reward units are abstract points per transition, not dollars or calibrated utility.
REWARDS = {"step": -0.1, "intel": 0.5, "progress": 1.0,
           "exposure": -0.8, "alert": -0.5, "contain_success": 3.0,
           "contain_failure": -1.0, "success_terminal": 5.0,
           "failure_terminal": -5.0, "truncation": 0.0}
MAX_TURNS = 12


class MazeEnv(gym.Env):
    """A reproducible investigation maze with an action shield.

    The hidden adversary is represented abstractly by intel/progress thresholds;
    there is no network, real cyber activity, randomness, or external service.
    """
    metadata = {"render_modes": []}
    ACTION_NAMES = tuple(a.name for a in Action)

    def __init__(self, max_turns: int = MAX_TURNS):
        super().__init__()
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        self.max_turns = int(max_turns)
        self.action_space = spaces.Discrete(len(Action))
        # Fixed ordering: intel, exposure, alert, progress, turn, contained.
        self.observation_space = spaces.MultiDiscrete([4, 4, 4, 4, self.max_turns + 1, 2])
        self.state = MazeState()
        self._terminated = False
        self._truncated = False

    def _observation(self) -> np.ndarray:
        s = self.state
        return np.asarray([s.intel, s.exposure, s.alert, s.progress, s.turn, s.contained], dtype=np.int64)

    def action_mask(self) -> np.ndarray:
        """Boolean legal-action mask in Action order; shield disallows unsafe moves."""
        s = self.state
        mask = np.ones(len(Action), dtype=np.int8)
        # Deep investigation risks exposure when already at exposure 2+.
        if s.exposure >= 2:
            mask[Action.DEEPEN] = 0
        # Lures are unsafe at high alert or if exposure is already critical.
        if s.alert >= 2 or s.exposure >= 2:
            mask[Action.LURE] = 0
        # Never permit a second containment attempt.
        if s.contained:
            mask[Action.CONTAIN] = 0
        return mask

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        if options is None:
            options = {}
        if not isinstance(options, dict) or set(options) - {"state", "scenario"}:
            raise ValueError("reset options may contain only 'state' and 'scenario'")
        initial = options.get("state", {})
        if isinstance(initial, MazeState):
            initial = asdict(initial)
        if not isinstance(initial, dict) or set(initial) - set(MazeState.__dataclass_fields__):
            raise ValueError("state must be a mapping of MazeState fields")
        state = MazeState(**initial)
        values = asdict(state)
        for name in ("turn", "intel", "exposure", "alert", "progress", "contained"):
            value = values[name]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"state.{name} must be an integer")
            maximum = self.max_turns if name == "turn" else (1 if name == "contained" else 3)
            if value < 0 or value > maximum:
                raise ValueError(f"state.{name} must be in [0, {maximum}]")
        # A start state must be a live, non-terminal state: otherwise the first
        # step() would leave the observation space (turn == max_turns + 1) or
        # begin an episode that has already ended.
        if state.turn >= self.max_turns:
            raise ValueError(f"state.turn must be < max_turns ({self.max_turns}) at reset")
        if state.contained:
            raise ValueError("state.contained must be 0 at reset (terminal state)")
        if state.exposure >= 3 or state.alert >= 3:
            raise ValueError("exposure/alert must be < 3 at reset (terminal state)")
        scenario = options.get("scenario", {})
        if not isinstance(scenario, dict):
            raise ValueError("scenario must be a mapping")
        self.state = state
        self._scenario = dict(scenario)
        self._terminated = self._truncated = False
        info = {"action_mask": self.action_mask(), "state": asdict(self.state), "scenario": dict(self._scenario)}
        return self._observation(), info

    def step(self, action: int):
        if self._terminated or self._truncated:
            raise RuntimeError("episode ended; call reset() before step()")
        if not self.action_space.contains(action):
            raise ValueError(f"action must be an integer in [0, {len(Action)-1}]")
        requested = Action(int(action))
        mask_before = self.action_mask()
        executed = requested if mask_before[requested] else Action.OBSERVE
        s = self.state
        turn, intel, exposure, alert, progress = s.turn + 1, s.intel, s.exposure, s.alert, s.progress
        contained = s.contained
        reward = REWARDS["step"]
        if executed == Action.OBSERVE:
            intel = min(3, intel + 1)
            # Pay the evidence bonus only for NEW evidence (no reward farming once intel is capped).
            reward += REWARDS["intel"] * (intel > s.intel)
        elif executed == Action.DEEPEN:
            progress = min(3, progress + (1 if intel >= 1 else 0))
            exposure = min(3, exposure + 1)
            alert = min(3, alert + 1)
            reward += REWARDS["progress"] * (progress > s.progress) + REWARDS["exposure"] + REWARDS["alert"]
        elif executed == Action.LURE:
            alert = min(3, alert + 1)
            progress = min(3, progress + (1 if intel >= 2 else 0))
            reward += REWARDS["progress"] * (progress > s.progress) + REWARDS["alert"]
        elif executed == Action.SLOW:
            alert = max(0, alert - 1)
            exposure = max(0, exposure - 1)
        elif executed == Action.CONTAIN:
            if intel >= 2 and progress >= 2:
                contained = 1
                reward += REWARDS["contain_success"]
            else:
                alert = min(3, alert + 1)
                reward += REWARDS["contain_failure"]
        self.state = MazeState(turn, intel, exposure, alert, progress, contained)
        terminated = bool(contained or exposure >= 3 or alert >= 3)
        truncated = bool(not terminated and turn >= self.max_turns)
        if contained:
            reward += REWARDS["success_terminal"]
        elif terminated:
            reward += REWARDS["failure_terminal"]
        elif truncated:
            reward += REWARDS["truncation"]
        self._terminated, self._truncated = terminated, truncated
        info = {"requested_action": requested.name, "executed_action": executed.name,
                "shielded": requested != executed, "action_mask": self.action_mask(),
                "state": asdict(self.state), "scenario": dict(self._scenario), "success": bool(contained),
                "termination_reason": "contained" if contained else ("exposure" if exposure >= 3 else ("alert" if alert >= 3 else None))}
        return self._observation(), float(reward), terminated, truncated, info

    def render(self):
        return f"MazeState({self.state})"

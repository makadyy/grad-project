"""Tested deterministic v0 rule policy for MazeEnv."""
from typing import Sequence
from game import Action


def choose_action(observation: Sequence[int], action_mask: Sequence[int]) -> Action:
    """Rules: contain with evidence; acquire evidence; control risk; then progress.

    Masking is authoritative: unsafe preference falls back to the first legal
    action in conservative order OBSERVE, SLOW, CONTAIN, LURE, DEEPEN.
    """
    intel, exposure, alert, progress = (int(x) for x in observation[:4])
    legal = [bool(x) for x in action_mask]
    if len(legal) != len(Action) or not any(legal):
        raise ValueError("action_mask must have five entries and at least one legal action")
    if intel >= 2 and progress >= 2 and legal[Action.CONTAIN]:
        preferred = Action.CONTAIN
    elif exposure >= 2 or alert >= 2:
        preferred = Action.SLOW
    elif intel < 2:
        preferred = Action.OBSERVE
    elif progress < 2 and exposure < 2:
        preferred = Action.DEEPEN if progress == 0 else Action.LURE
    else:
        preferred = Action.OBSERVE
    if legal[preferred]:
        return preferred
    for candidate in (Action.OBSERVE, Action.SLOW, Action.CONTAIN, Action.LURE, Action.DEEPEN):
        if legal[candidate]:
            return candidate
    raise AssertionError("unreachable")

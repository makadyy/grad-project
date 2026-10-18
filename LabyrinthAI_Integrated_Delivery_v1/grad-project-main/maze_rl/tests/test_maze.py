import pytest
from maze_env import Action, MazeEnv
from policy import choose_action


def test_reset_shape_mask_and_repeatable_episode():
    env = MazeEnv()
    obs, info = env.reset(seed=4)
    assert obs.tolist() == [0, 0, 0, 0, 0, 0]
    assert env.observation_space.contains(obs)
    assert info["action_mask"].tolist() == [1, 1, 1, 1, 1]
    a = env.step(Action.OBSERVE)
    env.reset(seed=99)
    b = env.step(Action.OBSERVE)
    assert a[0].tolist() == b[0].tolist() and a[1:4] == b[1:4]


def test_shield_rejects_unsafe_action_and_safe_fallback():
    env = MazeEnv()
    env.reset()
    env.step(Action.OBSERVE)  # intel 1
    env.step(Action.DEEPEN)   # exposure 1, alert 1
    env.step(Action.DEEPEN)   # exposure 2, alert 2
    assert env.action_mask().tolist() == [1, 0, 0, 1, 1]
    obs, reward, terminated, truncated, info = env.step(Action.DEEPEN)
    assert info["requested_action"] == "DEEPEN"
    assert info["executed_action"] == "OBSERVE" and info["shielded"]
    assert obs.tolist() == [2, 2, 2, 2, 4, 0]
    assert not terminated and not truncated


def test_rule_policy_respects_shield_and_containment_succeeds():
    env = MazeEnv()
    obs, info = env.reset()
    actions = []
    while True:
        action = choose_action(obs, info["action_mask"])
        actions.append(action)
        obs, _, term, trunc, info = env.step(action)
        assert not info["shielded"]
        if term or trunc:
            break
    assert actions == [Action.OBSERVE, Action.OBSERVE, Action.DEEPEN, Action.LURE, Action.CONTAIN]
    assert term and not trunc and info["success"]
    assert info["termination_reason"] == "contained"
    assert env.action_mask()[Action.CONTAIN] == 0
    with pytest.raises(RuntimeError):
        env.step(Action.OBSERVE)


def test_risk_failure_and_time_limit_truncation():
    env = MazeEnv()
    env.reset()
    env.step(Action.DEEPEN)
    env.step(Action.DEEPEN)
    _, _, term, trunc, info = env.step(Action.DEEPEN)  # shield maps to observe, so not fatal
    assert not term and not trunc and info["shielded"]
    # Use a fresh state path where containment fails and alert reaches three.
    env.reset()
    env.step(Action.OBSERVE)
    env.step(Action.DEEPEN)
    env.step(Action.DEEPEN)
    _, _, term, trunc, info = env.step(Action.CONTAIN)  # disallowed only if already contained
    assert term and not trunc and info["termination_reason"] == "alert"
    short = MazeEnv(max_turns=1)
    short.reset()
    _, _, term, trunc, info = short.step(Action.OBSERVE)
    assert not term and trunc and info["termination_reason"] is None
    with pytest.raises(RuntimeError):
        short.step(Action.OBSERVE)


def test_action_validation_and_mask_validation():
    env = MazeEnv()
    env.reset()
    with pytest.raises(ValueError):
        env.step(7)
    with pytest.raises(ValueError):
        choose_action([0, 0, 0, 0], [0, 0, 0, 0, 0])


def test_feature_driven_initial_state_and_scenario_metadata():
    env = MazeEnv()
    obs, info = env.reset(options={
        "state": {"intel": 2, "exposure": 1, "alert": 0, "progress": 2},
        "scenario": {"company": "synthetic-world", "honey_lures": ["H04"]},
    })
    assert obs.tolist() == [2, 1, 0, 2, 0, 0]
    assert info["scenario"]["honey_lures"] == ["H04"]
    action = choose_action(obs, info["action_mask"])
    assert action == Action.CONTAIN
    _, _, terminated, truncated, after = env.step(action)
    assert terminated and not truncated and after["scenario"]["company"] == "synthetic-world"


@pytest.mark.parametrize("state", [
    {"intel": 4}, {"turn": -1}, {"contained": 2}, {"alert": True}, {"missing": 1},
])
def test_invalid_initial_state_rejected(state):
    with pytest.raises(ValueError):
        MazeEnv().reset(options={"state": state})


@pytest.mark.parametrize("state", [
    {"turn": 12}, {"contained": 1}, {"alert": 3}, {"exposure": 3},
])
def test_terminal_or_exhausted_initial_state_rejected(state):
    with pytest.raises(ValueError):
        MazeEnv().reset(options={"state": state})


@pytest.mark.parametrize("options", [[], "", 0, {"state": []}, {"state": ""}, {"scenario": []}])
def test_wrong_type_or_empty_options_rejected(options):
    with pytest.raises(ValueError):
        MazeEnv().reset(options=options)


def test_observation_always_inside_space_from_last_live_turn():
    env = MazeEnv()
    for action in Action:
        obs, _ = env.reset(options={"state": {"turn": 11}})
        obs, _, _, _, _ = env.step(int(action))
        assert env.observation_space.contains(obs)
        assert obs[4] <= env.max_turns


def test_observe_bonus_only_when_intel_increases():
    env = MazeEnv()
    env.reset(options={"state": {"intel": 3}})
    _, reward, _, _, _ = env.step(Action.OBSERVE)
    assert reward == pytest.approx(-0.1)  # capped intel: step cost only
    env.reset()
    _, reward, _, _, _ = env.step(Action.OBSERVE)
    assert reward == pytest.approx(0.4)   # intel 0 -> 1: +0.5 - 0.1

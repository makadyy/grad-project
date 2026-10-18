import pytest
from gymnasium.utils.env_checker import check_env

from maze_env import Action, MazeEnv


def test_gymnasium_contract():
    """The environment must satisfy Gymnasium's reset/step contract."""
    check_env(MazeEnv())


def test_observe_has_no_repeatable_reward_at_intel_cap():
    env = MazeEnv()
    env.reset(options={"state": {"intel": 3}})
    _, reward, terminated, truncated, _ = env.step(Action.OBSERVE)
    assert reward == pytest.approx(-0.1)
    assert not terminated and not truncated


def test_successful_containment_route_total_reward_is_8_7():
    """Regression test for the agreed v0 route, including the terminal reward."""
    env = MazeEnv()
    env.reset()
    rewards = []
    for action in [Action.OBSERVE, Action.OBSERVE, Action.DEEPEN, Action.LURE, Action.CONTAIN]:
        _, reward, terminated, truncated, info = env.step(action)
        rewards.append(reward)
    assert rewards == pytest.approx([0.4, 0.4, -0.4, 0.4, 7.9])
    assert sum(rewards) == pytest.approx(8.7)
    assert terminated and not truncated
    assert info["success"] is True
    assert info["termination_reason"] == "contained"


def test_shield_records_requested_and_executed_action():
    env = MazeEnv()
    env.reset()
    env.step(Action.OBSERVE)
    env.step(Action.DEEPEN)
    env.step(Action.DEEPEN)
    _, reward, terminated, truncated, info = env.step(Action.DEEPEN)
    assert info["shielded"] is True
    assert info["requested_action"] == "DEEPEN"
    assert info["executed_action"] == "OBSERVE"
    assert reward == pytest.approx(0.4)
    assert not terminated and not truncated


def test_slow_reduces_risk_without_underflow():
    env = MazeEnv()
    env.reset(options={"state": {"exposure": 0, "alert": 0}})
    _, _, _, _, info = env.step(Action.SLOW)
    assert info["state"]["exposure"] == 0
    assert info["state"]["alert"] == 0


def test_all_transition_meters_stay_in_declared_ranges():
    env = MazeEnv()
    env.reset(options={"state": {"intel": 3, "exposure": 2, "alert": 2, "progress": 3}})
    for action in Action:
        if env._terminated or env._truncated:
            break
        obs, _, terminated, truncated, _ = env.step(action)
        assert env.observation_space.contains(obs)
        assert all(0 <= int(v) <= 3 for v in obs[:4])
        assert 0 <= int(obs[4]) <= env.max_turns
        assert int(obs[5]) in (0, 1)
        if terminated or truncated:
            break


def test_episode_requires_reset_after_termination():
    env = MazeEnv()
    env.reset(options={"state": {"intel": 2, "progress": 2}})
    _, _, terminated, truncated, _ = env.step(Action.CONTAIN)
    assert terminated and not truncated
    with pytest.raises(RuntimeError, match="call reset"):
        env.step(Action.OBSERVE)

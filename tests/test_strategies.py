"""전략 규칙과 파산·중단 조건."""

import numpy as np
import pytest

from simcore import SimSpec, Strategy, chunk_rng, simulate_gamblers
from simcore.money import CENTS


def test_martingale_doubles_after_loss_and_resets_after_win():
    s = Strategy("martingale", base_bet=2)
    amount = np.array([2, 8, 8, 16])
    net = np.array([-100, -100, 95, 0])
    assert s.next_stake(amount, net).tolist() == [4, 16, 2, 16]


def test_flat_always_bets_base():
    s = Strategy("flat", base_bet=3)
    assert s.next_stake(np.array([3, 3]), np.array([-100, 100])).tolist() == [3, 3]


def test_amount_respects_table_limit_and_bankroll():
    s = Strategy("martingale", table_limit=100)
    stake = np.array([64, 128, 128])
    affordable = np.array([1_000, 1_000, 50])
    assert s.amounts(stake, affordable).tolist() == [64, 100, 50]


def test_ruined_gamblers_lost_everything():
    """빨강 1칩 고정 베팅은 잔고가 1칩 단위라서, 파산한 사람은 정확히 시작 자금을 다 잃은 사람이다."""
    spec = SimSpec("roulette_red", Strategy("flat"), bankroll=20, rounds=5_000, gamblers=5_000, seed=1)
    out = simulate_gamblers(spec, spec.gamblers, chunk_rng(spec.seed, 0))
    assert out.ruined.mean() > 0.5
    assert (out.profit[out.ruined] == -20 * CENTS).all()
    assert (out.rounds <= spec.rounds).all()


def test_stop_win_stops_at_target():
    spec = SimSpec("roulette_red", Strategy("flat", stop_win=5), bankroll=100, rounds=1_000, gamblers=5_000, seed=2)
    out = simulate_gamblers(spec, spec.gamblers, chunk_rng(spec.seed, 0))
    reached = out.profit == 5 * CENTS
    assert out.profit.max() == 5 * CENTS
    assert reached.any()
    assert (out.rounds[reached] < spec.rounds).any()


@pytest.mark.parametrize(
    "bad",
    [
        Strategy("kelly"),
        Strategy("flat", base_bet=0),
        Strategy("martingale", base_bet=10, table_limit=5),
    ],
)
def test_invalid_strategy_is_rejected(bad):
    with pytest.raises(ValueError):
        bad.validate()

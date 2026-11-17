"""정확성: 시뮬레이션 결과가 확률 이론과 맞는지 99% 신뢰구간으로 확인한다."""

import math

import pytest

from simcore import BETS, SimSpec, Strategy, chunk_rng, simulate_gamblers
from simcore.money import CENTS

Z99 = 2.576


@pytest.mark.parametrize(
    ("key", "edge"),
    [
        ("roulette_single", -1 / 37),
        ("roulette_red", -1 / 37),
        ("baccarat_banker", -0.010579),
        ("baccarat_player", -0.012350),
        ("baccarat_tie", -0.143596),
        ("dice_six", -1 / 6),
    ],
)
def test_house_edge_of_each_bet(key, edge):
    assert BETS[key].edge == pytest.approx(edge, abs=1e-6)


@pytest.mark.parametrize("key", sorted(BETS))
def test_flat_bet_matches_theory(key):
    """파산이 없는 고정 베팅: 평균 = 판 수 × 엣지, 표준편차 = √(판 수 × 분산)."""
    game = BETS[key]
    rounds, n = 200, 20_000
    spec = SimSpec(key, Strategy("flat"), bankroll=10_000, rounds=rounds, gamblers=n, seed=20261117)
    out = simulate_gamblers(spec, n, chunk_rng(spec.seed, 0))

    assert not out.ruined.any()
    assert (out.rounds == rounds).all()
    profit = out.profit / CENTS
    sd = math.sqrt(rounds * game.variance)
    assert abs(profit.mean() - rounds * game.edge) < Z99 * sd / math.sqrt(n)
    assert profit.std() == pytest.approx(sd, rel=0.05)


@pytest.mark.parametrize("key", ["roulette_red", "roulette_single", "baccarat_banker"])
def test_martingale_still_loses_the_house_edge(key):
    """어떤 전략이든 기대 수익 = 엣지 × 기대 총베팅액(Wald 등식). 마틴게일도 하우스 엣지를 못 피한다."""
    game = BETS[key]
    spec = SimSpec(key, Strategy("martingale", table_limit=500), bankroll=1_000, rounds=500, gamblers=20_000, seed=7)
    out = simulate_gamblers(spec, spec.gamblers, chunk_rng(spec.seed, 0))

    d = (out.profit - game.edge * out.wagered) / CENTS
    assert abs(d.mean()) < Z99 * d.std() / math.sqrt(d.size)

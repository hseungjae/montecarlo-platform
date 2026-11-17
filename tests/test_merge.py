"""합치기: 청크별 도수분포표를 더한 결과가 원본 값을 모아 직접 만든 것과 정확히 같아야 한다."""

import random

import numpy as np
import pytest

from simcore import SimSpec, Strategy, Summary, bin_counts, chunk_rng, plan_job, run_chunk, simulate_gamblers
from simcore.money import CENTS

SPEC = SimSpec(
    "baccarat_banker",
    Strategy("martingale", table_limit=300),
    bankroll=400,
    rounds=400,
    gamblers=30_000,
    seed=99,
)


@pytest.fixture(scope="module")
def job():
    plan = plan_job(SPEC, chunk_gamblers=7_000)
    results = [run_chunk(SPEC, plan.edges, i, n) for i, n in plan.chunks]
    raw = [simulate_gamblers(SPEC, n, chunk_rng(SPEC.seed, i)) for i, n in plan.chunks]
    return plan, results, raw


def test_merge_equals_direct_count(job):
    plan, results, raw = job
    profit = np.concatenate([r.profit for r in raw])
    merged = Summary.merge(plan.edges, results)

    assert merged.n == profit.size == SPEC.gamblers
    assert merged.counts == bin_counts(profit, plan.edges).tolist()
    assert merged.sum_profit == int(profit.astype(object).sum())
    assert merged.min_profit == profit.min()
    assert merged.max_profit == profit.max()
    assert merged.losers == int((profit < 0).sum())
    assert merged.ruined == sum(int(r.ruined.sum()) for r in raw)
    assert merged.mean == pytest.approx(profit.mean() / CENTS, rel=1e-12)
    assert merged.std == pytest.approx(profit.std() / CENTS, rel=1e-9)


def test_merge_order_does_not_matter(job):
    plan, results, _ = job
    shuffled = random.Random(0).sample(results, len(results))
    a = Summary.merge(plan.edges, results)
    b = Summary.merge(plan.edges, shuffled)
    for field in ("counts", "n", "sum_profit", "sum_sq", "min_profit", "max_profit", "losers", "ruined", "sum_wagered"):
        assert getattr(a, field) == getattr(b, field)


def test_duplicate_chunk_is_rejected(job):
    plan, results, _ = job
    with pytest.raises(ValueError, match="두 번"):
        Summary.merge(plan.edges, [*results, results[2]])


def test_partial_merge_is_a_valid_summary(job):
    """끝난 청크 일부만 합쳐도 같은 규칙으로 중간 결과를 만들 수 있다(SSE 중간 분포)."""
    plan, results, _ = job
    partial = Summary.merge(plan.edges, results[:2])
    assert partial.n == 14_000
    assert sum(partial.counts) == partial.n

"""재현성: 같은 (작업 시드, 청크 번호)면 언제 다시 계산해도 결과가 같아야 재시도가 안전하다."""

import numpy as np

from simcore import SimSpec, Strategy, plan_job, run_chunk

SPEC = SimSpec(
    "roulette_single",
    Strategy("martingale", table_limit=200),
    bankroll=500,
    rounds=300,
    gamblers=30_000,
    seed=123,
)


def test_same_chunk_gives_same_result():
    plan = plan_job(SPEC, chunk_gamblers=10_000)
    a = run_chunk(SPEC, plan.edges, 1, 10_000)
    b = run_chunk(SPEC, plan.edges, 1, 10_000)
    assert a.comparable() == b.comparable()


def test_chunks_use_independent_streams():
    plan = plan_job(SPEC, chunk_gamblers=10_000)
    a = run_chunk(SPEC, plan.edges, 0, 10_000)
    b = run_chunk(SPEC, plan.edges, 1, 10_000)
    assert a.counts != b.counts


def test_plan_is_deterministic():
    p1 = plan_job(SPEC, chunk_gamblers=7_000)
    p2 = plan_job(SPEC, chunk_gamblers=7_000)
    assert np.array_equal(p1.edges, p2.edges)
    assert p1.chunks == p2.chunks == ((0, 7_000), (1, 7_000), (2, 7_000), (3, 7_000), (4, 2_000))


def test_different_job_seed_differs():
    other = SimSpec(SPEC.bet, SPEC.strategy, SPEC.bankroll, SPEC.rounds, SPEC.gamblers, seed=124)
    plan = plan_job(SPEC, chunk_gamblers=10_000)
    assert run_chunk(SPEC, plan.edges, 0, 10_000).counts != run_chunk(other, plan.edges, 0, 10_000).counts

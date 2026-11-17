"""분산 몬테카를로 시뮬레이션 플랫폼의 계산 엔진."""

from .engine import (
    ChunkResult,
    GamblerOutcomes,
    JobPlan,
    SimSpec,
    pilot_edges,
    plan_job,
    run_chunk,
    simulate_gamblers,
)
from .games import BETS, Bet, die_bet
from .histogram import Summary, bin_counts, make_edges
from .seeding import chunk_rng, new_job_seed, pilot_rng
from .strategies import Strategy

__all__ = [
    "BETS",
    "Bet",
    "ChunkResult",
    "GamblerOutcomes",
    "JobPlan",
    "SimSpec",
    "Strategy",
    "Summary",
    "bin_counts",
    "chunk_rng",
    "die_bet",
    "make_edges",
    "new_job_seed",
    "pilot_edges",
    "pilot_rng",
    "plan_job",
    "run_chunk",
    "simulate_gamblers",
]

"""시뮬레이션 엔진: 작업 계획, 도박사 시뮬레이션, 청크 계산.

도박사 n명을 NumPy 배열로 두고 한 판씩 동시에 진행한다. 워커는 청크 하나를 받아 run_chunk()를 부르고,
그 결과(ChunkResult)만 저장한다. 도박사별 원본 값은 저장하지 않는다.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np

from .games import BETS, Bet
from .histogram import bin_counts, make_edges
from .money import CENTS
from .seeding import chunk_rng, pilot_rng
from .strategies import Strategy

MAX_ROUNDS = 100_000
MAX_BANKROLL = 10_000_000  # 칩
MAX_GAMBLERS = 10_000_000_000


@dataclass(frozen=True)
class SimSpec:
    """작업 하나의 파라미터. API가 받아서 simulation_jobs.params에 저장하는 내용과 같다."""

    bet: str
    strategy: Strategy
    bankroll: int  # 시작 자금(칩)
    rounds: int  # 도박사 1명의 최대 판 수
    gamblers: int  # 전체 도박사 수
    seed: int

    def validate(self) -> None:
        if self.bet not in BETS:
            raise ValueError(f"알 수 없는 베팅입니다: {self.bet}")
        self.strategy.validate()
        if not 1 <= self.rounds <= MAX_ROUNDS:
            raise ValueError(f"판 수는 1~{MAX_ROUNDS:,} 사이여야 합니다")
        if not 1 <= self.gamblers <= MAX_GAMBLERS:
            raise ValueError(f"도박사 수는 1~{MAX_GAMBLERS:,} 사이여야 합니다")
        if not self.strategy.base_bet <= self.bankroll <= MAX_BANKROLL:
            raise ValueError(f"시작 자금은 기본 베팅액 이상, {MAX_BANKROLL:,}칩 이하여야 합니다")
        if not 0 <= self.seed < 2**63:
            raise ValueError("시드는 0 이상 2⁶³ 미만이어야 합니다")

    @property
    def game(self) -> Bet:
        return BETS[self.bet]


@dataclass
class GamblerOutcomes:
    """도박사별 결과. 금액은 센트."""

    profit: np.ndarray
    wagered: np.ndarray
    rounds: np.ndarray
    ruined: np.ndarray


def simulate_gamblers(spec: SimSpec, n: int, rng: np.random.Generator) -> GamblerOutcomes:
    game = spec.game
    strat = spec.strategy
    cum = game.cumulative()
    payouts = np.asarray(game.payouts_pct, dtype=np.int64)
    start = spec.bankroll * CENTS
    stop_win = None if strat.stop_win is None else strat.stop_win * CENTS

    bank = np.full(n, start, dtype=np.int64)
    stake = np.full(n, strat.base_bet, dtype=np.int64)
    wagered = np.zeros(n, dtype=np.int64)
    played = np.zeros(n, dtype=np.int64)
    ruined = np.zeros(n, dtype=bool)
    idx = np.arange(n)  # 아직 게임 중인 도박사

    for _ in range(spec.rounds):
        if idx.size == 0:
            break
        amount = strat.amounts(stake[idx], bank[idx] // CENTS)
        broke = amount < strat.base_bet  # 최소 베팅액도 못 거는 사람은 파산
        if broke.any():
            ruined[idx[broke]] = True
            keep = ~broke
            idx, amount = idx[keep], amount[keep]
            if idx.size == 0:
                break
        net = payouts[np.searchsorted(cum, rng.random(idx.size), side="right")]
        bank[idx] += amount * net
        wagered[idx] += amount * CENTS
        played[idx] += 1
        stake[idx] = strat.next_stake(amount, net)
        if stop_win is not None:
            done = bank[idx] - start >= stop_win
            if done.any():
                idx = idx[~done]

    return GamblerOutcomes(profit=bank - start, wagered=wagered, rounds=played, ruined=ruined)


@dataclass
class ChunkResult:
    """청크 하나의 결과. chunk_results 테이블의 한 행과 같다. 금액은 센트."""

    chunk_index: int
    n: int
    counts: list[int]
    sum_profit: int
    sum_sq: int
    min_profit: int
    max_profit: int
    losers: int
    ruined: int
    sum_wagered: int
    rounds_played: int
    duration_ms: int

    def to_dict(self) -> dict:
        return asdict(self)

    def comparable(self) -> dict:
        """재현성 비교용: 실행 환경에 따라 달라지는 처리 시간을 뺀 값."""
        d = self.to_dict()
        d.pop("duration_ms")
        return d


def summarize_chunk(chunk_index: int, out: GamblerOutcomes, edges: np.ndarray, duration_ms: int) -> ChunkResult:
    p = out.profit
    big = p.astype(object)  # 제곱합은 int64를 넘을 수 있어 파이썬 정수로 더한다
    return ChunkResult(
        chunk_index=chunk_index,
        n=int(p.size),
        counts=[int(c) for c in bin_counts(p, edges)],
        sum_profit=int(big.sum()),
        sum_sq=int((big * big).sum()),
        min_profit=int(p.min()),
        max_profit=int(p.max()),
        losers=int((p < 0).sum()),
        ruined=int(out.ruined.sum()),
        sum_wagered=int(out.wagered.astype(object).sum()),
        rounds_played=int(out.rounds.sum()),
        duration_ms=duration_ms,
    )


def run_chunk(spec: SimSpec, edges: np.ndarray, chunk_index: int, n: int) -> ChunkResult:
    """워커가 메시지 하나를 받아 하는 일 전부. 같은 입력이면 언제나 같은 결과(처리 시간 제외)."""
    t0 = time.perf_counter()
    out = simulate_gamblers(spec, n, chunk_rng(spec.seed, chunk_index))
    return summarize_chunk(chunk_index, out, edges, round((time.perf_counter() - t0) * 1000))


@dataclass(frozen=True)
class JobPlan:
    edges: np.ndarray
    chunks: tuple[tuple[int, int], ...]  # (청크 번호, 도박사 수)


def pilot_edges(spec: SimSpec, pilot_gamblers: int = 10_000, target_bins: int = 200) -> np.ndarray:
    """작은 파일럿 실행으로 수익 범위를 보고 계급 경계를 정한다. 범위 밖 값은 넘침 칸이 받는다."""
    out = simulate_gamblers(spec, min(pilot_gamblers, spec.gamblers), pilot_rng(spec.seed))
    lo, hi = int(out.profit.min()), int(out.profit.max())
    pad = max((hi - lo) // 4, CENTS)
    lo = max(lo - pad, -spec.bankroll * CENTS)  # 시작 자금보다 많이 잃을 수는 없다
    return make_edges(lo, hi + pad, target_bins)


def plan_job(spec: SimSpec, chunk_gamblers: int, pilot_gamblers: int = 10_000) -> JobPlan:
    """API가 작업을 받을 때 하는 일: 검증, 계급 경계 고정, 청크 분할."""
    spec.validate()
    if chunk_gamblers < 1:
        raise ValueError("청크당 도박사 수는 1 이상이어야 합니다")
    edges = pilot_edges(spec, pilot_gamblers)
    full, rest = divmod(spec.gamblers, chunk_gamblers)
    sizes = [chunk_gamblers] * full + ([rest] if rest else [])
    return JobPlan(edges=edges, chunks=tuple(enumerate(sizes)))

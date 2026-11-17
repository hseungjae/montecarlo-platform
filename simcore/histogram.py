"""도수분포표: 계급 경계, 계급별 도수 세기, 청크 결과 합치기.

계급 경계는 작업을 만들 때 한 번 정하고 모든 청크가 같은 경계를 쓴다. 그래서 합치기는 같은 계급끼리
도수를 더하기만 하면 되고, 청크가 어떤 순서로 끝나든 결과가 같다. 양 끝에는 경계 밖 값을 담는
아래 넘침·위 넘침 칸을 둔다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Iterator

import numpy as np

from .money import CENTS

if TYPE_CHECKING:
    from .engine import ChunkResult


def _nice_steps() -> Iterator[int]:
    """1, 2, 5, 10, 20, 50, ..."""
    p = 1
    while True:
        for m in (1, 2, 5):
            yield m * p
        p *= 10


def nice_width(raw_cents: float) -> int:
    """계급 폭(센트). 1칩 이상이고 1·2·5 × 10ⁿ 칩 중 raw 이상인 가장 작은 값."""
    for chips in _nice_steps():
        if chips * CENTS >= raw_cents:
            return chips * CENTS
    raise AssertionError("unreachable")


def make_edges(lo: int, hi: int, target_bins: int = 200) -> np.ndarray:
    """[lo, hi]를 덮는 계급 경계. 경계는 모두 폭의 배수라서 범위에 0이 있으면 0도 경계가 된다."""
    if hi < lo:
        raise ValueError("hi는 lo 이상이어야 합니다")
    width = nice_width((hi - lo) / target_bins)
    first = (lo // width) * width
    last = (hi // width + 1) * width
    return np.arange(first, last + 1, width, dtype=np.int64)


def bin_counts(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """칸 0 = edges[0] 미만, 칸 k = [edges[k-1], edges[k]), 마지막 칸 = edges[-1] 이상."""
    idx = np.searchsorted(edges, values, side="right")
    return np.bincount(idx, minlength=len(edges) + 1)


@dataclass
class Summary:
    """여러 청크 결과를 합친 작업 결과. 금액은 센트 정수, 읽기용 속성은 칩 단위다."""

    edges: np.ndarray
    counts: list[int]
    n: int
    sum_profit: int
    sum_sq: int
    min_profit: int
    max_profit: int
    losers: int
    ruined: int
    sum_wagered: int
    rounds_played: int
    chunks: int

    @classmethod
    def merge(cls, edges: np.ndarray, results: Iterable[ChunkResult]) -> Summary:
        edges = np.asarray(edges, dtype=np.int64)
        size = len(edges) + 1
        counts = [0] * size
        seen: set[int] = set()
        n = sum_profit = sum_sq = losers = ruined = sum_wagered = rounds_played = 0
        lo = hi = None
        for r in results:
            # DB의 기본 키 (job_id, chunk_index)와 같은 규칙: 같은 청크는 한 번만 센다
            if r.chunk_index in seen:
                raise ValueError(f"청크 {r.chunk_index}가 두 번 들어왔습니다")
            if len(r.counts) != size:
                raise ValueError(f"청크 {r.chunk_index}의 계급 수가 작업과 다릅니다")
            seen.add(r.chunk_index)
            for i, c in enumerate(r.counts):
                counts[i] += c
            n += r.n
            sum_profit += r.sum_profit
            sum_sq += r.sum_sq
            losers += r.losers
            ruined += r.ruined
            sum_wagered += r.sum_wagered
            rounds_played += r.rounds_played
            lo = r.min_profit if lo is None else min(lo, r.min_profit)
            hi = r.max_profit if hi is None else max(hi, r.max_profit)
        if not seen:
            raise ValueError("합칠 청크가 없습니다")
        return cls(edges, counts, n, sum_profit, sum_sq, lo, hi, losers, ruined, sum_wagered, rounds_played, len(seen))

    # ---- 읽기용 통계 (칩 단위) ----
    @property
    def mean(self) -> float:
        return self.sum_profit / self.n / CENTS

    @property
    def std(self) -> float:
        # 분산 = (n·Σx² − (Σx)²) / n². 정수로 계산하므로 오차가 없다.
        return math.sqrt(self.n * self.sum_sq - self.sum_profit**2) / self.n / CENTS

    @property
    def loss_rate(self) -> float:
        return self.losers / self.n

    @property
    def ruin_rate(self) -> float:
        return self.ruined / self.n

    @property
    def realized_edge(self) -> float:
        """총 베팅액 대비 손익. 전략과 상관없이 하우스 엣지에 수렴한다."""
        return self.sum_profit / self.sum_wagered if self.sum_wagered else 0.0

    def _slot_bounds(self) -> list[tuple[int, int]]:
        e = [int(x) for x in self.edges]
        under = (min(self.min_profit, e[0]), e[0])
        over = (e[-1], max(self.max_profit + 1, e[-1]))
        return [under, *zip(e[:-1], e[1:]), over]

    def quantile(self, q: float) -> float:
        """도수분포표를 계급 안에서 직선 보간한 분위수(칩). 계급 폭만큼의 근사값이다."""
        if not 0 <= q <= 1:
            raise ValueError("q는 0~1 사이여야 합니다")
        target = q * self.n
        acc = 0
        value = self.max_profit
        for (lo, hi), c in zip(self._slot_bounds(), self.counts):
            if c and acc + c >= target:
                value = lo + (target - acc) / c * (hi - lo)
                break
            acc += c
        return min(max(value, self.min_profit), self.max_profit) / CENTS

    def rebinned(self, max_rows: int = 16) -> list[tuple[int, int, int]]:
        """화면용으로 계급을 묶는다. (아래 경계, 위 경계, 도수) 목록, 금액은 센트.

        묶음 폭은 저장 계급 폭의 1·2·5 × 10ⁿ배이고 경계가 그 폭의 배수라서, 0은 계속 경계로 남는다.
        """
        e = [int(x) for x in self.edges]
        width = e[1] - e[0]
        inner = self.counts[1:-1]
        rows: list[tuple[int, int, int]] = []
        if self.counts[0]:
            rows.append((self.min_profit, e[0], self.counts[0]))
        nonzero = [i for i, c in enumerate(inner) if c]
        if nonzero:
            first, last = nonzero[0], nonzero[-1]
            for k in _nice_steps():
                g = k * width
                lo_key, hi_key = e[first] // g, e[last] // g
                if hi_key - lo_key + 1 <= max_rows:
                    break
            grouped: dict[int, int] = {}
            for i in range(first, last + 1):
                key = e[i] // g
                grouped[key] = grouped.get(key, 0) + inner[i]
            rows.extend((key * g, (key + 1) * g, grouped.get(key, 0)) for key in range(lo_key, hi_key + 1))
        if self.counts[-1]:
            rows.append((e[-1], self.max_profit + 1, self.counts[-1]))
        return rows

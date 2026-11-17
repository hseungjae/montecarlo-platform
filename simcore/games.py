"""게임과 베팅 종류.

한 판의 결과를 (확률, 순배당) 목록으로 나타낸다. 순배당은 건 금액 1칩당 받는 순이익을 퍼센트 정수로
적는다. 룰렛 숫자 하나(35배)는 +3500, 지면 -100, 바카라 뱅커 승리(수수료 5%)는 +95, 비기면 0이다.
베팅은 1칩 단위이므로 '베팅 칩 수 × 순배당'이 곧 정확한 센트 정수가 된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class Bet:
    key: str
    name: str
    probs: tuple[float, ...]
    payouts_pct: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.probs) != len(self.payouts_pct):
            raise ValueError(f"{self.key}: 확률과 배당의 개수가 다릅니다")
        if any(p < 0 for p in self.probs) or abs(sum(self.probs) - 1.0) > 1e-9:
            raise ValueError(f"{self.key}: 확률은 0 이상이고 합이 1이어야 합니다")
        if min(self.payouts_pct) < -100:
            raise ValueError(f"{self.key}: 건 금액보다 많이 잃을 수는 없습니다")

    @property
    def edge(self) -> float:
        """1칩을 걸었을 때의 기대 순이익(칩). 음수면 그 크기가 하우스 엣지다."""
        return sum(p * v for p, v in zip(self.probs, self.payouts_pct)) / 100

    @property
    def variance(self) -> float:
        """1칩 베팅 한 판의 순이익 분산(칩²)."""
        second = sum(p * (v / 100) ** 2 for p, v in zip(self.probs, self.payouts_pct))
        return second - self.edge**2

    def cumulative(self) -> np.ndarray:
        cum = np.cumsum(np.asarray(self.probs, dtype=np.float64))
        cum[-1] = 1.0
        return cum


def die_bet(
    face_probs: Sequence[float],
    face: int,
    payout_pct: int = 400,
    key: str = "dice_custom",
    name: str | None = None,
) -> Bet:
    """주사위의 한 눈에 거는 베팅. 기본 배당은 5배 지급(순이익 +4칩)이다."""
    if len(face_probs) != 6 or not 1 <= face <= 6:
        raise ValueError("주사위는 눈 6개의 확률과 1~6 사이의 눈이 필요합니다")
    p = float(face_probs[face - 1])
    return Bet(key, name or f"주사위 · {face}에 걸기", (p, 1.0 - p), (payout_pct, -100))


# 바카라 확률은 8덱 기준으로 널리 쓰이는 값이다.
_BANKER, _PLAYER, _TIE = 0.458597, 0.446247, 0.095156

BETS: dict[str, Bet] = {
    b.key: b
    for b in (
        Bet("roulette_single", "유럽식 룰렛 · 숫자 하나 (35배)", (1 / 37, 36 / 37), (3500, -100)),
        Bet("roulette_red", "유럽식 룰렛 · 빨강 (1배)", (18 / 37, 19 / 37), (100, -100)),
        Bet("baccarat_banker", "바카라 · 뱅커 (수수료 5%)", (_BANKER, _PLAYER, _TIE), (95, -100, 0)),
        Bet("baccarat_player", "바카라 · 플레이어", (_PLAYER, _BANKER, _TIE), (100, -100, 0)),
        Bet("baccarat_tie", "바카라 · 타이 (8배)", (_TIE, 1 - _TIE), (800, -100)),
        die_bet([1 / 6] * 6, 6, key="dice_six", name="공정한 주사위 · 6에 걸기 (5배 지급)"),
    )
}

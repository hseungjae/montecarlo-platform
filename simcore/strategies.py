"""베팅 전략: 다음 판에 얼마를 걸지 정하는 규칙."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

KINDS = ("flat", "martingale")


@dataclass(frozen=True)
class Strategy:
    kind: str
    base_bet: int = 1  # 칩
    table_limit: int | None = None  # 한 판 최대 베팅액(칩)
    stop_win: int | None = None  # 이만큼(칩) 따면 그만둔다

    def validate(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"전략은 {', '.join(KINDS)} 중 하나여야 합니다")
        if self.base_bet < 1:
            raise ValueError("기본 베팅액은 1칩 이상이어야 합니다")
        if self.table_limit is not None and self.table_limit < self.base_bet:
            raise ValueError("테이블 한도는 기본 베팅액 이상이어야 합니다")
        if self.stop_win is not None and self.stop_win < 1:
            raise ValueError("목표 수익은 1칩 이상이어야 합니다")

    def amounts(self, stake: np.ndarray, affordable: np.ndarray) -> np.ndarray:
        """이번 판에 실제로 걸 금액: 원하는 금액, 테이블 한도, 남은 자금 중 가장 작은 값."""
        want = stake if self.table_limit is None else np.minimum(stake, self.table_limit)
        return np.minimum(want, affordable)

    def next_stake(self, amount: np.ndarray, net_pct: np.ndarray) -> np.ndarray:
        """이번 판 결과를 보고 다음 판에 걸고 싶은 금액."""
        if self.kind == "flat":
            return np.full_like(amount, self.base_bet)
        # 마틴게일: 지면 두 배, 이기면 기본액으로, 비기면 그대로
        return np.where(net_pct < 0, amount * 2, np.where(net_pct > 0, self.base_bet, amount))

    def describe(self) -> str:
        if self.kind == "flat":
            text = f"고정 베팅 {self.base_bet:,}칩"
        else:
            limit = f", 한도 {self.table_limit:,}칩" if self.table_limit else ""
            text = f"마틴게일 (기본 {self.base_bet:,}칩{limit})"
        if self.stop_win:
            text += f", {self.stop_win:,}칩 따면 중단"
        return text

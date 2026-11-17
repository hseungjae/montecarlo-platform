"""계급 경계, 넘침 칸, 분위수, 화면용 묶기."""

import numpy as np
import pytest

from simcore import bin_counts, make_edges
from simcore.histogram import Summary, nice_width
from simcore.money import CENTS


def test_nice_width_is_whole_chips_1_2_5():
    assert nice_width(1) == 100
    assert nice_width(150) == 200
    assert nice_width(3_000) == 5_000
    assert nice_width(7_100) == 10_000


def test_edges_cover_range_and_keep_zero_as_edge():
    edges = make_edges(-123_456, 45_678, target_bins=200)
    assert edges[0] <= -123_456 and edges[-1] > 45_678
    assert 0 in edges
    assert 100 <= len(edges) - 1 <= 400
    assert len(set(np.diff(edges))) == 1


def test_bin_counts_has_underflow_and_overflow_slots():
    edges = np.array([0, 100, 200])
    counts = bin_counts(np.array([-5, 0, 99, 100, 200, 999]), edges)
    assert counts.tolist() == [1, 2, 1, 2]


def _summary_from(values: np.ndarray, edges: np.ndarray) -> Summary:
    obj = values.astype(object)
    return Summary(
        edges=edges,
        counts=bin_counts(values, edges).tolist(),
        n=values.size,
        sum_profit=int(obj.sum()),
        sum_sq=int((obj * obj).sum()),
        min_profit=int(values.min()),
        max_profit=int(values.max()),
        losers=int((values < 0).sum()),
        ruined=0,
        sum_wagered=1,
        rounds_played=0,
        chunks=1,
    )


def test_quantile_is_close_to_exact():
    values = np.random.default_rng(0).integers(-50_000, 50_000, size=100_000)
    edges = make_edges(int(values.min()), int(values.max()))
    s = _summary_from(values, edges)
    width = (edges[1] - edges[0]) / CENTS
    for q in (0.05, 0.5, 0.95):
        assert s.quantile(q) == pytest.approx(np.quantile(values, q) / CENTS, abs=width)


def test_rebinned_rows_keep_every_count():
    values = np.random.default_rng(1).normal(0, 20_000, size=50_000).astype(np.int64)
    edges = make_edges(-30_000, 30_000)  # 일부러 좁게 잡아 넘침 칸이 생기게 한다
    s = _summary_from(values, edges)
    rows = s.rebinned(max_rows=12)
    assert sum(c for _, _, c in rows) == values.size
    assert len(rows) <= 12 + 2
    assert any(lo == 0 or hi == 0 for lo, hi, _ in rows)

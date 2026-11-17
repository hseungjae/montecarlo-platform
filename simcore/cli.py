"""명령줄 도구.

run   : 작업 하나를 로컬에서 끝까지 돌린다. 계획 → 청크 계산 → 합치기 순서가 Phase 1의 API·워커와 같다.
bench : 코어당 처리 속도를 재고, 청크 크기와 '1코어 1시간' 기준 작업의 크기를 계산한다.
"""

from __future__ import annotations

import argparse
import statistics
import time
import unicodedata

from .engine import SimSpec, plan_job, run_chunk, simulate_gamblers
from .games import BETS
from .histogram import Summary
from .money import CENTS
from .seeding import chunk_rng, new_job_seed
from .strategies import KINDS, Strategy


# ---- 표 정렬: 한글은 터미널에서 두 칸을 차지한다 ----
def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _ljust(s: str, n: int) -> str:
    return s + " " * max(0, n - _width(s))


def _rjust(s: str, n: int) -> str:
    return " " * max(0, n - _width(s)) + s


def _chips(cents: float) -> str:
    v = cents / CENTS
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _add_spec_args(p: argparse.ArgumentParser, gamblers: int) -> None:
    # 기본값은 기준 작업(빨강 마틴게일). 숫자 하나에 마틴게일을 걸면 대부분 30판 안에 파산해 계산량이 너무 작다.
    p.add_argument("--bet", choices=sorted(BETS), default="roulette_red")
    p.add_argument("--strategy", choices=KINDS, default="martingale")
    p.add_argument("--base-bet", type=int, default=1, help="기본 베팅액(칩)")
    p.add_argument("--table-limit", type=int, default=500, help="한 판 최대 베팅액(칩), 0이면 한도 없음")
    p.add_argument("--stop-win", type=int, default=0, help="이만큼 따면 중단(칩), 0이면 끝까지")
    p.add_argument("--bankroll", type=int, default=1_000, help="시작 자금(칩)")
    p.add_argument("--rounds", type=int, default=1_000, help="도박사 1명의 최대 판 수")
    p.add_argument("--gamblers", type=int, default=gamblers)
    p.add_argument("--seed", type=int, default=None, help="생략하면 새로 만든다")


def _spec(a: argparse.Namespace) -> SimSpec:
    strategy = Strategy(a.strategy, a.base_bet, a.table_limit or None, a.stop_win or None)
    seed = new_job_seed() if a.seed is None else a.seed
    spec = SimSpec(a.bet, strategy, a.bankroll, a.rounds, a.gamblers, seed)
    spec.validate()
    return spec


def _describe(spec: SimSpec) -> str:
    return (
        f"{spec.game.name}, {spec.strategy.describe()}\n"
        f"시작 자금 {spec.bankroll:,}칩, 최대 {spec.rounds:,}판 × {spec.gamblers:,}명, 시드 {spec.seed}"
    )


def cmd_run(a: argparse.Namespace) -> int:
    spec = _spec(a)
    t0 = time.perf_counter()
    plan = plan_job(spec, a.chunk)
    width = int(plan.edges[1] - plan.edges[0])
    print(_describe(spec))
    print(f"계급 {len(plan.edges) - 1}개 (폭 {_chips(width)}칩), 청크 {len(plan.chunks)}개\n")

    results = []
    for index, n in plan.chunks:
        r = run_chunk(spec, plan.edges, index, n)
        results.append(r)
        print(f"  청크 {index:>3}  {n:>10,}명  {r.duration_ms / 1000:7.2f}초")
    s = Summary.merge(plan.edges, results)
    elapsed = time.perf_counter() - t0

    edge = spec.game.edge
    rows = [
        ("평균 수익", f"{s.mean:+,.2f}칩"),
        ("표준편차", f"{s.std:,.2f}칩"),
        ("p5 / p50 / p95", f"{s.quantile(0.05):+,.0f} / {s.quantile(0.5):+,.0f} / {s.quantile(0.95):+,.0f}칩"),
        ("돈을 잃은 사람", f"{s.loss_rate:.1%}"),
        ("파산한 사람", f"{s.ruin_rate:.1%}"),
        ("1인당 평균 판 수", f"{s.rounds_played / s.n:,.1f}판"),
        ("총 베팅액 대비 손익", f"{s.realized_edge:+.3%}  (하우스 엣지 {edge:+.3%})"),
        ("처리", f"{s.rounds_played:,}판, {elapsed:.1f}초, {s.rounds_played / elapsed:,.0f}판/초"),
    ]
    print("\n결과")
    for k, v in rows:
        print(f"  {_ljust(k, 20)} {v}")

    print("\n최종 수익 도수분포표 (칩, 이상~미만)")
    table = s.rebinned(a.rows)
    biggest = max(c for _, _, c in table) or 1
    for lo, hi, c in table:
        label = f"{_chips(lo)} ~ {_chips(hi)}"
        bar = "█" * round(30 * c / biggest)
        print(f"  {_rjust(label, 22)}  {c:>10,}  {c / s.n:6.1%}  {bar}")
    return 0


def cmd_bench(a: argparse.Namespace) -> int:
    spec = _spec(a)
    print(_describe(spec))
    print(f"측정: 도박사 {spec.gamblers:,}명 한 묶음을 {a.repeat}번 계산\n")

    rates, per_gambler = [], []
    for i in range(a.repeat):
        t0 = time.perf_counter()
        out = simulate_gamblers(spec, spec.gamblers, chunk_rng(spec.seed, i))
        dt = time.perf_counter() - t0
        played = int(out.rounds.sum())
        rates.append(played / dt)
        per_gambler.append(dt / spec.gamblers)
        print(f"  {i + 1}회  {dt:6.2f}초  {played:>13,}판  {played / dt:>13,.0f}판/초")

    rate = statistics.median(rates)
    sec_per_gambler = statistics.median(per_gambler)
    chunk = int(a.target / sec_per_gambler)
    core_hour = int(3600 / sec_per_gambler)
    print("\n결과 (중앙값)")
    print(f"  {_ljust('코어당 처리 속도', 20)} {rate:,.0f}판/초")
    print(f"  {_ljust(f'청크 {a.target:g}초 크기', 20)} 도박사 {chunk:,}명")
    print(f"  {_ljust('1코어 1시간 기준 작업', 20)} 도박사 {core_hour:,}명 (이 설정 기준)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="simcore", description="몬테카를로 도박 시뮬레이션 엔진")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="작업 하나를 로컬에서 끝까지 실행")
    _add_spec_args(run, gamblers=200_000)
    run.add_argument("--chunk", type=int, default=50_000, help="청크당 도박사 수")
    run.add_argument("--rows", type=int, default=14, help="도수분포표 최대 줄 수")
    run.set_defaults(func=cmd_run)

    bench = sub.add_parser("bench", help="코어당 처리 속도 측정")
    _add_spec_args(bench, gamblers=100_000)
    bench.add_argument("--repeat", type=int, default=3)
    bench.add_argument("--target", type=float, default=25.0, help="목표 청크 처리 시간(초)")
    bench.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as e:
        parser.error(str(e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

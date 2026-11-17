"""금액 단위.

모든 금액은 정수 센트(1칩 = 100센트)로 계산한다. 부동소수점을 쓰면 청크를 합치는 순서에 따라
합계가 미세하게 달라지지만, 정수는 어떤 순서로 더해도 정확히 같다.
"""

CENTS = 100


def to_chips(cents: int | float) -> float:
    return cents / CENTS

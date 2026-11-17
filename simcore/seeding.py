"""난수 시드 규칙.

청크 c의 난수열은 SeedSequence(작업 시드, spawn_key=(0, c))에서 나온다. 같은 (작업 시드, 청크 번호)면
언제, 어느 파드에서 다시 계산해도 결과가 같으므로 재시도가 안전하다. 파일럿 실행은 spawn_key=(1,)을
써서 어떤 청크와도 난수열이 겹치지 않는다.

시간이나 파드 이름으로 시드를 잡으면 재시도 결과가 달라지고, 같은 시각에 뜬 파드끼리 시드가 겹칠 수 있다.
"""

from __future__ import annotations

import secrets

import numpy as np

_CHUNK, _PILOT = 0, 1


def chunk_rng(job_seed: int, chunk_index: int) -> np.random.Generator:
    if chunk_index < 0:
        raise ValueError("청크 번호는 0 이상이어야 합니다")
    return np.random.default_rng(np.random.SeedSequence(job_seed, spawn_key=(_CHUNK, chunk_index)))


def pilot_rng(job_seed: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(job_seed, spawn_key=(_PILOT,)))


def new_job_seed() -> int:
    return secrets.randbits(63)

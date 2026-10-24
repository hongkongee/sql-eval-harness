"""추출기들. 모두 같은 형식의 결과 한 줄(dict)을 낸다 (eval/extract.py, README 참고)."""

from __future__ import annotations


class ExtractError(Exception):
    """질의 하나에 대한 추출 실패. 실패 파일(<out>.failed.jsonl)에 남고, 이어하기 때 다시 시도된다."""

    def __init__(self, message: str, *, attempts: int = 1, raw: str | None = None):
        super().__init__(message)
        self.attempts = attempts
        self.raw = raw


class PreflightError(Exception):
    """실행 전에 서버가 안 떠 있는 등 진행할 수 없는 상태. 메시지를 출력하고 종료한다."""


def dedup_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out

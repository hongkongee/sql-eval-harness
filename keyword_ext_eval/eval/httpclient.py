"""재시도(지수 백오프)가 들어간 HTTP POST 헬퍼. 세 추출기가 같이 쓴다."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

import requests

# 재시도할 HTTP 상태: 과부하/일시 장애. 그 밖의 4xx(잘못된 모델명, 컨텍스트 초과 등)는
# 다시 보내도 같은 결과라 바로 실패 처리한다.
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class RequestFailed(Exception):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class Response:
    body: object
    latency_ms: float  # 마지막(성공한) 시도의 HTTP 왕복 시간
    attempts: int


def post_json(
    url: str,
    payload: dict,
    *,
    timeout: float,
    max_retries: int = 0,
    backoff_base: float = 1.0,
    headers: dict | None = None,
    post=requests.post,
    sleep=time.sleep,
) -> Response:
    """JSON POST. 타임아웃·연결 오류·RETRY_STATUS면 backoff_base * 2^n (+지터)만큼 쉬고 다시 보낸다.

    `post`/`sleep`은 테스트에서 가짜로 바꿔 끼우기 위한 인자다.
    """
    last_error = ""
    for attempt in range(1, max_retries + 2):
        start = time.perf_counter()
        try:
            resp = post(url, json=payload, timeout=timeout, headers=headers)
            latency_ms = (time.perf_counter() - start) * 1000
            if resp.status_code in RETRY_STATUS:
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            elif not resp.ok:
                raise RequestFailed(f"HTTP {resp.status_code}: {resp.text[:300]}", attempt)
            else:
                return Response(resp.json(), latency_ms, attempt)
        except requests.Timeout:
            last_error = f"timeout ({timeout}s)"
        except requests.ConnectionError as exc:
            last_error = f"connection error: {exc}"
        if attempt <= max_retries:
            sleep(backoff_base * (2 ** (attempt - 1)) * (1 + random.random() * 0.1))
    raise RequestFailed(last_error, max_retries + 1)


def check_health(base_url: str, timeout: float = 5.0) -> dict:
    """GET {base_url}/health. 실패하면 ConnectionError를 그대로 올린다."""
    resp = requests.get(base_url.rstrip("/") + "/health", timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {}

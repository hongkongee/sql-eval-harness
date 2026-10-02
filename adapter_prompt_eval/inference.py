"""원격 vLLM 서버(베이스 모델 + 여러 LoRA 체크포인트를 `--enable-lora`로 동시
서빙 중)에 OpenAI 호환 `/v1/chat/completions`로 요청을 보낸다.

automl-llm/scripts/serve_vllm.sh가 띄우는 서버는 체크포인트 하나당 모델이
따로 로드되는 게 아니라, 베이스 모델 가중치를 한 번만 올려두고 체크포인트들은
그 위에 작은 LoRA 델타로만 얹혀 있다 (README.md "GET /v1/models" 참고). 그래서
이 모듈은 로컬에서 모델을 로드하지 않고, 요청마다 `model` 필드를 체크포인트별
서빙 이름(예: `by-loss`/`final-step`/`by-adherence`, serve_vllm.sh가 등록한
이름)으로 바꿔 보내기만 하면 된다 — scripts/eval_api_model.py의 call_model과
요청 형태는 같지만, 그쪽은 system 메시지를 항상 붙이는 반면 여기는 기본값이
system 메시지 없음(없으면 아예 안 보냄)이다. 이유는 run_eval.py 상단 설명 참고
(automl-llm/scripts/compute_adherence.py가 검증 시 system 메시지 없이
instruction+input만 단일 user 메시지로 넣는 방식과 맞추기 위함).
"""
from __future__ import annotations

import time

import requests


def call_model(
    user_content: str,
    api_url: str,
    model: str,
    timeout: float,
    max_tokens: int,
    system_prompt: str | None = None,
) -> tuple[str | None, float, str | None]:
    """반환값: (응답 텍스트 또는 None, 소요 시간(초), 에러 메시지 또는 None)."""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    start = time.perf_counter()
    try:
        resp = requests.post(api_url, json=payload, timeout=timeout)
        elapsed = time.perf_counter() - start
        if not resp.ok:
            # vLLM 등은 4xx 사유(컨텍스트 초과, 등록 안 된 model 이름 등)를
            # 바디에 담아 보내는 경우가 많아 바디를 같이 넣어야 원인을 알 수 있다.
            return None, elapsed, f"{resp.status_code} {resp.reason}: {resp.text[:500]}"
        content = resp.json()["choices"][0]["message"]["content"]
        return content, elapsed, None
    except Exception as exc:  # noqa: BLE001 - API 오류는 결과 행에 그대로 기록
        elapsed = time.perf_counter() - start
        return None, elapsed, str(exc)

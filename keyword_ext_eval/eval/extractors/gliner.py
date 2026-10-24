"""비교 기준선: zero-shot GLiNER에 스키마 라벨을 직접 줘서 스키마 키워드를 뽑는다.

"사전 대신 GLiNER를 썼다면"의 기준선이다. 모델은 이 프로세스에서 돌리지 않고,
gliner-entity-router의 eval 전용 하네스(service/, POST /extract)를 HTTP로 호출한다
(`docker compose up -d entity-router` → localhost:8000, 기본 모델 urchade/gliner_multi-v2.1).
라벨과 threshold는 요청마다 보내므로 컨테이너 기본값과 무관하다.
"""

from __future__ import annotations

import os

import requests

from eval.extractors import ExtractError, PreflightError, dedup_keep_order
from eval.httpclient import RequestFailed, check_health, post_json

DEFAULT_URL = "http://localhost:8000"
DEFAULT_LABELS = ["환자 또는 대상자", "진단 행위", "처방 또는 투약 행위", "측정 또는 검사 행위"]
DEFAULT_THRESHOLD = 0.3


class GlinerExtractor:
    system = "gliner"

    def __init__(self, url: str | None = None, labels: list[str] | None = None,
                 threshold: float = DEFAULT_THRESHOLD, timeout: float = 120.0):
        self.url = (url or os.environ.get("GLINER_EXTRACT_URL") or DEFAULT_URL).rstrip("/")
        self.labels = labels or DEFAULT_LABELS
        self.threshold = threshold
        self.timeout = timeout
        self._model = None

    def preflight(self) -> None:
        try:
            health = check_health(self.url)
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            raise PreflightError(
                f"GLiNER /extract 하네스에 연결할 수 없습니다: {self.url} ({type(exc).__name__})\n"
                "  → gliner-entity-router에서 `docker compose up -d entity-router`(multi-v2.1, :8000) 또는\n"
                "    `entity-router-biomed`(:8002)를 띄우고, 주소가 다르면 GLINER_EXTRACT_URL(--gliner-url)을 지정하세요."
            ) from None
        self._model = health.get("model")

    def config(self) -> dict:
        return {"extract_url": self.url, "gliner_model": self._model,
                "labels": self.labels, "threshold": self.threshold}

    def check_config(self, cfg: dict) -> None:
        pass

    def extract(self, record: dict) -> dict:
        payload = {"text": record["text"], "labels": self.labels, "threshold": self.threshold}
        try:
            resp = post_json(self.url + "/extract", payload, timeout=self.timeout, max_retries=2)
        except RequestFailed as exc:
            raise ExtractError(str(exc), attempts=exc.attempts) from None
        entities = sorted(resp.body, key=lambda e: e["start"])
        # multi_label=True라 같은 단어가 여러 라벨로 나올 수 있다 - (단어, 라벨)별로 최고 score만 남김
        best: dict[tuple[str, str], float] = {}
        for e in entities:
            key = (e["text"], e["label"])
            best[key] = max(best.get(key, 0.0), e["score"])
        return {
            "schema_keywords": dedup_keep_order(e["text"] for e in entities),
            "schema_labels": [{"text": t, "label": l, "score": round(s, 4)} for (t, l), s in best.items()],
            "concept_spans": [],
            "latency_ms": round(resp.latency_ms, 2),
            "attempts": resp.attempts,
        }

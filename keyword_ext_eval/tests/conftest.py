"""테스트 공용: 가짜 키워드 추출 API / GLiNER /extract 서버, 고정 사전, 임시 캐시."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE = FIXTURES / "sample.jsonl"
DICT = FIXTURES / "schema_keywords.yaml"

# 가짜 API가 concept로 돌려줄 단어와 GLiNER 라벨
FAKE_CONCEPTS = {
    "수축기혈압": "검사명 또는 측정 항목",
    "본태성 고혈압": "진단명 또는 질병명",
    "이차성 고혈압": "진단명 또는 질병명",
    "심부전": "진단명 또는 질병명",
    "돌연심장사": "진단명 또는 질병명",
    "뇌졸중": "진단명 또는 질병명",
}
# 가짜 GLiNER가 스키마 라벨로 돌려줄 단어
FAKE_GLINER = {"환자": "환자 또는 대상자", "심부전 진단": "진단 행위", "측정값": "측정 또는 검사 행위",
               "방문 이력": "환자 또는 대상자"}


def _find_all(text, word):
    i = text.find(word)
    while i != -1:
        yield i, i + len(word)
        i = text.find(word, i + 1)


def fake_schema_spans(text: str) -> list[dict]:
    """테스트 전용 가짜 사전 매칭 (긴 표면형 우선). 실제 판정은 API가 한다."""
    surfaces = sorted({s for v in yaml.safe_load(DICT.read_text(encoding="utf-8")).values() for s in v},
                      key=len, reverse=True)
    taken, spans = set(), []
    for s in surfaces:
        for a, b in _find_all(text, s):
            if not taken & set(range(a, b)):
                taken |= set(range(a, b))
                spans.append({"type": "schema", "text": s, "start": a, "end": b})
    return spans


class FakeServer:
    def __init__(self, with_labels=False):
        self.with_labels = with_labels
        self.requests = []
        self.fail_texts = set()  # 이 문장이 오면 500
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/health":
                    self._send(200, {"status": "ok", "model": "fake-gliner"})
                else:
                    self._send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                server.requests.append((self.path, body))
                text = body["text"]
                if text in server.fail_texts:
                    return self._send(500, {"detail": "boom"})
                if self.path == "/keyword-extraction":
                    spans = fake_schema_spans(text)
                    for w, label in FAKE_CONCEPTS.items():
                        for a, b in _find_all(text, w):
                            s = {"type": "concept", "text": w, "start": a, "end": b, "score": 0.9}
                            if server.with_labels:
                                s["label"] = label
                            spans.append(s)
                    self._send(200, {"text": text, "spans": sorted(spans, key=lambda s: s["start"])})
                elif self.path == "/extract":
                    ents = [{"text": w, "label": l, "start": a, "end": b, "score": 0.5}
                            for w, l in FAKE_GLINER.items() if l in body["labels"] for a, b in _find_all(text, w)]
                    self._send(200, ents)
                else:
                    self._send(404, {})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def fake_server():
    with FakeServer() as s:
        yield s


@pytest.fixture
def fake_server_labels():
    with FakeServer(with_labels=True) as s:
        yield s


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """고정 사전, 임시 sql 캐시, 존재하지 않는 컨테이너 이름(docker 조회가 실제 컨테이너를 안 보게)."""
    import eval.common as common
    import eval.sql_tables as st

    # 실제 keyword_ext_eval/.env를 읽지 않도록 .env 위치를 빈 임시 폴더로
    monkeypatch.setattr(common, "ROOT_DIR", tmp_path)
    monkeypatch.setenv("SCHEMA_KEYWORDS_PATH", str(DICT))
    monkeypatch.setenv("KEYWORD_API_CONTAINER", "keyword-eval-test-no-such-container")
    monkeypatch.setattr(st, "CACHE_PATH", tmp_path / "cache" / "sql_tables.json")
    for k in ("KEYWORD_API_URL", "GLINER_EXTRACT_URL", "QWEN_BASE_URL", "QWEN_MODEL", "QWEN_API_KEY",
              "QWEN_SYSTEM_PROMPT_FILE", "QWEN_SYSTEM_PROMPT", "QWEN_PROMPT_FILE", "QWEN_MAX_TOKENS",
              "QWEN_TIMEOUT", "QWEN_MAX_RETRIES", "QWEN_CONCURRENCY", "QWEN_EXTRA_BODY"):
        monkeypatch.delenv(k, raising=False)

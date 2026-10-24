import json
import socket

import pytest
import requests

from eval import extract
from eval.common import read_jsonl
from eval.extractors import ExtractError
from eval.extractors.qwen import QwenExtractor, _MockResponse, parse_keywords
from tests.conftest import SAMPLE


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ── api ────────────────────────────────────────────────────────────────

def test_api_normal(fake_server, tmp_path):
    out = tmp_path / "api.jsonl"
    rc = extract.main(["--system", "api", "--api-url", fake_server.url, "--data", str(SAMPLE), "--out", str(out)])
    assert rc == 0
    rows = read_jsonl(out)
    assert len(rows) == 8
    r = next(x for x in rows if x["id"] == "sample:440")
    assert r["system"] == "api" and r["schema_keywords"] == ["진단", "입원", "방문", "환자"]
    assert r["concept_spans"][0]["text"] == "심부전" and r["concept_spans"][0]["label"] is None
    assert r["latency_ms"] > 0
    meta = json.loads((tmp_path / "api.meta.json").read_text())
    assert meta["config"]["api_url"] == fake_server.url
    assert meta["config"]["dict_check"].startswith("unknown")  # 테스트에선 컨테이너가 없다
    assert meta["config"]["gliner_model"]  # 서비스 settings.py 기본값


def test_api_server_down(tmp_path, capsys):
    url = f"http://127.0.0.1:{_free_port()}"
    rc = extract.main(["--system", "api", "--api-url", url, "--data", str(SAMPLE), "--out", str(tmp_path / "a.jsonl")])
    assert rc == 2
    assert "키워드 추출 API에 연결할 수 없습니다" in capsys.readouterr().err
    assert not (tmp_path / "a.jsonl").exists()


def test_api_request_failure_goes_to_failed_file_then_resume(fake_server, tmp_path):
    out = tmp_path / "api.jsonl"
    fail_text = read_jsonl(SAMPLE)[0]["text"]
    fake_server.fail_texts.add(fail_text)
    args = ["--system", "api", "--api-url", fake_server.url, "--data", str(SAMPLE), "--out", str(out)]
    assert extract.main(args) == 0
    assert len(read_jsonl(out)) == 7
    failed = read_jsonl(tmp_path / "api.failed.jsonl")
    assert [f["id"] for f in failed] == ["sample:439"] and "HTTP 500" in failed[0]["error"]
    # 서버 복구 후 다시 실행하면 실패한 1건만 처리
    fake_server.fail_texts.clear()
    n_before = len(fake_server.requests)
    assert extract.main(args) == 0
    assert len(fake_server.requests) - n_before == 1
    assert len(read_jsonl(out)) == 8 and not (tmp_path / "api.failed.jsonl").exists()


def test_resume_refuses_on_config_change(fake_server, tmp_path, monkeypatch, capsys):
    out = tmp_path / "api.jsonl"
    args = ["--system", "api", "--api-url", fake_server.url, "--data", str(SAMPLE), "--out", str(out), "--limit", "2"]
    assert extract.main(args) == 0
    # 사전이 바뀐 상황 흉내
    other = tmp_path / "dict.yaml"
    other.write_text("환자: [환자]\n", encoding="utf-8")
    monkeypatch.setenv("SCHEMA_KEYWORDS_PATH", str(other))
    assert extract.main(args) == 2
    assert "다른 설정으로 만든 결과" in capsys.readouterr().err
    assert extract.main(args + ["--overwrite"]) == 0


# ── gliner ─────────────────────────────────────────────────────────────

def test_gliner_records_labels(fake_server, tmp_path):
    out = tmp_path / "gliner.jsonl"
    rc = extract.main(["--system", "gliner", "--gliner-url", fake_server.url, "--data", str(SAMPLE), "--out", str(out)])
    assert rc == 0
    r = next(x for x in read_jsonl(out) if x["id"] == "sample:440")
    assert r["schema_keywords"] == ["심부전 진단", "환자"]
    assert {"text": "심부전 진단", "label": "진단 행위", "score": 0.5} in r["schema_labels"]
    path, body = fake_server.requests[-1]
    assert path == "/extract" and body["threshold"] == 0.3 and "처방 또는 투약 행위" in body["labels"]
    meta = json.loads((tmp_path / "gliner.meta.json").read_text())
    assert meta["config"]["gliner_model"] == "fake-gliner"


# ── qwen ───────────────────────────────────────────────────────────────

class ScriptedPost:
    """호출마다 정해진 응답(또는 예외)을 차례로 돌려주는 가짜 requests.post."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def __call__(self, url, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, content = item
        return _MockResponse(status, {"choices": [{"message": {"content": content}}]} if status == 200 else {"error": "x"})


def _qwen(post, **kw):
    return QwenExtractor(base_url="http://qwen.test/v1", model="qwen-test", post=post, sleep=lambda s: None, **kw)


REC = {"text": "발사르탄 처방 이력이 있는 환자."}
OK = json.dumps({"schema_keywords": [{"text": "처방", "table": "drug_exposure"}, {"text": "환자", "table": "person"}]})


def test_qwen_normal_and_fenced_json():
    out = _qwen(ScriptedPost([(200, "```json\n" + OK + "\n```")])).extract(REC)
    assert out["schema_keywords"] == ["처방", "환자"]
    assert out["keyword_tables"][0] == {"text": "처방", "table": "drug_exposure"}


def test_qwen_drops_words_not_in_query():
    kws, _, dropped = parse_keywords('{"schema_keywords": ["처방", "투약", "환자"]}', REC["text"])
    assert kws == ["처방", "환자"] and dropped == ["투약"]


def test_qwen_parse_failure_not_retried():
    post = ScriptedPost([(200, "처방, 환자 입니다")])
    with pytest.raises(ExtractError) as e:
        _qwen(post).extract(REC)
    assert "parse error" in str(e.value) and e.value.raw == "처방, 환자 입니다" and post.calls == 1


def test_qwen_timeout_then_retry_succeeds():
    post = ScriptedPost([requests.Timeout(), (503, ""), (200, OK)])
    out = _qwen(post).extract(REC)
    assert out["attempts"] == 3 and out["schema_keywords"] == ["처방", "환자"]


def test_qwen_retries_exhausted():
    post = ScriptedPost([requests.Timeout()] * 3)
    with pytest.raises(ExtractError) as e:
        _qwen(post, max_retries=2).extract(REC)
    assert "timeout" in str(e.value) and e.value.attempts == 3


def test_qwen_4xx_not_retried():
    post = ScriptedPost([(400, "")])
    with pytest.raises(ExtractError):
        _qwen(post).extract(REC)
    assert post.calls == 1


def test_qwen_backoff_is_exponential():
    sleeps = []
    ex = QwenExtractor(base_url="http://q/v1", model="m", post=ScriptedPost([requests.Timeout()] * 3 + [(200, OK)]),
                       sleep=sleeps.append, backoff_base=1.0)
    ex.extract(REC)
    assert [round(s) for s in sleeps] == [1, 2, 4]


def test_qwen_requires_config_without_mock(tmp_path, capsys):
    rc = extract.main(["--system", "qwen", "--data", str(SAMPLE), "--out", str(tmp_path / "q.jsonl")])
    assert rc == 2 and "QWEN_BASE_URL" in capsys.readouterr().err


def test_qwen_mock_cli_with_resume(tmp_path):
    out = tmp_path / "qwen.jsonl"
    base = ["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(out), "--concurrency", "3"]
    assert extract.main(base + ["--limit", "3"]) == 0
    assert len(read_jsonl(out)) == 3
    assert extract.main(base) == 0
    rows = read_jsonl(out)
    assert len(rows) == 8 and len({r["id"] for r in rows}) == 8
    meta = json.loads((tmp_path / "qwen.meta.json").read_text())
    assert [s["processed"] for s in meta["sessions"]] == [3, 5]
    assert meta["config"]["mock"] is True and len(meta["config"]["prompt_sha256"]) == 64


def test_qwen_failures_written_and_retried_on_resume(tmp_path, monkeypatch):
    import eval.extractors.qwen as q

    calls = {"n": 0}
    real = q.mock_post

    def flaky(url, **kwargs):
        calls["n"] += 1
        if "외래 방문" in kwargs["json"]["messages"][-1]["content"]:
            return _MockResponse(200, {"choices": [{"message": {"content": "not json"}}]})
        return real(url, **kwargs)

    monkeypatch.setattr(q, "mock_post", flaky)
    out = tmp_path / "qwen.jsonl"
    args = ["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(out)]
    assert extract.main(args) == 0
    failed = read_jsonl(tmp_path / "qwen.failed.jsonl")
    assert {f["id"] for f in failed} == {"sample:439", "sample:seed_1_test_paraphrase"}
    assert all(f["raw"] == "not json" for f in failed)
    monkeypatch.setattr(q, "mock_post", real)
    assert extract.main(args) == 0
    assert len(read_jsonl(out)) == 8


def test_api_dict_hash_mismatch_warns_or_stops(fake_server, tmp_path, monkeypatch, capsys):
    import eval.extractors.api as api

    monkeypatch.setattr(api, "container_dict_hash", lambda c: "0" * 64)
    args = ["--system", "api", "--api-url", fake_server.url, "--data", str(SAMPLE), "--limit", "1"]
    assert extract.main(args + ["--out", str(tmp_path / "a.jsonl")]) == 0
    assert "재빌드가 필요합니다" in capsys.readouterr().out
    assert extract.main(args + ["--out", str(tmp_path / "b.jsonl"), "--strict-dict"]) == 2
    assert "docker compose up -d --build keyword-extraction" in capsys.readouterr().err

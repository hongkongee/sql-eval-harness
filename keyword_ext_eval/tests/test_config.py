""".env 로딩과 Qwen 설정(모델·시스템 프롬프트·요청 옵션)."""

import json
import os

from eval import extract
from eval.common import load_dotenv, read_jsonl
from eval.extractors.qwen import QwenExtractor, _MockResponse
from tests.conftest import SAMPLE


def test_dotenv_rules_and_shell_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# 주석\nQWEN_MODEL="Flash-Next-FP8"\nQWEN_SYSTEM_PROMPT=첫 줄\\n둘째 줄\n'
                   "QWEN_API_KEY=\nQWEN_BASE_URL=http://from-dotenv/v1\n잘못된 줄\n", encoding="utf-8")
    monkeypatch.setenv("QWEN_BASE_URL", "http://from-shell/v1")
    monkeypatch.setenv("QWEN_MAX_TOKENS", "")  # 빈 값은 없는 것으로 본다
    env.write_text(env.read_text(encoding="utf-8") + "QWEN_MAX_TOKENS=256\n", encoding="utf-8")
    load_dotenv(env)
    assert os.environ["QWEN_MODEL"] == "Flash-Next-FP8"
    assert os.environ["QWEN_SYSTEM_PROMPT"] == "첫 줄\n둘째 줄"
    assert os.environ["QWEN_BASE_URL"] == "http://from-shell/v1"
    assert os.environ["QWEN_MAX_TOKENS"] == "256"


def _capture():
    sent = []

    def post(url, **kwargs):
        sent.append((url, kwargs["json"], kwargs.get("headers")))
        content = '<think>음...</think>{"schema_keywords": [{"text": "처방", "table": "drug_exposure"}]}'
        return _MockResponse(200, {"choices": [{"message": {"content": content}}]})
    return sent, post


def test_qwen_settings_from_env(tmp_path, monkeypatch):
    sysfile = tmp_path / "sys.txt"
    sysfile.write_text("확정된 시스템 프롬프트\n여러 줄", encoding="utf-8")
    monkeypatch.setenv("QWEN_BASE_URL", "http://qwen.test:8003/v1")
    monkeypatch.setenv("QWEN_MODEL", "Flash-Next-FP8")
    monkeypatch.setenv("QWEN_API_KEY", "secret")
    monkeypatch.setenv("QWEN_SYSTEM_PROMPT_FILE", str(sysfile))
    monkeypatch.setenv("QWEN_SYSTEM_PROMPT", "무시돼야 함")  # 파일이 우선
    monkeypatch.setenv("QWEN_MAX_TOKENS", "256")
    monkeypatch.setenv("QWEN_EXTRA_BODY", '{"chat_template_kwargs": {"enable_thinking": false}}')
    sent, post = _capture()
    ex = QwenExtractor(post=post)
    out = ex.extract({"text": "발사르탄 처방 이력이 있는 환자."})
    url, body, headers = sent[0]
    assert url == "http://qwen.test:8003/v1/chat/completions"
    assert body["model"] == "Flash-Next-FP8" and body["max_tokens"] == 256 and body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert headers == {"Authorization": "Bearer secret"}
    # [system, user]: 시스템은 파일 내용, 작업 지시·예시·질의는 user 쪽
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["messages"][0]["content"] == "확정된 시스템 프롬프트\n여러 줄"
    assert "규칙:" in body["messages"][1]["content"]
    assert body["messages"][1]["content"].endswith("질의: 발사르탄 처방 이력이 있는 환자.")
    assert out["schema_keywords"] == ["처방"]  # <think> 블록은 떼고 파싱
    cfg = ex.config()
    assert cfg["system_prompt_source"] == f"file:{sysfile}" and cfg["extra_body"]


def test_no_system_prompt_sends_user_only(monkeypatch):
    sent, post = _capture()
    QwenExtractor(base_url="http://q/v1", model="m", post=post).extract({"text": "처방"})
    assert [m["role"] for m in sent[0][1]["messages"]] == ["user"]


def test_system_prompt_change_stops_resume(tmp_path, monkeypatch, capsys):
    out = tmp_path / "qwen.jsonl"
    args = ["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(out), "--limit", "2"]
    monkeypatch.setenv("QWEN_SYSTEM_PROMPT", "임시 프롬프트")
    assert extract.main(args) == 0
    monkeypatch.setenv("QWEN_SYSTEM_PROMPT", "확정 프롬프트")
    assert extract.main(args) == 2
    assert "다른 설정으로 만든 결과" in capsys.readouterr().err
    meta = json.loads((tmp_path / "qwen.meta.json").read_text())
    assert meta["config"]["system_prompt_source"] == "env:QWEN_SYSTEM_PROMPT"


def test_model_change_stops_resume(tmp_path, monkeypatch):
    out = tmp_path / "qwen.jsonl"
    args = ["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(out), "--limit", "2"]
    monkeypatch.setenv("QWEN_MODEL", "Flash-Next-FP8")
    assert extract.main(args) == 0
    assert read_jsonl(out)[0]["system"] == "qwen"
    monkeypatch.setenv("QWEN_MODEL", "다른-모델")
    assert extract.main(args) == 2
    # 모델별로 결과 파일을 따로 두면 그대로 진행
    assert extract.main(args[:-4] + ["--out", str(tmp_path / "qwen_other.jsonl"), "--limit", "2"]) == 0


def test_invalid_extra_body(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("QWEN_EXTRA_BODY", "{not json")
    rc = extract.main(["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(tmp_path / "q.jsonl")])
    assert rc == 2 and "QWEN_EXTRA_BODY" in capsys.readouterr().err


def test_concurrency_default_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_CONCURRENCY", "3")
    used = {}
    import eval.extract as ex_mod
    real = ex_mod.ThreadPoolExecutor

    def spy(max_workers):
        used["n"] = max_workers
        return real(max_workers=max_workers)

    monkeypatch.setattr(ex_mod, "ThreadPoolExecutor", spy)
    assert extract.main(["--system", "qwen", "--mock", "--data", str(SAMPLE), "--out", str(tmp_path / "q.jsonl")]) == 0
    assert used["n"] == 3

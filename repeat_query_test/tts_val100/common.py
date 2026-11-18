"""공통 설정. 프롬프트 조립·요청 설정은 TTS 프로젝트 코드를 그대로 import 해서 쓴다
(따라 만든 사본이 아니라 TTS 와 같은 함수·같은 값)."""
import json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
HARNESS = ROOT.parent.parent                                   # sql-eval-harness
TTS_DIR = pathlib.Path(os.getenv("TTS_DIR", "/Users/seo/Developer/mpx-cdm-tts"))
sys.path.insert(0, str(TTS_DIR))
from app.core import config as tts_config                      # noqa: E402  NL2SQL_* 설정
from app.services.text2sql import prompt_builder               # noqa: E402  build_messages

TTS_URL = os.getenv("TTS_URL", "http://10.1.1.69:8080")         # /rag 를 부를 TTS 서버
RAG_DIR = ROOT / "rag"
REQUESTS = ROOT / "requests.json"
RESPONSES = ROOT / "responses.jsonl"


def build_request(rag_resp: dict) -> tuple[dict, dict]:
    """/rag 응답 → (LLM 요청 본문, 자리표시자 복원맵).

    TTS /nl2sql 경로와 같은 순서:
      generator.generate_sql : build_messages(materials, dialect=NL2SQL_SQL_DIALECT, mask=True)
      client.ChatClient.complete : {model, messages, max_tokens, temperature}
    materials 는 /rag 응답의 prompt(=_render_materials 결과)와 concepts(자리표시자 규칙 덧붙임 판단용).
    """
    materials = {"prompt": rag_resp["prompt"], "concepts": rag_resp.get("concepts")}
    messages, restore = prompt_builder.build_messages(
        materials, dialect=tts_config.NL2SQL_SQL_DIALECT, mask=True)
    body = {"model": tts_config.NL2SQL_MODEL, "messages": messages,
            "max_tokens": tts_config.NL2SQL_MAX_TOKENS, "temperature": tts_config.NL2SQL_TEMPERATURE}
    return body, restore


def llm_url() -> str:
    return f"{tts_config.NL2SQL_BASE_URL.rstrip('/')}/chat/completions"


def metrics_url() -> str:
    base = tts_config.NL2SQL_BASE_URL.rstrip("/")
    return (base[:-3] if base.endswith("/v1") else base) + "/metrics"


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")] if pathlib.Path(path).exists() else []

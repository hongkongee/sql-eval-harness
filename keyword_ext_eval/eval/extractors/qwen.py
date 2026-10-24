"""비교 기준선: 개발서버 Qwen(OpenAI 호환 chat completions)으로 스키마 키워드를 뽑는다.

설정은 전부 환경변수(또는 keyword_ext_eval/.env, .env.example 참고)로 받는다. 모델·서버가
바뀌어도 코드는 그대로 두고 .env만 고치면 된다.
- 접속: QWEN_BASE_URL(예: http://<서버>:<포트>/v1), QWEN_MODEL(served model name), QWEN_API_KEY(선택).
  요청 URL은 {QWEN_BASE_URL}/chat/completions. 레포의 기존 호출 코드
  (adapter_prompt_eval/inference.py)와 같은 방식(temperature 0, choices[0].message.content)이다.
- 메시지 구성: [system] + 작업 프롬프트 파일(QWEN_PROMPT_FILE, 기본 eval/prompts/qwen_schema_keywords.txt)의
  메시지들. 작업 지시·예시는 USER 쪽에 있으므로 시스템 프롬프트를 바꿔도 지시는 그대로 남는다.
- 시스템 프롬프트 우선순위: QWEN_SYSTEM_PROMPT_FILE > QWEN_SYSTEM_PROMPT(한 줄, 리터럴 \\n 허용)
  > 작업 프롬프트 파일의 ### SYSTEM > 없음. 시스템 프롬프트가 확정되기 전까지는
  eval/prompts/qwen_system_temp.txt(임시)를 .env에서 가리킨다.
- 추론(thinking) 모델이 <think>...</think>를 앞에 붙여도 떼고 파싱한다. 요청에 추가 필드가 필요하면
  QWEN_EXTRA_BODY(JSON, 예: {"chat_template_kwargs": {"enable_thinking": false}})로 넣는다.
- 타임아웃·연결 오류·429/5xx는 지수 백오프로 재시도한다. 파싱 실패는 temperature 0이라
  다시 보내도 같은 답이 나오므로 재시도하지 않고 바로 실패 처리한다.
- --mock: 서버 없이 가짜 응답(질의 속 일부 단어)을 돌려준다. 흐름 확인용.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from eval.common import EVAL_DIR, ROOT_DIR, sha256_file, sha256_text
from eval.extractors import ExtractError, PreflightError, dedup_keep_order
from eval.httpclient import RequestFailed, post_json

DEFAULT_PROMPT = EVAL_DIR / "prompts" / "qwen_schema_keywords.txt"
TABLES = {"person", "observation_period", "visit_occurrence", "condition_occurrence",
          "drug_exposure", "procedure_occurrence", "measurement", "death"}


def load_prompt(path) -> list[dict]:
    """"### ROLE" 줄로 구분된 프롬프트 파일을 chat messages 템플릿으로 읽는다."""
    messages = []
    role, buf = None, []
    for line in open(path, encoding="utf-8").read().splitlines():
        m = re.fullmatch(r"###\s*(SYSTEM|USER|ASSISTANT)\s*", line)
        if m:
            if role:
                messages.append({"role": role, "content": "\n".join(buf).strip()})
            role, buf = m.group(1).lower(), []
        else:
            buf.append(line)
    if role:
        messages.append({"role": role, "content": "\n".join(buf).strip()})
    if not messages or messages[-1]["role"] != "user" or "{text}" not in messages[-1]["content"]:
        raise ValueError(f"{path}: 마지막 메시지는 {{text}}가 들어간 ### USER여야 합니다")
    return messages


def build_messages(template: list[dict], text: str) -> list[dict]:
    msgs = [dict(m) for m in template]
    # str.format은 JSON 예시의 중괄호와 충돌하므로 replace를 쓴다
    msgs[-1]["content"] = msgs[-1]["content"].replace("{text}", text)
    return msgs


class ParseError(ValueError):
    pass


def parse_keywords(content: str, text: str) -> tuple[list[str], list[dict], list[str]]:
    """모델 응답에서 (키워드, [{text, table}], 질의에 없어서 버린 키워드)를 뽑는다."""
    s = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        raise ParseError("JSON 객체를 찾지 못함")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON 파싱 실패: {exc}") from None
    items = obj.get("schema_keywords") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise ParseError("'schema_keywords' 배열이 없음")
    pairs = []
    for it in items:
        if isinstance(it, str):
            pairs.append({"text": it.strip(), "table": None})
        elif isinstance(it, dict) and isinstance(it.get("text"), str):
            table = it.get("table")
            pairs.append({"text": it["text"].strip(), "table": table if table in TABLES else None})
        else:
            raise ParseError(f"알 수 없는 항목 형식: {it!r}")
    kept, dropped = [], []
    for p in pairs:
        if p["text"] and p["text"] in text:
            kept.append(p)
        elif p["text"]:
            dropped.append(p["text"])  # 질의에 글자 그대로 없는 단어(바꿔 말함/환각)
    keywords = dedup_keep_order(p["text"] for p in kept)
    tables = []
    seen = set()
    for p in kept:
        if p["text"] not in seen:
            seen.add(p["text"])
            tables.append(p)
    return keywords, tables, dedup_keep_order(dropped)


# ── mock ────────────────────────────────────────────────────────────────

MOCK_VOCAB = {
    "환자": "person", "연령": "person", "성별": "person", "진단": "condition_occurrence",
    "처방": "drug_exposure", "투약": "drug_exposure", "측정": "measurement", "수치": "measurement",
    "방문": "visit_occurrence", "관찰기간": "observation_period", "사망": "death", "수술": "procedure_occurrence",
    # 사전에 없는 단어 - 보강 후보 수집 흐름을 확인하기 위한 것
    "이력": "condition_occurrence", "발생": "condition_occurrence", "노출군": "drug_exposure",
}


class _MockResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._body = body
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._body


def mock_post(url, **kwargs):
    """requests.post 자리에 끼우는 가짜. 질의에 들어 있는 MOCK_VOCAB 단어를 돌려준다."""
    text = kwargs["json"]["messages"][-1]["content"].rsplit("질의:", 1)[-1].strip()
    found = [{"text": w, "table": t} for w, t in MOCK_VOCAB.items() if w in text]
    content = json.dumps({"schema_keywords": found}, ensure_ascii=False)
    return _MockResponse(200, {"choices": [{"message": {"content": content}}]})


# ── extractor ───────────────────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    return float(os.environ[name]) if os.environ.get(name) else default


def _env_int(name: str, default: int) -> int:
    return int(os.environ[name]) if os.environ.get(name) else default


def resolve_system_prompt(template: list[dict]) -> tuple[str | None, str]:
    """→ (시스템 프롬프트 또는 None, 출처 설명)."""
    path = os.environ.get("QWEN_SYSTEM_PROMPT_FILE")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = ROOT_DIR / p
        return p.read_text(encoding="utf-8").strip(), f"file:{p}"
    if os.environ.get("QWEN_SYSTEM_PROMPT"):
        return os.environ["QWEN_SYSTEM_PROMPT"], "env:QWEN_SYSTEM_PROMPT"
    sys_msgs = [m["content"] for m in template if m["role"] == "system"]
    if sys_msgs:
        return sys_msgs[0], "prompt file ### SYSTEM"
    return None, "none"


class QwenExtractor:
    system = "qwen"

    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None,
                 prompt_path=None, timeout: float | None = None, max_retries: int | None = None,
                 backoff_base: float = 1.0, max_tokens: int | None = None, mock: bool = False,
                 post=None, sleep=None):
        self.mock = mock
        self.base_url = (base_url or os.environ.get("QWEN_BASE_URL") or ("mock://qwen" if mock else "")).rstrip("/")
        self.model = model or os.environ.get("QWEN_MODEL") or ("mock-qwen" if mock else "")
        self.api_key = api_key if api_key is not None else os.environ.get("QWEN_API_KEY", "")
        prompt_path = prompt_path or os.environ.get("QWEN_PROMPT_FILE") or DEFAULT_PROMPT
        self.prompt_path = Path(prompt_path) if Path(prompt_path).is_absolute() else ROOT_DIR / prompt_path
        template = load_prompt(self.prompt_path)
        self.system_prompt, self.system_prompt_source = resolve_system_prompt(template)
        body = [m for m in template if m["role"] != "system"]
        self.template = ([{"role": "system", "content": self.system_prompt}] if self.system_prompt else []) + body
        self.timeout = timeout if timeout is not None else _env_float("QWEN_TIMEOUT", 60.0)
        self.max_retries = max_retries if max_retries is not None else _env_int("QWEN_MAX_RETRIES", 4)
        self.backoff_base = backoff_base
        self.max_tokens = max_tokens if max_tokens is not None else _env_int("QWEN_MAX_TOKENS", 512)
        extra = os.environ.get("QWEN_EXTRA_BODY")
        try:
            self.extra_body = json.loads(extra) if extra else {}
        except json.JSONDecodeError as exc:
            raise PreflightError(f"QWEN_EXTRA_BODY가 올바른 JSON이 아닙니다: {exc}") from None
        self._post = post or (mock_post if mock else None)
        self._sleep = sleep

    @property
    def url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return self.base_url + "/chat/completions"

    def preflight(self) -> None:
        missing = [n for n, v in (("QWEN_BASE_URL", self.base_url), ("QWEN_MODEL", self.model)) if not v]
        if missing:
            raise PreflightError(
                f"Qwen 접속 설정이 없습니다: {', '.join(missing)}\n"
                "  → keyword_ext_eval/.env에 채우세요 (cp .env.example .env). 또는 export로 지정.\n"
                "    서버 없이 흐름만 확인하려면 --mock을 붙이세요."
            )

    def config(self) -> dict:
        return {"base_url": self.base_url, "model": self.model, "mock": self.mock,
                "prompt_path": str(self.prompt_path), "prompt_sha256": sha256_file(self.prompt_path),
                "system_prompt_source": self.system_prompt_source,
                "system_prompt_sha256": sha256_text(self.system_prompt) if self.system_prompt else None,
                # 이어하기 판정용: 실제로 보내는 메시지 템플릿 전체(시스템 + 작업 프롬프트)의 해시
                "messages_sha256": sha256_text(json.dumps(self.template, ensure_ascii=False)),
                "temperature": 0, "max_tokens": self.max_tokens, "extra_body": self.extra_body,
                "api_key_set": bool(self.api_key)}

    def check_config(self, cfg: dict) -> None:
        if self.system_prompt_source.startswith("file:") and "qwen_system_temp" in self.system_prompt_source:
            print("[warn] 임시 시스템 프롬프트(eval/prompts/qwen_system_temp.txt)를 쓰고 있습니다. "
                  "확정되면 QWEN_SYSTEM_PROMPT_FILE을 바꾸세요.")

    def extract(self, record: dict) -> dict:
        payload = {"model": self.model, "messages": build_messages(self.template, record["text"]),
                   "temperature": 0, "max_tokens": self.max_tokens, **self.extra_body}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        kwargs = {}
        if self._post:
            kwargs["post"] = self._post
        if self._sleep:
            kwargs["sleep"] = self._sleep
        try:
            resp = post_json(self.url, payload, timeout=self.timeout, max_retries=self.max_retries,
                             backoff_base=self.backoff_base, headers=headers, **kwargs)
        except RequestFailed as exc:
            raise ExtractError(str(exc), attempts=exc.attempts) from None
        try:
            content = resp.body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ExtractError("응답에 choices[0].message.content가 없음", attempts=resp.attempts,
                               raw=str(resp.body)[:2000]) from None
        try:
            keywords, tables, dropped = parse_keywords(content, record["text"])
        except ParseError as exc:
            raise ExtractError(f"parse error: {exc}", attempts=resp.attempts, raw=content[:2000]) from None
        return {"schema_keywords": keywords, "keyword_tables": tables, "dropped_keywords": dropped,
                "concept_spans": [], "latency_ms": round(resp.latency_ms, 2), "attempts": resp.attempts}

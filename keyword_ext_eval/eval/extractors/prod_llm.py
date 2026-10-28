"""비교 기준선: 운영 환경의 프롬프트 기반 LLM 키워드 추출.

키워드 추출 API(KE-r1, KE-r2 …)와 같은 정답셋·채점기(eval.csv_keyword_eval)로 비교하려고, LLM 응답을
API와 같은 spans 형태({type, text, start, end, category})로 바꿔 저장한다.

설정은 전부 PROD_LLM_* 환경변수(keyword_ext_eval/.env)로 받는다. 개발서버 Qwen 기준선(QWEN_*,
우리가 만든 작업 프롬프트를 씀)과는 별개다. 이쪽은 **운영 프롬프트를 그대로** 보낸다.
- 접속: PROD_LLM_BASE_URL(OpenAI 호환, 요청 URL은 {BASE_URL}/chat/completions), PROD_LLM_MODEL,
  PROD_LLM_API_KEY(선택)
- 메시지: [system: 운영 시스템 프롬프트] + [user: PROD_LLM_USER_TEMPLATE의 {text}를 질의로 바꾼 것]
  - 시스템 프롬프트: PROD_LLM_SYSTEM_PROMPT_FILE > PROD_LLM_SYSTEM_PROMPT(한 줄, 리터럴 \\n 허용)
  - 사용자 메시지 템플릿 기본값은 "{text}" (질의만 보냄). 운영에서 감싸는 문구가 있으면 그대로 옮긴다.
- 요청 옵션: PROD_LLM_TEMPERATURE(기본 0), PROD_LLM_MAX_TOKENS, PROD_LLM_TIMEOUT, PROD_LLM_MAX_RETRIES,
  PROD_LLM_EXTRA_BODY(JSON, 요청 본문에 합침)

응답 해석 (운영 출력 형식이 정해지면 그에 맞는지 tests/test_prod_llm.py에 예시를 추가해 확인할 것):
- <think>…</think>, ```json 코드 펜스는 떼고 첫 JSON 객체(또는 배열)를 읽는다.
- 운영 프롬프트 형식 [{"keyword", "label", "table"}] 배열: label이 EVENT/ATTRIBUTE/ENTITY면 schema,
  VALUE/OPERATOR/TIME이면 other(채점 제외), 나머지(DISEASE 등)는 concept. table은 span에 그대로 남긴다.
- {"spans": [{type, text, category}]}이면 그대로 쓴다.
- 아니면 키 이름으로 경로를 나눈다. SCHEMA_KEYS는 schema, CONCEPT_KEYS는 concept. 항목은 문자열이거나
  {text|keyword|name|word, category|label|domain|type} 객체다. {"진단명": [...], "약물명": [...]}처럼
  카테고리가 키인 형식도 받는다.
- 카테고리 이름은 eval/maps/llm_category_map.yaml로 API 라벨(진단명 또는 질병명 …, 방문 유형, 성별)에
  맞춘다. 표에 없는 이름은 그대로 둔다. 채점에서는 라벨이 다른 것으로 계산된다.
- LLM은 위치를 주지 않으므로 질의에서 글자 그대로 찾아 위치를 붙인다. 못 찾은 단어(바꿔 말함·환각)는
  spans에서 빼고 dropped에 남긴다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import yaml

import eval.common as common
from eval.common import EVAL_DIR, sha256_text
from eval.extractors import ExtractError, PreflightError
from eval.httpclient import RequestFailed, post_json

CATEGORY_MAP_PATH = EVAL_DIR / "maps" / "llm_category_map.yaml"
SCHEMA_KEYS = ("schema_keywords", "schema", "schemas", "스키마", "스키마_키워드", "스키마 키워드")
CONCEPT_KEYS = ("concept_keywords", "concepts", "concept", "컨셉", "컨셉_키워드", "컨셉 키워드", "개념")
TEXT_KEYS = ("text", "keyword", "name", "word", "term", "value", "키워드", "단어")
CAT_KEYS = ("category", "label", "domain", "type", "카테고리", "라벨", "도메인")
# 운영 프롬프트(2026-10)의 라벨 10개 중 의료 개체값 4개(DISEASE/DRUG/MEASUREMENT/PROCEDURE)가 아닌 것의 경로.
# 데이터 구조 참조 3개는 schema, 조건 3개(값·비교·시점)는 API에 대응 경로가 없어 other(채점 제외)로 둔다.
LABEL_TYPE = {"EVENT": "schema", "ATTRIBUTE": "schema", "ENTITY": "schema",
              "VALUE": "other", "OPERATOR": "other", "TIME": "other"}


class ParseError(ValueError):
    pass


def load_category_map(path=CATEGORY_MAP_PATH) -> dict[str, str]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out = {}
    for label, aliases in raw.items():
        out[label.lower()] = label
        for a in aliases or []:
            out[str(a).lower()] = label
    return out


def _extract_json(content: str):
    s = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    starts = [i for i in (s.find("{"), s.find("[")) if i != -1]
    if not starts:
        raise ParseError("JSON을 찾지 못함")
    try:
        obj, _ = json.JSONDecoder().raw_decode(s[min(starts):])
    except json.JSONDecodeError as exc:
        raise ParseError(f"JSON 파싱 실패: {exc}") from None
    return obj


def _item(it, default_type, default_cat=None):
    if isinstance(it, str):
        return {"type": default_type, "text": it.strip(), "category": default_cat}
    if isinstance(it, dict):
        text = next((it[k] for k in TEXT_KEYS if isinstance(it.get(k), str)), None)
        if text is None:
            raise ParseError(f"항목에 텍스트가 없음: {it!r}")
        cat = next((it[k] for k in CAT_KEYS if isinstance(it.get(k), str) and k != "type"), None)
        typ = it.get("type") if it.get("type") in ("schema", "concept") else default_type
        if cat is None and isinstance(it.get("type"), str) and it["type"] not in ("schema", "concept"):
            cat = it["type"]  # {"text": .., "type": "약물"}처럼 type에 카테고리를 넣은 경우
        cat = cat or default_cat
        if isinstance(cat, str) and cat.upper() in LABEL_TYPE:
            typ = LABEL_TYPE[cat.upper()]
        out = {"type": typ, "text": text.strip(), "category": cat}
        if isinstance(it.get("table"), str) and it["table"].strip():
            out["table"] = it["table"].strip()  # 운영 프롬프트는 schema 키워드에 테이블을 같이 낸다
        return out
    raise ParseError(f"알 수 없는 항목 형식: {it!r}")


def _items(value, default_type):
    """리스트 또는 {카테고리: [단어 …]} 사전을 항목 목록으로."""
    if isinstance(value, list):
        return [_item(it, default_type) for it in value]
    if isinstance(value, dict):
        return [_item(it, default_type, cat) for cat, vs in value.items() for it in (vs if isinstance(vs, list) else [vs])]
    raise ParseError(f"목록이 아님: {value!r}")


def parse_response(content: str) -> list[dict]:
    """→ [{type: schema|concept|other, text, category, table?}] (위치 없음)."""
    return parse_obj(_extract_json(content))


def parse_obj(obj) -> list[dict]:
    """이미 디코딩된 JSON(운영 LLM 응답 본문, 또는 같은 형식의 /keyword-extraction/llm-compat 응답)을 항목 목록으로."""
    if isinstance(obj, list):
        return [_item(it, "concept") for it in obj]
    if not isinstance(obj, dict):
        raise ParseError("JSON 객체가 아님")
    if isinstance(obj.get("spans"), list):
        return [_item(it, "concept") for it in obj["spans"]]
    items, known = [], False
    for k, v in obj.items():
        if k in SCHEMA_KEYS:
            items += _items(v, "schema"); known = True  # noqa: E702
        elif k in CONCEPT_KEYS:
            items += _items(v, "concept"); known = True  # noqa: E702
    if not known:
        raise ParseError(f"schema/concept 키를 찾지 못함 (받은 키: {list(obj)})")
    return items


def to_spans(items: list[dict], text: str, category_map: dict[str, str]) -> tuple[list[dict], list[str]]:
    """질의에서 위치를 찾아 API 형식 span으로. 같은 경로의 같은 단어가 여러 번 나오면 차례로 다음 위치."""
    spans, dropped, used = [], [], {"schema": [], "concept": [], "other": []}
    for it in items:
        t = it["text"]
        if not t:
            continue
        start = text.find(t)
        while start != -1 and any(start < e and s < start + len(t) for s, e in used[it["type"]]):
            start = text.find(t, start + 1)
        if start == -1:
            dropped.append(t)
            continue
        used[it["type"]].append((start, start + len(t)))
        cat = it["category"]
        if cat is not None and it["type"] == "concept":  # schema는 표면형으로 채점하므로 그대로 둔다
            cat = category_map.get(cat.lower(), cat)
        span = {"type": it["type"], "text": t, "start": start, "end": start + len(t), "category": cat}
        if "table" in it:
            span["table"] = it["table"]
        spans.append(span)
    return sorted(spans, key=lambda s: (s["start"], s["type"])), dropped


# ── mock ────────────────────────────────────────────────────────────────

MOCK_SCHEMA = ("환자", "진단", "처방", "측정", "방문", "사망", "수술")
MOCK_CONCEPT = {"당뇨병": "진단", "고혈압": "질병", "메트포르민": "drug", "수축기혈압": "검사", "여성": "성별", "입원": "visit"}


class _MockResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._body = body
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._body


def mock_chat_post(url, **kwargs):
    """requests.post 자리에 끼우는 가짜 LLM. 질의 속 MOCK 단어를 운영 LLM이 낼 법한 형식으로 돌려준다."""
    text = kwargs["json"]["messages"][-1]["content"]
    body = {"schema_keywords": [w for w in MOCK_SCHEMA if w in text],
            "concept_keywords": [{"text": w, "category": c} for w, c in MOCK_CONCEPT.items() if w in text]}
    content = "```json\n" + json.dumps(body, ensure_ascii=False) + "\n```"
    return _MockResponse(200, {"choices": [{"message": {"content": content}}]})


def _env(name, default=None):
    return os.environ.get(name) or default


class ProdLLMExtractor:
    system = "prod-llm"

    def __init__(self, post=None, sleep=None):
        self.base_url = (_env("PROD_LLM_BASE_URL", "")).rstrip("/")
        self.model = _env("PROD_LLM_MODEL", "")
        self.api_key = _env("PROD_LLM_API_KEY", "")
        self.system_prompt, self.system_prompt_source = self._system_prompt()
        self.user_template = _env("PROD_LLM_USER_TEMPLATE", "{text}")
        self.temperature = float(_env("PROD_LLM_TEMPERATURE", "0"))
        self.max_tokens = int(_env("PROD_LLM_MAX_TOKENS", "1024"))
        self.timeout = float(_env("PROD_LLM_TIMEOUT", "60"))
        self.max_retries = int(_env("PROD_LLM_MAX_RETRIES", "4"))
        extra = _env("PROD_LLM_EXTRA_BODY")
        try:
            self.extra_body = json.loads(extra) if extra else {}
        except json.JSONDecodeError as exc:
            raise PreflightError(f"PROD_LLM_EXTRA_BODY가 올바른 JSON이 아닙니다: {exc}") from None
        self.category_map = load_category_map()
        self._post = post
        self._sleep = sleep

    @staticmethod
    def _system_prompt() -> tuple[str | None, str]:
        path = _env("PROD_LLM_SYSTEM_PROMPT_FILE")
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = common.ROOT_DIR / p
            if not p.exists():
                return None, f"missing:{p}"
            return p.read_text(encoding="utf-8").strip(), f"file:{p}"
        if _env("PROD_LLM_SYSTEM_PROMPT"):
            return os.environ["PROD_LLM_SYSTEM_PROMPT"], "env:PROD_LLM_SYSTEM_PROMPT"
        return None, "none"

    @property
    def url(self) -> str:
        return self.base_url if self.base_url.endswith("/chat/completions") else self.base_url + "/chat/completions"

    def preflight(self) -> None:
        missing = [n for n, v in (("PROD_LLM_BASE_URL", self.base_url), ("PROD_LLM_MODEL", self.model),
                                  ("PROD_LLM_SYSTEM_PROMPT(_FILE)", self.system_prompt)) if not v]
        if missing:
            hint = (f" (시스템 프롬프트 파일 없음: {self.system_prompt_source[8:]})"
                    if self.system_prompt_source.startswith("missing:") else "")
            raise PreflightError(f"운영 LLM 설정이 없습니다: {', '.join(missing)}{hint} → keyword_ext_eval/.env에 채우세요")
        if "{text}" not in self.user_template:
            raise PreflightError("PROD_LLM_USER_TEMPLATE에 {text}가 없습니다")

    def messages(self, text: str) -> list[dict]:
        return [{"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.user_template.replace("{text}", text)}]

    def config(self) -> dict:
        return {"system": self.system, "base_url": self.base_url, "model": self.model,
                "system_prompt_source": self.system_prompt_source,
                "system_prompt_sha256": sha256_text(self.system_prompt) if self.system_prompt else None,
                "user_template": self.user_template, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "extra_body": self.extra_body, "api_key_set": bool(self.api_key)}

    def extract(self, text: str) -> dict:
        payload = {"model": self.model, "messages": self.messages(text), "temperature": self.temperature,
                   "max_tokens": self.max_tokens, **self.extra_body}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        kwargs = {k: v for k, v in (("post", self._post), ("sleep", self._sleep)) if v}
        try:
            resp = post_json(self.url, payload, timeout=self.timeout, max_retries=self.max_retries,
                             headers=headers, **kwargs)
        except RequestFailed as exc:
            raise ExtractError(str(exc), attempts=exc.attempts) from None
        try:
            content = resp.body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ExtractError("응답에 choices[0].message.content가 없음", attempts=resp.attempts,
                               raw=str(resp.body)[:2000]) from None
        if not content.strip():
            ch = resp.body["choices"][0]
            why = (" - 추론(reasoning)으로 max_tokens를 다 썼습니다. PROD_LLM_EXTRA_BODY로 thinking을 끄거나"
                   " PROD_LLM_MAX_TOKENS를 늘리세요" if ch.get("finish_reason") == "length" else "")
            raise ExtractError(f"빈 응답 (finish_reason={ch.get('finish_reason')}){why}", attempts=resp.attempts,
                               raw=str((ch.get("message") or {}).get("reasoning") or "")[:2000])
        try:
            items = parse_response(content)
        except ParseError as exc:
            raise ExtractError(f"parse error: {exc}", attempts=resp.attempts, raw=content[:2000]) from None
        spans, dropped = to_spans(items, text, self.category_map)
        return {"spans": spans, "dropped": dropped, "raw": content, "latency_ms": round(resp.latency_ms, 1),
                "attempts": resp.attempts}

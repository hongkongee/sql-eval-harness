"""기준점: 실행 중인 키워드 추출 API(POST /keyword-extraction)의 응답을 그대로 기록한다.

사전 매칭 로직은 여기 복제하지 않는다 - 무엇이 schema이고 concept인지는 API 응답이 정한다.
"""

from __future__ import annotations

import ast
import os
import subprocess

import requests

from eval.common import dict_path, service_dir, sha256_file
from eval.extractors import ExtractError, PreflightError, dedup_keep_order
from eval.httpclient import RequestFailed, check_health, post_json

DEFAULT_URL = "http://localhost:8001"
# docker-compose(gliner-entity-router)의 keyword-extraction 서비스 컨테이너. 사전이 이미지에
# 구워져 있어서(볼륨 마운트 없음) API가 실제로 쓰는 사전은 컨테이너 안 파일로 확인한다.
DEFAULT_CONTAINER = "gliner-entity-router-keyword-extraction-1"
CONTAINER_DICT_PATH = "/app/app/config/schema_keywords.yaml"


def _docker(container: str, *cmd: str) -> str | None:
    try:
        out = subprocess.run(
            ["docker", "exec", container, *cmd], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def _service_setting_defaults() -> dict:
    """서비스의 app/config/settings.py에서 기본값을 import 없이(ast로) 읽는다."""
    path = service_dir() / "app" / "config" / "settings.py"
    if not path.exists():
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_DEFAULT_CONCEPT_LABELS" for t in node.targets
        ):
            found["concept_labels"] = list(ast.literal_eval(node.value))
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            if node.target.id in ("gliner_model_path", "gliner_threshold"):
                try:
                    found[node.target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return found


def service_config(container: str) -> dict:
    """API가 쓰는 GLiNER 모델·라벨·threshold. 컨테이너 환경변수 → 서비스 settings.py 기본값 순."""
    defaults = _service_setting_defaults()
    env = {}
    raw_env = _docker(container, "env")
    if raw_env:
        for line in raw_env.splitlines():
            k, _, v = line.partition("=")
            env[k] = v
    labels = [x.strip() for x in env.get("CONCEPT_LABELS", "").split(",") if x.strip()]
    return {
        "gliner_model": env.get("GLINER_MODEL_PATH") or defaults.get("gliner_model_path"),
        "gliner_threshold": float(env["GLINER_THRESHOLD"]) if env.get("GLINER_THRESHOLD") else defaults.get("gliner_threshold"),
        "concept_labels": labels or defaults.get("concept_labels"),
        "source": "container env + settings.py defaults" if raw_env else "settings.py defaults (컨테이너 조회 실패)",
    }


def container_dict_hash(container: str) -> str | None:
    out = _docker(container, "sha256sum", CONTAINER_DICT_PATH)
    return out.split()[0] if out else None


class ApiExtractor:
    system = "api"

    def __init__(self, url: str | None = None, timeout: float = 60.0, container: str | None = None,
                 dict_override: str | None = None, strict_dict: bool = False):
        self.url = (url or os.environ.get("KEYWORD_API_URL") or DEFAULT_URL).rstrip("/")
        self.timeout = timeout
        self.container = container or os.environ.get("KEYWORD_API_CONTAINER", DEFAULT_CONTAINER)
        self.dict_file = dict_path(dict_override)
        self.strict_dict = strict_dict

    def preflight(self) -> None:
        try:
            check_health(self.url)
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            raise PreflightError(
                f"키워드 추출 API에 연결할 수 없습니다: {self.url} ({type(exc).__name__})\n"
                "  → gliner-entity-router에서 `docker compose up -d keyword-extraction`으로 띄우거나,\n"
                "    다른 주소면 KEYWORD_API_URL 환경변수(또는 --api-url)를 지정하세요."
            ) from None

    def config(self) -> dict:
        local_hash = sha256_file(self.dict_file) if self.dict_file.exists() else None
        api_hash = container_dict_hash(self.container)
        cfg = {
            "api_url": self.url,
            "dict_path": str(self.dict_file),
            "dict_sha256_local": local_hash,
            "dict_sha256_api": api_hash,
            "container": self.container,
            **service_config(self.container),
        }
        if api_hash is None:
            cfg["dict_check"] = "unknown (컨테이너 사전 해시를 읽지 못함)"
        elif api_hash == local_hash:
            cfg["dict_check"] = "match"
        else:
            cfg["dict_check"] = "MISMATCH"
        return cfg

    def check_config(self, cfg: dict) -> None:
        if cfg["dict_check"] == "MISMATCH":
            msg = (
                "API가 쓰는 사전과 현재 사전 파일이 다릅니다 "
                f"(API {cfg['dict_sha256_api'][:12]} ≠ 파일 {cfg['dict_sha256_local'][:12]}).\n"
                "  사전이 이미지에 구워져 있으므로 재시작이 아니라 재빌드가 필요합니다:\n"
                f"    cd {service_dir()} && docker compose up -d --build keyword-extraction"
            )
            if self.strict_dict:
                raise PreflightError(msg)
            print(f"[warn] {msg}")
        elif cfg["dict_check"].startswith("unknown"):
            print(f"[warn] API 사전 해시를 확인하지 못했습니다 (컨테이너 '{self.container}'). "
                  "KEYWORD_API_CONTAINER로 컨테이너 이름을 지정할 수 있습니다.")

    def extract(self, record: dict) -> dict:
        try:
            resp = post_json(self.url + "/keyword-extraction", {"text": record["text"]},
                             timeout=self.timeout, max_retries=2)
        except RequestFailed as exc:
            raise ExtractError(str(exc), attempts=exc.attempts) from None
        spans = resp.body.get("spans", [])
        schema = dedup_keep_order(s["text"] for s in spans if s.get("type") == "schema")
        concepts = [
            {"text": s["text"], "start": s["start"], "end": s["end"],
             "score": s.get("score"), "label": s.get("label")}
            for s in spans if s.get("type") == "concept"
        ]
        return {"schema_keywords": schema, "concept_spans": concepts,
                "latency_ms": round(resp.latency_ms, 2), "attempts": resp.attempts}

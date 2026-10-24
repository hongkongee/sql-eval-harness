"""데이터 로딩, JSONL 입출력, 해시, 실행 환경 정보 등 공용 함수."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT_DIR = EVAL_DIR.parent  # keyword_ext_eval/

# 서비스 사전 기본 위치: ~/Developer/gliner-entity-router (이 폴더 기준 ../../../).
# 평가 도구는 이 파일을 "읽기만" 한다 - 매칭 로직은 API가 담당한다.
DEFAULT_SERVICE_DIR = ROOT_DIR.parent.parent.parent / "gliner-entity-router"
DEFAULT_DICT_PATH = DEFAULT_SERVICE_DIR / "app" / "config" / "schema_keywords.yaml"

# 정답 SQL 필드명 후보 (test_set/*.jsonl은 query, data/omop_seed_dataset_10.jsonl은 sql_query)
SQL_FIELDS = ("query", "sql_query")


def load_dotenv(path: str | Path | None = None) -> None:
    """keyword_ext_eval/.env 로더 (scripts/eval_api_model.py의 _load_dotenv와 같은 규칙).

    KEY=VALUE, '#' 주석, 값 앞뒤 따옴표, 값 안의 리터럴 \\n(실제 줄바꿈으로 변환)만 지원한다.
    이미 셸에 값이 있는 환경변수가 우선한다(빈 값은 없는 것으로 본다).
    """
    path = Path(path) if path else ROOT_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        value = value.replace("\\n", "\n")
        if not os.environ.get(key):
            os.environ[key] = value


def service_dir() -> Path:
    return Path(os.environ.get("KEYWORD_SERVICE_DIR", str(DEFAULT_SERVICE_DIR)))


def dict_path(override: str | None = None) -> Path:
    if override:
        return Path(override)
    if os.environ.get("SCHEMA_KEYWORDS_PATH"):
        return Path(os.environ["SCHEMA_KEYWORDS_PATH"])
    return service_dir() / "app" / "config" / "schema_keywords.yaml"


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: str | Path, row: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: str | Path, obj) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def dataset_name(path: str | Path) -> str:
    return Path(path).stem


def load_dataset(path: str | Path) -> list[dict]:
    """평가 데이터 파일 하나를 읽어 {id, raw_id, dataset, text, sql, row} 리스트로 돌려준다.

    파일마다 id 체계가 달라서(시드는 정수, 변형 테스트셋은 "seed_5_test_concept") 여러
    파일을 한 번에 돌릴 때 충돌하지 않도록 id를 "<파일명>:<원래 id>"로 만든다. 같은 파일
    안에서 id가 중복되면(restructure/concept에 1건씩 있음) 두 번째부터 "#2"를 붙이고 경고한다.
    """
    name = dataset_name(path)
    records = []
    seen: dict[str, int] = {}
    for row in read_jsonl(path):
        raw_id = str(row["id"])
        seen[raw_id] = seen.get(raw_id, 0) + 1
        rid = f"{name}:{raw_id}" if seen[raw_id] == 1 else f"{name}:{raw_id}#{seen[raw_id]}"
        if seen[raw_id] == 2:
            print(f"[warn] {path}: id '{raw_id}' 중복 - 두 번째부터 '#N'을 붙여 구분합니다", file=sys.stderr)
        sql = next((row[k] for k in SQL_FIELDS if row.get(k)), "")
        records.append({"id": rid, "raw_id": raw_id, "dataset": name, "text": row["text"], "sql": sql, "row": row})
    return records


def load_datasets(paths: list[str]) -> list[dict]:
    records = []
    for p in paths:
        records.extend(load_dataset(p))
    return records


def hardware_info() -> dict:
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "hostname": platform.node(),
    }
    return info

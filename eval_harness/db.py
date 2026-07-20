"""db_id별 스키마+샘플데이터(.sql)를 in-memory SQLite로 구성하는 픽스처 로더.

새 도메인을 추가하려면 data/fixtures/<db_id>.sql을 만들고 DB_REGISTRY에 등록한다.
"""
import sqlite3
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

DB_REGISTRY = {
    "company_db": FIXTURES_DIR / "company_db.sql",
}


def load_fixture(db_id: str) -> sqlite3.Connection:
    if db_id not in DB_REGISTRY:
        raise KeyError(f"등록되지 않은 db_id: {db_id!r} (등록됨: {list(DB_REGISTRY)})")

    sql_path = DB_REGISTRY[db_id]
    conn = sqlite3.connect(":memory:")
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.commit()
    return conn

"""SQL Validity — 픽스처 스키마 기준으로 컴파일 가능한(문법+테이블/컬럼 참조가 유효한) SQL인지 확인.

EXPLAIN은 쿼리를 실행하지 않고 SQLite 옵티마이저가 실행 계획을 세울 수 있는지만
검증하므로, 실제 실행 없이 syntax + schema 참조 오류를 함께 잡아낼 수 있다.
"""
import sqlite3


def is_valid_sql(conn: sqlite3.Connection, sql: str) -> bool:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return False
    try:
        conn.execute(f"EXPLAIN {sql}")
        return True
    except sqlite3.Error:
        return False

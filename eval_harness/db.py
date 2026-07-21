"""db_id별로 PostgreSQL 샌드박스 DB에 연결하는 커넥션 로더.

스키마+샘플데이터는 더 이상 이 harness가 in-memory로 적재하지 않는다.
DATABASE_URL 환경변수가 가리키는 샌드박스 DB에 이미 적재되어 있다고 가정하고
연결만 맺는다 (data/fixtures/*.sql은 그 샌드박스 DB를 준비할 때 쓰는
스키마+데이터 원본 문서로만 남는다).

새 도메인을 추가하려면 샌드박스 DB에 해당 스키마+데이터를 적재한 뒤
DB_REGISTRY에 db_id를 등록한다.
"""
import os

import psycopg

# 등록된 db_id 목록. 값은 쓰지 않고 존재 여부만 확인한다 —
# 실제 스키마/데이터는 DATABASE_URL이 가리키는 샌드박스 DB에 이미 있다.
DB_REGISTRY = {
    "omop_cdm_v53": None,
}


def get_connection(db_id: str) -> psycopg.Connection:
    if db_id not in DB_REGISTRY:
        raise KeyError(f"등록되지 않은 db_id: {db_id!r} (등록됨: {list(DB_REGISTRY)})")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "DATABASE_URL 환경변수가 설정되어 있지 않습니다. "
            "예: postgresql://user:password@localhost:5432/sandbox_db"
        )

    conn = psycopg.connect(dsn)
    # autocommit이 아니면 EXPLAIN/쿼리 실행 중 하나가 실패했을 때 트랜잭션이
    # aborted 상태로 남아 같은 연결을 재사용하는 이후의 모든 호출이
    # "current transaction is aborted" 에러로 연쇄 실패한다. 문항마다 독립적인
    # 성공/실패만 보면 되므로 각 statement를 자체 트랜잭션으로 커밋한다.
    conn.autocommit = True
    return conn

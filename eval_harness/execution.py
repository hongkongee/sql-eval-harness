"""EX — 예측 SQL과 정답 SQL을 동일 샌드박스 DB에서 실행해 결과를 비교.

정답 쿼리에 ORDER BY가 있으면 행 순서까지 비교하고, 없으면 결과 행 집합만
(순서 무관) 비교한다. repr() 기준으로 정렬해 None 등 서로 다른 타입이
섞인 행을 비교할 때 발생하는 TypeError를 피한다.
"""
import psycopg


def _run(conn: psycopg.Connection, sql: str) -> list[tuple]:
    sql = sql.strip().rstrip(";").strip()
    cur = conn.execute(sql)
    return cur.fetchall()


def _normalize_rowset(rows: list[tuple]) -> list[tuple]:
    return sorted(rows, key=repr)


def is_execution_match(conn: psycopg.Connection, predicted_sql: str, gold_sql: str) -> bool:
    try:
        gold_rows = _run(conn, gold_sql)
    except psycopg.Error as exc:
        raise RuntimeError(
            f"정답 쿼리 실행 실패 (테스트셋/샌드박스 DB 확인 필요): {exc}\nSQL: {gold_sql}"
        ) from exc

    try:
        pred_rows = _run(conn, predicted_sql)
    except psycopg.Error:
        return False

    if "order by" in gold_sql.lower():
        return pred_rows == gold_rows
    return _normalize_rowset(pred_rows) == _normalize_rowset(gold_rows)

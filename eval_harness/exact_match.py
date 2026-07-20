"""EM — 공백/대소문자/후행 세미콜론을 정규화한 뒤 문자열 완전 일치 여부를 비교.

주의: AST 수준 동치 판정이 아니라 문자열 정규화 비교라, 의미는 같지만 표현이
다른 쿼리(컬럼 순서, 별칭, 괄호 위치 등)는 EM에서 불일치로 처리된다.
의미적 동치까지 보려면 execution.py의 EX 지표를 함께 참고할 것.
"""
import re


def normalize_sql(sql: str) -> str:
    sql = sql.strip().rstrip(";").strip()
    sql = re.sub(r"\s+", " ", sql)
    return sql.lower()


def is_exact_match(predicted_sql: str, gold_sql: str) -> bool:
    return normalize_sql(predicted_sql) == normalize_sql(gold_sql)

# 베이스 vs 파인튜닝 모델 생성 SQL 비교 (2026-11-16)

- user 메시지: 운영 서버 `POST /rag`의 `prompt` 그대로
- (A) 학습용 시스템 프롬프트 / (B) 운영 API 시스템 프롬프트
- vLLM `10.1.1.69:8007`, temperature 0, 질의당 1회

## 고혈압 환자의 연령대별 환자 수

### (A) 학습용 시스템 프롬프트

**베이스**

```sql
SELECT
  CASE
    WHEN EXTRACT(YEAR FROM birth_datetime) BETWEEN 0 AND 19
    THEN '0-19'
    WHEN EXTRACT(YEAR FROM birth_datetime) BETWEEN 20 AND 39
    THEN '20-39'
    WHEN EXTRACT(YEAR FROM birth_datetime) BETWEEN 40 AND 59
    THEN '40-59'
    WHEN EXTRACT(YEAR FROM birth_datetime) BETWEEN 60 AND 79
    THEN '60-79'
    ELSE '80+'
  END AS age_group,
  COUNT(*) AS patient_count
FROM person
JOIN condition_occurrence
  ON person.person_id = condition_occurrence.person_id
WHERE
  condition_concept_id IN (320128, 319826, 4289933)
GROUP BY
  age_group
ORDER BY
  age_group
```

**파인튜닝 (by-loss)**

```sql
SELECT
  p.person_id,
  CASE
    WHEN (
      EXTRACT(YEAR FROM (
        CAST('2026-11-16' AS DATE) - p.birth_datetime
      )) - 1
    ) % 10 = 0
    THEN (
      EXTRACT(YEAR FROM (
        CAST('2026-11-16' AS DATE) - p.birth_datetime
      )) - 1
    ) / 10
    ELSE (
      EXTRACT(YEAR FROM (
        CAST('2026-11-16' AS DATE) - p.birth_datetime
      )) - 1
    ) / 10
  END AS age_decade,
  COUNT(DISTINCT c.person_id) AS high_blood_pressure_person_count
FROM person AS p
JOIN condition_occurrence AS c
  ON c.person_id = p.person_id
WHERE
  c.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826)
  )
GROUP BY
  p.person_id,
  age_decade
ORDER BY
  age_decade
```

### (B) 운영 API 시스템 프롬프트

**베이스**

```sql
SELECT
  EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), person.birth_datetime)) AS age,
  COUNT(person.person_id) AS patient_count
FROM person
JOIN condition_occurrence
  ON person.person_id = condition_occurrence.person_id
WHERE
  condition_occurrence.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826)
  )
GROUP BY
  age
ORDER BY
  age
```

**파인튜닝 (by-loss)**

```sql
SELECT
  p.person_id,
  EXTRACT(YEAR FROM p.birth_datetime) AS birth_year,
  CASE
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1900 AND 1920
    THEN '1900-1920'
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1921 AND 1940
    THEN '1921-1940'
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1941 AND 1960
    THEN '1941-1960'
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1961 AND 1980
    THEN '1961-1980'
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1981 AND 2000
    THEN '1981-2000'
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 2001 AND 2020
    THEN '2001-2020'
    ELSE 'Other'
  END AS age_group,
  COUNT(DISTINCT c.person_id) AS hypertensive_count
FROM person AS p
JOIN condition_occurrence AS c
  ON c.person_id = p.person_id
WHERE
  c.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826)
  )
GROUP BY
  p.person_id,
  birth_year,
  age_group
HAVING
  COUNT(DISTINCT c.person_id) > 0
```

## 연령대 별 고혈압 환자

### (A) 학습용 시스템 프롬프트

**베이스**

```sql
SELECT
  p.person_id,
  p.birth_datetime,
  c.condition_start_date,
  c.condition_end_date
FROM person AS p
JOIN condition_occurrence AS c
  ON p.person_id = c.person_id
WHERE
  c.condition_concept_id IN (320128, 319826)
  AND c.condition_start_date <= '2026-11-16'
  AND (
    c.condition_end_date IS NULL OR c.condition_end_date >= '2026-11-16'
  )
ORDER BY
  p.birth_datetime
```

**파인튜닝 (by-loss)**

```sql
SELECT
  p.person_id,
  p.birth_date,
  (
    EXTRACT(YEAR FROM (
      CAST('2026-11-16' AS DATE) - p.birth_date
    )) / 10
  ) * 10 AS age_decade,
  CASE
    WHEN EXISTS(
      SELECT
        1
      FROM condition_occurrence AS co
      WHERE
        co.person_id = p.person_id
        AND co.condition_concept_id IN (
          SELECT
            descendant_concept_id
          FROM concept_ancestor
          WHERE
            ancestor_concept_id IN (320128)
        )
    )
    THEN 'Yes'
    ELSE 'No'
  END AS has_hypertension
FROM person AS p
```

### (B) 운영 API 시스템 프롬프트

**베이스**

```sql
SELECT
  p.person_id,
  EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) AS age,
  c.condition_concept_id
FROM person AS p
JOIN condition_occurrence AS c
  ON p.person_id = c.person_id
WHERE
  c.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826, 4289933)
  )
ORDER BY
  age
```

**파인튜닝 (by-loss)**

```sql
SELECT
  p.person_id,
  p.birth_date,
  CASE
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 18 AND 24
    THEN '18-24'
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 25 AND 34
    THEN '25-34'
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 35 AND 44
    THEN '35-44'
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 45 AND 54
    THEN '45-54'
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 55 AND 64
    THEN '55-64'
    WHEN (
      EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_date)
    ) BETWEEN 65 AND 74
    THEN '65-74'
    ELSE '75+'
  END AS age_group
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  p.person_id,
  p.birth_date
```

## 성별 고혈압 환자 수

### (A) 학습용 시스템 프롬프트

**베이스**

```sql
SELECT
  COUNT(DISTINCT p.person_id) AS male_hypertension_count
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  p.gender_concept_id = 8507
  AND co.condition_concept_id IN (320128, 319826, 4289933, 192680)
  AND co.condition_start_date <= '2026-11-16'
```

**파인튜닝 (by-loss)**

```sql
SELECT
  p.gender_concept_id,
  COUNT(DISTINCT p.person_id) AS hypertensive_person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  p.gender_concept_id
```

### (B) 운영 API 시스템 프롬프트

**베이스**

```sql
SELECT
  COUNT(DISTINCT p.person_id) AS male_hypertension_count
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  p.gender_concept_id = 8507
  AND co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826, 4289933, 192680)
  )
```

**파인튜닝 (by-loss)**

```sql
SELECT
  COUNT(DISTINCT p.person_id) AS hypertensive_person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
  AND p.gender_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (8507, 8532)
  )
```

---

# 운영 API 시스템 프롬프트 + `[범주별 집계]` 규칙 (C)

- 운영 시스템 프롬프트 끝에 `[범주별 집계]` 규칙을 덧붙임 (규칙 원문은 P07 본문 5.3)
- 신규 질의 2개와 회귀 확인 질의 1개는 규칙 없는 운영 프롬프트(B) 결과도 함께 싣는다

## 고혈압 환자의 연령대별 환자 수 (P07)

**베이스 — (C) 규칙 추가**

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), person.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS patient_count
FROM person
JOIN condition_occurrence
  ON person.person_id = condition_occurrence.person_id
WHERE
  condition_concept_id IN (320128, 319826)
GROUP BY
  age_group
ORDER BY
  age_group
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM (
    CAST('2026-11-16' AS DATE) - person.birth_datetime
  )) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS num_patients
FROM person
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence
    WHERE
      condition_occurrence.person_id = person.person_id
      AND condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 연령대 별 고혈압 환자 (P07)

**베이스 — (C) 규칙 추가**

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), person.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS patient_count
FROM person
JOIN condition_occurrence
  ON person.person_id = condition_occurrence.person_id
WHERE
  condition_occurrence.condition_concept_id IN (4289933, 320128, 319826, 192680)
GROUP BY
  age_group
ORDER BY
  age_group
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM (
    CAST('2026-11-16' AS DATE) - person.birth_datetime
  )) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS num_patients
FROM person
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence
    WHERE
      condition_occurrence.person_id = person.person_id
      AND condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 성별 고혈압 환자 수 (P07)

**베이스 — (C) 규칙 추가**

```sql
SELECT
  COUNT(DISTINCT person.person_id) AS total_patients
FROM person
JOIN condition_occurrence
  ON person.person_id = condition_occurrence.person_id
WHERE
  person.gender_concept_id IN (8507, 8532)
  AND condition_occurrence.condition_concept_id IN (4289933, 320128, 319826, 192680)
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT
  p.gender_concept_id,
  COUNT(DISTINCT p.person_id) AS person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  p.gender_concept_id
```

## 진단 연도별 제2형 당뇨병 환자 수 (신규)

**베이스 — (B) 규칙 없음**

```sql
SELECT
  EXTRACT(YEAR FROM condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT person_id) AS patient_count
FROM condition_occurrence
WHERE
  condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id = 201826
  )
GROUP BY
  EXTRACT(YEAR FROM condition_start_date)
ORDER BY
  diagnosis_year
```

**베이스 — (C) 규칙 추가**

```sql
SELECT
  EXTRACT(YEAR FROM condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT person_id) AS patient_count
FROM condition_occurrence
WHERE
  condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id = 201826
  )
GROUP BY
  EXTRACT(YEAR FROM condition_start_date)
ORDER BY
  diagnosis_year
```

**파인튜닝 (by-loss) — (B) 규칙 없음**

```sql
SELECT
  EXTRACT(YEAR FROM co.condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT co.person_id) AS person_count
FROM condition_occurrence AS co
WHERE
  co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (201826)
  )
GROUP BY
  diagnosis_year
ORDER BY
  diagnosis_year
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT
  EXTRACT(YEAR FROM co.condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT co.person_id) AS person_count
FROM condition_occurrence AS co
WHERE
  co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (201826)
  )
GROUP BY
  diagnosis_year
ORDER BY
  diagnosis_year
```

## 성별·연령대별 심근경색 환자 수 (신규)

**베이스 — (B) 규칙 없음**

```sql
SELECT
  p.gender_concept_id,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  co.condition_concept_id IN (4329847, 4121477, 314666, 4270024, 321320)
GROUP BY
  p.gender_concept_id
```

**베이스 — (C) 규칙 추가**

```sql
SELECT
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  co.condition_concept_id IN (4329847, 4121477, 314666, 4270024, 321320)
GROUP BY
  p.gender_concept_id,
  age_group
ORDER BY
  p.gender_concept_id,
  age_group
```

**파인튜닝 (by-loss) — (B) 규칙 없음**

```sql
SELECT
  p.gender_concept_id,
  CASE
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1900 AND 1929
    THEN 1
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1930 AND 1959
    THEN 2
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1960 AND 1989
    THEN 3
    WHEN EXTRACT(YEAR FROM p.birth_datetime) BETWEEN 1990 AND 2019
    THEN 4
    ELSE 5
  END AS age_group,
  COUNT(DISTINCT p.person_id) AS num_persons
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (4329847)
      )
  )
GROUP BY
  p.gender_concept_id,
  age_group
ORDER BY
  p.gender_concept_id,
  age_group
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM (
    CAST('2026-11-16' AS DATE) - p.birth_datetime
  )) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (4329847)
      )
  )
GROUP BY
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM (
    CAST('2026-11-16' AS DATE) - p.birth_datetime
  )) / 10) * 10
```

## 80세 초과이면서 고혈압 진단 이력이 있는 환자 목록 (회귀(코호트))

**베이스 — (B) 규칙 없음**

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  p.birth_datetime <= CAST('1945-11-16' AS DATE)
  AND co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (320128, 319826, 4289933, 192680)
  )
```

**베이스 — (C) 규칙 추가**

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
JOIN condition_occurrence AS co
  ON p.person_id = co.person_id
WHERE
  p.birth_datetime <= CAST('1945-11-16' AS DATE)
  AND co.condition_concept_id IN (4289933, 320128, 319826, 192680)
```

**파인튜닝 (by-loss) — (B) 규칙 없음**

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
WHERE
  (
    EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_datetime)
  ) > 80
  AND EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
```

**파인튜닝 (by-loss) — (C) 규칙 추가**

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
WHERE
  (
    EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_datetime)
  ) > 80
  AND EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
```

---

# 파인튜닝 + 규칙 + 나이 치환 (D)

- (C) 파인튜닝 + 규칙으로 다시 생성한 SQL(이전과 동일)에 서버 후처리로 나이 계산식을 `AGE(기준일, 생년월일)`로 치환한 결과 (패턴은 P07 본문 5.3)

## 고혈압 환자의 연령대별 환자 수 (P07) — 치환: 날짜뺄셈

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), person.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS num_patients
FROM person
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence
    WHERE
      condition_occurrence.person_id = person.person_id
      AND condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 연령대 별 고혈압 환자 (P07) — 치환: 날짜뺄셈

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), person.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT person.person_id) AS num_patients
FROM person
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence
    WHERE
      condition_occurrence.person_id = person.person_id
      AND condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 성별 고혈압 환자 수 (P07) — 치환: 없음

```sql
SELECT
  p.gender_concept_id,
  COUNT(DISTINCT p.person_id) AS person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  p.gender_concept_id
```

## 진단 연도별 제2형 당뇨병 환자 수 (신규) — 치환: 없음

```sql
SELECT
  EXTRACT(YEAR FROM co.condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT co.person_id) AS person_count
FROM condition_occurrence AS co
WHERE
  co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id IN (201826)
  )
GROUP BY
  diagnosis_year
ORDER BY
  diagnosis_year
```

## 성별·연령대별 심근경색 환자 수 (신규) — 치환: 날짜뺄셈, 날짜뺄셈

```sql
SELECT
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS person_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (4329847)
      )
  )
GROUP BY
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10
```

## 80세 초과이면서 고혈압 진단 이력이 있는 환자 목록 (회귀(코호트)) — 치환: 출생연도차이

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
WHERE
  (
    EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime))
  ) > 80
  AND EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
```

---

# 파인튜닝 + 규칙 + 예시 (변형 2, 시스템 프롬프트만 변경)

- (C)의 규칙 프롬프트에 나이 계산 규칙과 연령대 집계 예시 SQL 1개를 덧붙임 (프롬프트 원문은 P07 본문 5.3)

## 고혈압 환자의 연령대별 환자 수 (P07)

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 연령대 별 고혈압 환자 (P07)

```sql
SELECT
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  age_group
ORDER BY
  age_group
```

## 성별 고혈압 환자 수 (P07)

```sql
SELECT
  p.gender_concept_id,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
GROUP BY
  p.gender_concept_id
```

## 진단 연도별 제2형 당뇨병 환자 수 (신규)

```sql
SELECT
  EXTRACT(YEAR FROM co.condition_start_date) AS diagnosis_year,
  COUNT(DISTINCT co.person_id) AS person_count
FROM condition_occurrence AS co
WHERE
  co.condition_concept_id IN (
    SELECT
      descendant_concept_id
    FROM concept_ancestor
    WHERE
      ancestor_concept_id = 201826
  )
GROUP BY
  diagnosis_year
ORDER BY
  diagnosis_year
```

## 성별·연령대별 심근경색 환자 수 (신규)

```sql
SELECT
  p.gender_concept_id,
  FLOOR(EXTRACT(YEAR FROM AGE(CAST('2026-11-16' AS DATE), p.birth_datetime)) / 10) * 10 AS age_group,
  COUNT(DISTINCT p.person_id) AS patient_count
FROM person AS p
WHERE
  EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id = 4329847
      )
  )
GROUP BY
  p.gender_concept_id,
  age_group
```

## 80세 초과이면서 고혈압 진단 이력이 있는 환자 목록 (회귀(코호트))

```sql
SELECT DISTINCT
  p.person_id
FROM person AS p
WHERE
  (
    EXTRACT(YEAR FROM CAST('2026-11-16' AS DATE)) - EXTRACT(YEAR FROM p.birth_datetime)
  ) > 80
  AND EXISTS(
    SELECT
      1
    FROM condition_occurrence AS co
    WHERE
      co.person_id = p.person_id
      AND co.condition_concept_id IN (
        SELECT
          descendant_concept_id
        FROM concept_ancestor
        WHERE
          ancestor_concept_id IN (320128, 319826)
      )
  )
```

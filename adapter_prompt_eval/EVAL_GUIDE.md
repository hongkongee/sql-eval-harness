# 평가 실행 가이드 — 명령어로 테스트하고 결과 확인하기

지금까지 보고서(`reports/`)에 쓴 테스트를 직접 돌리고 결과를 확인하는 방법이에요. 모든 명령은 `adapter_prompt_eval/` 폴더에서 실행해요.

```
1. 준비 확인   →   2. 테스트 실행   →   3. 진행 확인   →   4. 끝난 뒤 정리   →   5. 결과 보기
(서버·DB·설정)     (run_eval.py)       (로그·서버 상태)    (실패 재시도·재판정)   (summarize.py)
```

---

## 1. 준비 확인

### 1.1 설정 파일

| 파일 | 내용 |
|---|---|
| `adapter_prompt_eval/.env` | vLLM 서버 주소(`VLLM_HOST`, `VLLM_PORT`), 베이스 모델 이름(`BASE_MODEL_NAME`) |
| `../.env` (저장소 루트) | 샌드박스 DB 접속 정보(`SANDBOX_DB_*`) — 실행검증과 EX 채점에 필요 |

Python은 시스템 `python3`를 써요. 필요한 패키지는 `requirements.txt`에 있어요.

### 1.2 서버에 어떤 모델이 떠 있는지

```bash
curl -s http://10.1.1.69:8007/v1/models | python3 -c "import json,sys;[print(m['id'],'|',m.get('root')) for m in json.load(sys.stdin)['data']]"
```

```
xiyansql-qwencoder-14b-proposed-input | XGenerationLab/XiYanSQL-QwenCoder-14B-2504      ← 베이스 모델
by-loss | /workspace/output/xiyansql-qwencoder-14b-proposed-input/best_model/best_by_loss  ← 어댑터
```

- 왼쪽이 요청에 쓰는 **서빙 이름**이에요. `root`가 어느 학습의 어느 체크포인트인지 보여줘요. 테스트 전에 의도한 모델이 맞는지 꼭 확인해요.
- 어댑터 방식이라 베이스 모델도 함께 떠요(`root`가 `XGenerationLab/...`인 줄). 베이스 모델은 이 이름으로 테스트해요.

### 1.3 샌드박스 DB

```bash
python3 -c "from run_eval import base; c=base.SandboxConnectionPool().get(); print(c.execute('select count(*) from person').fetchone())"
```

숫자가 나오면 정상이에요. DB 컨테이너의 공유 메모리는 1GB로 설정돼 있어야 해요(`docker exec lakefs-postgres df -h /dev/shm` → `1.0G`). 64MB면 큰 쿼리가 `could not resize shared memory segment` 오류로 실패해요.

**정답 쿼리 결과 캐시:** EX를 판정할 때 정답 쿼리는 모델과 상관없이 결과가 같아서, 한 번 실행한 결과를 `../results/gold_cache/`에 저장해 두고 다음부터는 저장된 결과를 써요(`run_eval.py`, `rescore_ex.py` 모두). 모델 SQL은 매번 실행해요.

- 정답 SQL을 고치면 자동으로 새로 실행해요(정답 SQL 원문과 DB 주소가 캐시 키예요).
- `CURRENT_DATE`·`NOW()` 같은 날짜 함수가 들어간 정답 SQL은 실행한 날짜별로 따로 저장해요.
- 정답 쿼리가 실패하거나 시간 초과가 나면 저장하지 않고, 다음 실행 때 다시 시도해요.
- **샌드박스 DB의 데이터를 바꿨다면 캐시를 지워요:** `rm -rf ../results/gold_cache`
- 캐시 없이 돌리려면 명령 앞에 `EX_GOLD_CACHE=0`을 붙여요(예: `EX_GOLD_CACHE=0 python3 run_eval.py ...`).

### 1.4 시스템 프롬프트 파일

| 파일 | 쓰는 모델 |
|---|---|
| `../results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt` | 파인튜닝 모델(FT0·FT1·FT2·FT3 …)과 base — **파인튜닝 학습 때 쓴 문구** |
| `../results/adapter_eval/prompts/adapter_eval_base_sysprompt_v2_system_prompt.txt` | base+시스템 프롬프트 — 규칙 + few-shot |

**파인튜닝 모델은 반드시 학습 때 문구를 넣어서 평가해요.** `--system-prompt`를 빼면 모델 기본 문구("You are Qwen…")가 들어가서 학습 때와 조건이 달라지고, 점수가 낮게 나와요(FT1 val EX 74.6% → 58.7%).

---

## 2. 테스트 실행

### 2.1 기본 형태

```bash
python3 -u run_eval.py \
    --adapter <결과 라벨>=<서빙 이름> \
    --no-base \
    --system-prompt "$(cat <시스템 프롬프트 파일>)" \
    --testset <테스트셋 라벨>=<jsonl 경로> [--testset ...]
```

| 옵션 | 의미 |
|---|---|
| `--adapter LABEL=MODEL` | `MODEL`은 1.2의 서빙 이름, `LABEL`은 결과 파일 이름에 들어갈 이름이에요. 여러 번 줄 수 있어요 |
| `--no-base` | `.env`의 베이스 모델을 자동으로 같이 돌리지 않아요. 베이스 모델은 `--adapter base_xxx=<베이스 서빙 이름>`으로 따로 돌리는 걸 권장해요(시스템 프롬프트를 모델마다 다르게 줘야 해서) |
| `--system-prompt` | 시스템 메시지. 한 번 실행에 하나만 줄 수 있어서, 프롬프트가 다른 모델은 따로 실행해요 |
| `--testset LABEL=PATH` | 결과 파일 이름에 `LABEL`이 들어가요. 아래 라벨을 그대로 쓰면 `summarize.py`가 원본과 짝지어 비교할 수 있어요 |
| `--resume` | 이미 결과 CSV에 있는 문항은 건너뛰고 나머지만 돌려요 |
| `--timeout 120` | 모델 응답 제한 시간(초, 기본 60) |
| `--limit 5` | 테스트셋마다 앞 5건만 (스모크 테스트) |

**테스트셋 라벨 (보고서와 같은 이름)**

| 라벨 | 경로 | 문항 |
|---|---|---:|
| `proposed_input_train` | `../test_set/proposed_input_train.jsonl` | 612 |
| `proposed_input_val` | `../test_set/proposed_input_val.jsonl` | 68 |
| `variant_paraphrase` | `../test_set/eval_ready/paraphrase.jsonl` | 573 |
| `variant_restructure` | `../test_set/eval_ready/restructure.jsonl` | 387 |
| `variant_slot` | `../test_set/eval_ready/slot.jsonl` | 141 |
| `variant_concept` | `../test_set/eval_ready/concept.jsonl` | 455 |

변형 테스트셋은 `test_set/eval_ready/`의 사본을 써요. 원본 파일에 같은 id가 두 번 나오는 행이 있어서, 사본에서 두 번째 행에 `_2`를 붙여 뒀어요.

### 2.2 예시 — 파인튜닝 모델 하나를 전체 테스트셋으로

```bash
SP="$(cat ../results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt)"
ALL=(
  --testset proposed_input_val=../test_set/proposed_input_val.jsonl
  --testset proposed_input_train=../test_set/proposed_input_train.jsonl
  --testset variant_paraphrase=../test_set/eval_ready/paraphrase.jsonl
  --testset variant_restructure=../test_set/eval_ready/restructure.jsonl
  --testset variant_slot=../test_set/eval_ready/slot.jsonl
  --testset variant_concept=../test_set/eval_ready/concept.jsonl
)

nohup python3 -u run_eval.py --adapter ft2_trainsys=proposed-random-by-loss --no-base \
    --timeout 120 --system-prompt "$SP" "${ALL[@]}" > ft2_trainsys_run.log 2>&1 &
```

- **zsh에서는 테스트셋 목록을 배열(`ALL=( ... )`, `"${ALL[@]}"`)로 넘겨야 해요.** 문자열 변수(`TS="--testset ..."`, `$TS`)로 넘기면 하나의 인자로 붙어서 `--testset is required` 오류가 나요.
- `nohup ... &`로 돌리면 터미널을 닫아도 계속 돌아요. 모델 하나에 전체 테스트셋(2,236건)이면 3~4시간 걸려요.
- 결과 라벨은 `<모델>_<조건>`처럼 짓는 걸 권장해요(예: `ft2_trainsys` = FT2 + 학습 때 문구).

### 2.3 예시 — base와 base+시스템 프롬프트

```bash
SP="$(cat ../results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt)"
V2="$(cat ../results/adapter_eval/prompts/adapter_eval_base_sysprompt_v2_system_prompt.txt)"
BASE=xiyansql-qwencoder-14b-proposed-input   # 1.2에서 확인한 베이스 모델 서빙 이름

nohup python3 -u run_eval.py --adapter base_trainsys=$BASE --no-base --system-prompt "$SP" "${ALL[@]}" > base_trainsys_run.log 2>&1 &
nohup python3 -u run_eval.py --adapter base_sysprompt_v2=$BASE --no-base --system-prompt "$V2" "${ALL[@]}" > v2_run.log 2>&1 &
```

### 2.4 여러 모델을 동시에 돌릴 때

- 실행을 여러 개 동시에 띄울 수 있어요. 각 실행은 자기 결과 파일에만 써요.
- **같은 서버의 서로 다른 어댑터를 동시에 돌리면 생각보다 빨라지지 않을 수 있어요.** vLLM이 서로 다른 어댑터 요청을 한 번에 하나씩만 처리하는 설정이면(`--max-loras 1`), 요청이 줄을 서요. 3.2의 서버 상태 확인에서 `running 1, waiting 1`이 계속 보이면 이 경우예요. 서버를 `--max-loras 2` 이상으로 띄우면 동시에 처리돼요.
- 동시에 돌리면 응답 속도 지표가 평소보다 느리게 나와요. 속도는 따로 비교하지 않아요.

---

## 3. 진행 확인

### 3.1 로그

```bash
tail -f ft2_trainsys_run.log                          # 실시간
grep "^===" ft2_trainsys_run.log | tail -1            # 지금 돌고 있는 테스트셋
grep "^\s*\[" ft2_trainsys_run.log | tail -1          # 마지막으로 끝난 문항
grep -c "^\s*\[" ft2_trainsys_run.log                 # 지금까지 끝난 문항 수
stat -f "%Sm" ft2_trainsys_run.log                    # 로그 마지막 갱신 시각 (macOS)
```

로그 한 줄은 이렇게 생겼어요.

```
  [ft2_trainsys][253/612] 272: 문법=pass 전개=1.00 concept_correctness=1.00 EM=fail EX=pass (7.68s)
```

`[253/612]`가 현재 테스트셋의 진행, 괄호 안이 모델 응답 시간이에요. 모든 테스트셋이 끝나면 마지막에 `전체 요약 저장: …json`이 찍혀요.

**남은 시간 계산:** 10~20분 간격으로 끝난 문항 수를 두 번 세서 분당 처리 수를 구하고, 남은 문항 수를 나눠요. 보통 한 실행에 분당 7~10건이에요.

### 3.2 멈췄는지 확인

로그가 15분 넘게 갱신되지 않으면 멈춘 거예요. 원인은 둘 중 하나예요.

```bash
# vLLM 서버: 실행 중 / 대기 중 요청 수
curl -s http://10.1.1.69:8007/metrics | grep -E "^vllm:num_requests_(running|waiting)\{"

# 샌드박스 DB: 실행 중인 쿼리
python3 -c "
from run_eval import base
c=base.SandboxConnectionPool().get()
for r in c.execute(\"select pid,state,now()-query_start,left(query,60) from pg_stat_activity where datname=current_database() and state<>'idle'\"): print(r)"
```

- **vLLM은 놀고 있고 DB에도 실행 중인 쿼리가 없는데 로그가 멈춰 있으면** DB 연결이 쿼리 도중 끊긴 거예요. 지금 코드는 연결 상태를 확인하는 설정(TCP keepalive)이 들어가 있어서 1분 안에 에러로 끝나고 다음 문항으로 넘어가요. 그래도 멈춰 있으면 프로세스를 끄고(`kill <pid>`) 같은 명령에 `--resume`을 붙여 다시 시작해요.
- 실행 중인 프로세스 확인: `ps -axo pid,etime,command | grep "run_eval.py --adapter" | grep -v grep`

---

## 4. 끝난 뒤 정리

### 4.1 API 호출 실패 문항 다시 돌리기

서버가 느리거나 끊겨서 응답을 못 받은 문항은 비고가 `API 호출 실패`로 남아요. `--resume`은 이미 CSV에 있는 문항을 건너뛰기 때문에, 이 행을 먼저 지우고 다시 돌려요.

```bash
python3 - <<'EOF'
import csv, glob
for f in glob.glob('../results/adapter_eval_ft2_trainsys_*.csv'):
    rows = list(csv.DictReader(open(f, encoding='utf-8-sig')))
    keep = [r for r in rows if not r['비고'].startswith('API 호출 실패')]
    with open(f, 'w', newline='', encoding='utf-8-sig') as o:
        w = csv.DictWriter(o, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(keep)
    print(f, len(rows), '->', len(keep))
EOF
# 그다음 2.2와 같은 명령에 --resume을 붙여 다시 실행
```

### 4.2 DB 인프라 오류 문항 다시 판정

DB 공유 메모리 부족, 쿼리 30초 초과, 연결 끊김으로 실행검증·EX가 제대로 판정되지 않은 문항만 저장된 SQL로 다시 판정해요. 모델은 다시 호출하지 않아요.

```bash
python3 rescore_ex.py \
    --testset proposed_input_train=../test_set/proposed_input_train.jsonl \
    --testset proposed_input_val=../test_set/proposed_input_val.jsonl \
    --testset variant_paraphrase=../test_set/eval_ready/paraphrase.jsonl \
    --testset variant_restructure=../test_set/eval_ready/restructure.jsonl \
    --testset variant_slot=../test_set/eval_ready/slot.jsonl \
    --testset variant_concept=../test_set/eval_ready/concept.jsonl \
    ../results/adapter_eval_ft2_trainsys_*.csv
```

다시 해도 `(여전히 인프라 오류)`로 남는 문항은 대부분 **모델 SQL이 30초를 넘기는 경우**예요. 너무 느린 SQL로 보고 실패로 둬요. `ERROR -> ERROR`는 정답 쿼리가 다시 실행해도 시간 초과가 난 경우예요(정답 쿼리 자체가 무거운 문항). DB가 한가할 때 다시 돌리거나 실패로 둬요.

- 대상 문항은 원래 무거운 쿼리라 1건에 몇 분씩 걸릴 수 있어요. 진행 상황은 파일 하나가 끝날 때마다 출력돼요. 출력을 `| grep` 등으로 넘길 때는 `python3 -u`로 실행해야 바로 보여요.

### 4.3 결과 파일 옮기기

평가 스크립트는 `results/` 바로 아래에 결과를 써요. 끝나면 테스트셋별 폴더로 옮겨요(`summarize.py`는 두 위치를 모두 찾아요).

```bash
cd ../results
mv adapter_eval_*_proposed_input_train.csv adapter_eval/train/
mv adapter_eval_*_proposed_input_val.csv   adapter_eval/val/
mv adapter_eval_*_variant_*.csv            adapter_eval/variant/
mv adapter_eval_summary_*.json             adapter_eval/summaries/
cd ../adapter_prompt_eval
```

실행 중인 테스트의 결과 파일은 옮기지 않아요.

---

## 5. 결과 보기

### 5.1 summarize.py로 보고서와 같은 기준의 표 만들기

```bash
# 학습셋·val: 여러 모델을 한 표로
python3 summarize.py \
    --model ft1_trainsys --model ft2_trainsys --model base_trainsys --model base_sysprompt_v2 \
    --testset proposed_input_train=../test_set/proposed_input_train.jsonl \
    --testset proposed_input_val=../test_set/proposed_input_val.jsonl

# 변형 테스트셋: 같은 시드의 원본 결과와 짝지어 비교
python3 summarize.py --pair-original \
    --model ft1_trainsys --model base_sysprompt_v2 \
    --testset variant_concept=../test_set/eval_ready/concept.jsonl
```

출력 예시:

```
### proposed_input_val (집계 63건, 제외 5건)

| 모델 | 문항 | 자연어 답변 | API 실패 | 문법 | 실행검증 | 하위 전개 | 올바른 반영률 | 필요한 코드 | 불필요한 코드 ↓ | EM | EX |
| ft1_trainsys | 63 | 0 | 0 | 100.00% | 96.83% | 91.38% | 87.3% | 88.6% | 45.5% (11) | 47.62% | 74.60% (47) |
```

| 열 | 의미 |
|---|---|
| 집계 / 제외 | base+시스템 프롬프트의 few-shot 문항(id·seed_id 290·535·721·447·299)은 모든 모델에서 빼요. `--exclude-seeds ""`로 끌 수 있어요 |
| 자연어 답변 / API 실패 | 0이 아니면 확인이 필요해요. API 실패는 4.1로 다시 돌려요 |
| 올바른 반영률 | 필요한 concept_id를 하위 전개 형식으로, 실행되는 SQL에 넣은 비율 (concept_id 핵심 지표) |
| 필요한 코드 / 불필요한 코드 | 정답 SQL이 쓰는 코드를 넣은 비율 / 정답이 쓰지 않는 코드를 넣은 비율(괄호는 그런 코드의 개수) |
| EX | 정답 SQL과 실행 결과가 같은 비율 (괄호는 맞힌 문항 수). 가장 중요한 지표예요 |
| 원본 EX / 변화 / 원본 맞힘→틀림 / 원본 틀림→맞힘 | `--pair-original`일 때만. 같은 모델의 학습셋·val 결과 중 같은 시드와 비교해요 |

- 끝나지 않은 실행의 CSV를 넣으면 `⚠️ N건 미완료`가 붙어요.
- 각 지표의 자세한 정의는 `reports/00_overview.md`의 "지표 설명"에 있어요.

### 5.2 summary JSON은 그대로 쓰지 않아요

`results/adapter_eval/summaries/adapter_eval_summary_<시각>.json`은 실행이 끝날 때 자동으로 저장되는 집계예요. **자연어로 답한 문항을 분모에서 빼서 점수가 부풀려지고, few-shot 문항도 빼지 않아요.** 보고서 수치는 5.1의 `summarize.py`로 계산해요.

### 5.3 문항별로 직접 보기

결과 CSV(`results/adapter_eval/{train,val,variant}/adapter_eval_<라벨>_<테스트셋>.csv`)는 문항 하나가 한 줄이에요. 엑셀로 열어도 돼요(UTF-8 BOM).

| 열 | 내용 |
|---|---|
| `모델 답변 쿼리문` | 모델이 만든 SQL |
| `SQL문법 결과`, `샌드박스 DB 실행검증 결과` (+ 에러 사유) | 문법 / 실행 가능 여부 |
| `쿼리문 하위 전개 반영도`, `concept_id …` | 개념 코드 관련 지표 (0~1, 코드가 여러 개면 평균) |
| `EM 결과`, `EX 결과`, `EX 참고사항` | 정답 비교. EX가 fail이면 참고사항에 실행 실패 사유가 남아요 |
| `비고` | `Format 이탈…`(자연어 답변), `API 호출 실패…` |

예: 모델 A는 맞히고 모델 B는 틀린 문항 찾기

```bash
python3 - <<'EOF'
import csv
f = '../results/adapter_eval/val/adapter_eval_{}_proposed_input_val.csv'
a = {r['id']: r for r in csv.DictReader(open(f.format('ft1_trainsys'), encoding='utf-8-sig'))}
b = {r['id']: r for r in csv.DictReader(open(f.format('base_sysprompt_v2'), encoding='utf-8-sig'))}
for i in a:
    if a[i]['EX 결과'] == 'pass' and b[i]['EX 결과'] != 'pass':
        print(i, a[i]['자연어 질의'][:50])
EOF
```

---

## 6. 자주 나는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| 모든 문항이 `API 호출 실패: … Connection refused` | vLLM 서버가 내려가 있음 | 1.2로 서버 확인, 다시 띄운 뒤 결과 CSV를 지우고 다시 실행 |
| 모든 문항이 `API 호출 실패: … 404` | 서빙 이름이 틀림 | 1.2의 이름으로 `--adapter` 수정 |
| 일부 문항만 `API 호출 실패: … Read timed out` | 서버가 느림 | `--timeout 120`, 4.1로 재시도 |
| `EX 참고사항`에 `could not resize shared memory segment` | DB 공유 메모리 부족 | DB 컨테이너 `shm_size: '1gb'` 설정 후 4.2 |
| `EX 참고사항`에 `canceling statement due to statement timeout` | 쿼리가 30초를 넘김 | 4.2로 재판정. 계속 남으면 실패로 둠 |
| 로그가 15분 넘게 멈춤 | DB 연결 끊김 또는 서버 멈춤 | 3.2 |
| 같은 정답인데 EX가 이상하게 모두 fail | 샌드박스 DB 데이터를 바꿨는데 예전 정답 결과 캐시를 씀 | `rm -rf ../results/gold_cache` 후 4.2 |
| `the following arguments are required: --testset` | zsh에서 테스트셋 인자를 문자열 변수로 넘김 | 2.2처럼 배열로 넘김 |
| `컬럼 구성이 지금 스크립트와 다릅니다` (`--resume`) | 예전 버전 스크립트로 만든 CSV | 그 CSV를 다른 곳으로 옮기고 새로 실행 |

---

## 7. 직접 물어보기 (정성 평가)

테스트셋 전체를 돌리지 않고, 문항 하나를 모델에 직접 보내서 답변을 눈으로 확인하는 방법이에요. 평가와 똑같은 조건(시스템 프롬프트, temperature 0, max_tokens 512)으로 보내요.

먼저 공통 변수를 잡아 둬요(`adapter_prompt_eval/`에서 실행).

```bash
API=http://10.1.1.69:8007/v1/chat/completions
MODEL=proposed-random-by-loss    # 1.2에서 확인한 서빙 이름
SPF=../results/adapter_eval/prompts/adapter_eval_train_system_prompt.txt   # base+시스템 프롬프트는 v2 파일
```

### 7.1 가장 간단한 curl

질문만 직접 써서 보내요. 재료가 없어서 평가 때와 입력이 달라요. 모델이 응답하는지 빠르게 볼 때 써요.

```bash
curl -s $API -H 'Content-Type: application/json' -d '{
  "model": "'"$MODEL"'",
  "messages": [
    {"role": "system", "content": "당신은 OMOP-CDM v5.3 스키마 기반 임상 데이터베이스를 위한 SQL 생성 전문가입니다. 사용자의 질문에 대해 정확하고 실행 가능한 SQL 쿼리를 작성하세요. 스키마 정보나 concept_id 후보가 함께 제공되는 경우, 반드시 그 정보를 우선적으로 참고하여 SQL을 작성하세요. 부연 설명 없이 SQL 코드만 출력하세요."},
    {"role": "user", "content": "[질의]\n외래 방문 방문이고 입원 방문인 환자."}
  ],
  "temperature": 0, "max_tokens": 512
}' | python3 -c "import json,sys; print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

- 응답 JSON 전체를 보고 싶으면 마지막 `| python3 ...`를 `| python3 -m json.tool`로 바꿔요.
- `[질의]` 아래에 `\n\n[재료]\n...`를 직접 붙여 써도 돼요. 재료 형식은 7.2의 출력이나 `reports/00_overview.md`의 "요청 프롬프트 구성"을 참고해요.

### 7.2 테스트셋 문항을 평가 때와 똑같이 보내기

문항 id로 평가 때와 똑같은 사용자 메시지(질의 + 재료)를 만들어 보내고, 정답 SQL과 나란히 보여줘요. 변형 테스트셋은 `TS`와 `ID`만 바꾸면 돼요(예: `TS=../test_set/eval_ready/paraphrase.jsonl ID=seed_181_test_paraphrase`).

```bash
TS=../test_set/proposed_input_val.jsonl
ID=439

# 1) 요청 본문 만들기 (재료 조립은 평가 스크립트와 같은 함수를 써요)
python3 - "$TS" "$ID" "$MODEL" "$SPF" > /tmp/req.json <<'EOF'
import json, sys
import adherence as ad
ts, cid, model, spf = sys.argv[1:]
case = next(c for c in map(json.loads, open(ts, encoding='utf-8')) if str(c['id']) == cid)
print(json.dumps({
    "model": model,
    "messages": [{"role": "system", "content": open(spf, encoding='utf-8').read().strip()},
                 {"role": "user", "content": ad.build_prompt(case)}],
    "temperature": 0, "max_tokens": 512}, ensure_ascii=False))
print('--- 질의:', case['text'], file=sys.stderr)
print('--- 정답 SQL:\n' + case['query'], file=sys.stderr)
EOF

# 2) 보내고 답변만 보기
curl -s $API -H 'Content-Type: application/json' -d @/tmp/req.json \
  | python3 -c "import json,sys; print('--- 모델 답변:'); print(json.load(sys.stdin)['choices'][0]['message']['content'])"
```

- 모델에 실제로 보낸 메시지를 보고 싶으면 `python3 -m json.tool /tmp/req.json`으로 열어요.
- 결과 CSV의 `모델 답변 쿼리문`과 같은 답이 나와야 정상이에요(temperature 0). 서버 상태에 따라 아주 가끔 달라질 수 있어요.

### 7.3 여러 모델의 답을 한 번에 비교하기

7.2의 1)을 실행해 둔 상태에서, 모델 이름만 바꿔 같은 요청을 보내요.

```bash
for M in baseline-by-loss proposed-random-by-loss; do   # 1.2에서 확인한 서빙 이름들
  echo "===== $M"
  python3 -c "import json,sys; d=json.load(open('/tmp/req.json')); d['model']=sys.argv[1]; print(json.dumps(d, ensure_ascii=False))" $M \
    | curl -s $API -H 'Content-Type: application/json' -d @- \
    | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['choices'][0]['message']['content'] if 'choices' in r else r)"
done
```

- 서버에 떠 있는 모델만 응답해요. 없는 이름이면 `404 … does not exist` 오류가 출력돼요(1.2로 이름 확인).
- base+시스템 프롬프트와 비교하려면 `SPF`를 v2 파일로 바꿔 7.2의 1)을 다시 실행한 뒤 base 서빙 이름으로 보내요.

### 7.4 모델 답변을 샌드박스 DB에서 실행해 정답과 비교하기

답변 SQL을 `/tmp/pred.sql`에 붙여 넣고 실행해요. EX 판정과 같은 함수를 써요.

```bash
python3 - "$TS" "$ID" <<'EOF'
import json, sys
from run_eval import base
ts, cid = sys.argv[1:]
case = next(c for c in map(json.loads, open(ts, encoding='utf-8')) if str(c['id']) == cid)
pred = open('/tmp/pred.sql', encoding='utf-8').read()
conn = base.SandboxConnectionPool().get()
print('EX:', base.check_ex(conn, pred, case['query']))
print('모델 결과 (앞 5행):', base._run_rows(conn, pred)[:5])
print('정답 결과 (앞 5행):', base._run_rows(conn, case['query'])[:5])
EOF
```

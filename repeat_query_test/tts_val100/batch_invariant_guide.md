# batch-invariant 모드 적용·해제·확인 방법 (2026-11-18)

`report_summary.md`의 "직접 시험" 중 **1. batch-invariant 모드만 켬**을 하기 위한 절차입니다. 2번(LoRA 병합)은 병합 로직이 따로 있어서 여기서는 다루지 않습니다.

대상 서버:
- vLLM v0.26.0 (`vllm/vllm-openai:v0.26.0`), 컨테이너 이름 `vllm-serve`
- NVIDIA L40S 1장 (CC 8.9), `--gpu-memory-utilization 0.85`
- LoRA 런타임 서빙 (`--enable-lora --lora-modules by-loss=… final-step=…`)

> **주의: 운영 서버입니다. 서버 관리 쪽과 시간을 맞춰서 진행하세요.**
> - GPU 1장의 메모리를 85% 쓰고 있어서, 컨테이너를 하나 더 띄워 따로 시험할 수 없습니다. 기존 컨테이너를 다시 만들어야 합니다.
> - 모델을 다시 올리는 몇 분 동안 서비스가 멈춥니다.

## 0. 바꾸기 전에 현재 설정 백업

```bash
# 현재 설정 전체 저장 (되돌릴 때 기준)
docker inspect vllm-serve > vllm-serve.before.json

# compose로 띄웠는지 docker run으로 띄웠는지 확인
docker inspect vllm-serve --format '{{index .Config.Labels "com.docker.compose.project"}} {{index .Config.Labels "com.docker.compose.project.working_dir"}}'
```

- **값이 나오는 경우:** compose로 띄운 것입니다. 함께 나온 경로에 compose 파일이 있습니다.
- **비어 있는 경우:** `docker run`으로 띄운 것입니다.

## 1. 적용

`VLLM_BATCH_INVARIANT`는 환경변수라서 실행 중인 컨테이너에는 넣을 수 없습니다. **컨테이너를 다시 만들어야 합니다.**

### compose인 경우

compose 파일의 해당 서비스에 아래를 추가합니다.

```yaml
    environment:
      - VLLM_BATCH_INVARIANT=1
```

```bash
docker compose up -d        # 바뀐 서비스만 다시 만듦
```

### docker run인 경우

원래 실행 인자를 그대로 쓰고 `-e`만 하나 추가합니다.

```bash
# 원래 인자 확인 (vllm serve 뒤의 인자, 포트, 볼륨, GPU)
docker inspect vllm-serve --format '{{json .Config.Cmd}}'
docker inspect vllm-serve --format '{{json .HostConfig.PortBindings}} {{json .Mounts}}'

docker stop vllm-serve && docker rename vllm-serve vllm-serve-old   # 지우지 말고 이름만 바꿔 둠
docker run -d --name vllm-serve --gpus all -p 8007:8000 \
  -v <원래 볼륨들> \
  -e VLLM_BATCH_INVARIANT=1 \
  vllm/vllm-openai:v0.26.0 <원래 인자 그대로: --enable-lora --lora-modules ... --max-lora-rank 32 등>
```

- 원래 컨테이너는 지우지 말고 이름만 바꿔 두면 되돌리기 쉽습니다.
- 포트(`8007:8000`)와 볼륨은 백업한 `vllm-serve.before.json`의 값과 같은지 꼭 확인하세요.

## 2. 해제 (원래대로)

### compose인 경우

추가한 `VLLM_BATCH_INVARIANT=1` 줄을 지우고 `docker compose up -d`를 실행합니다.

### docker run인 경우

새 컨테이너를 내리고 원래 컨테이너를 되살립니다.

```bash
docker stop vllm-serve && docker rm vllm-serve
docker rename vllm-serve-old vllm-serve && docker start vllm-serve
```

## 3. 적용됐는지 확인

```bash
# (1) 실제로 돌고 있는 서버 프로세스(PID 1)의 환경변수. 가장 확실한 방법
docker exec vllm-serve sh -c 'tr "\0" "\n" < /proc/1/environ | grep VLLM_BATCH'
#  → VLLM_BATCH_INVARIANT=1 이 나오면 적용, 아무것도 안 나오면 미적용

# (2) 컨테이너 설정에 들어갔는지
docker inspect vllm-serve --format '{{range .Config.Env}}{{println .}}{{end}}' | grep VLLM_BATCH

# (3) 시작 로그: batch-invariant 관련 메시지, 경고, 오류
docker logs vllm-serve 2>&1 | grep -i -E "batch.?invariant|attention backend|lora" | head -50

# (4) 정상 기동 확인
curl -s localhost:8007/v1/models -H "Authorization: Bearer $키" | head
```

(3)에서 볼 것:
- **LoRA 관련 경고나 오류:** batch-invariant와 런타임 LoRA를 함께 쓸 수 있는지는 아직 확인하지 못했습니다. 기동이 실패하거나 경고가 뜨면 그 문구를 기록합니다.
- **어텐션 백엔드:** batch-invariant는 지원하는 백엔드에서만 동작합니다. 어떤 백엔드가 선택됐는지와, 백엔드를 바꿨다는 메시지가 있는지 확인합니다.
- 로그 문구는 버전마다 달라서 정확한 문장은 장담하지 못합니다. 그래서 grep 조건을 넓게 잡았습니다.

## 4. 시험 방법

### 응답

갈린 10개 질의를 3차와 같은 조건(순차 5, mixed 5, same 4)으로 140건 보내고, 3차 결과와 비교합니다.

### 속도

- **요청별 시간:** 응답 파일에 기록된 시간을 3차 같은 질의의 시간과 비교합니다.
- **서버 지표:** 적용 전과 후에 각각 받아 둡니다.
  ```bash
  curl -s localhost:8007/metrics | grep e2e_request_latency
  ```
- batch-invariant는 느려진다고 알려져 있습니다. 병렬 처리량이 얼마나 떨어지는지가 핵심입니다.

### 해석할 때 주의할 점

batch-invariant를 켜도 갈림이 남을 수 있습니다. 이 결과는 NeurIPS 2026 논문의 주장, 곧 런타임 LoRA 경로 자체가 비결정적이라는 주장과 맞습니다. 이때 2번 시험(LoRA 병합)과 비교하면 원인을 가를 수 있습니다.

| 결과 | 해석 |
|---|---|
| batch-invariant만으로 갈림이 사라짐 | 배치 구성에 따른 계산 순서 차이가 원인 |
| batch-invariant로는 남고, 병합하면 사라짐 | 런타임 LoRA 경로가 원인 |
| 둘 다 해야 사라짐 | 두 원인이 겹침 |
| 둘 다 해도 남음 | 다른 원인(prefix caching, CUDA graph 등)을 더 봐야 함 |

## 기록할 것

| 항목 | 적용 전 | 적용 후 |
|---|---|---|
| `/proc/1/environ`의 VLLM_BATCH_INVARIANT | 없음 | |
| 기동 로그의 경고·오류 | | |
| 선택된 어텐션 백엔드 | | |
| 140건 중 소수 답 (순차 / mixed / same) | 3차 결과 | |
| 갈린 질의 수 | 10 | |
| 요청당 평균 시간 (순차 / 병렬) | 3차 결과 | |

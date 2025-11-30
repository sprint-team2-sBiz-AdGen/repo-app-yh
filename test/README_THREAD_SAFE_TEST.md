# Thread-safe 모델 로딩 테스트 가이드

## 개요

여러 variants가 동시에 실행될 때 LLaVA 모델이 한 번만 로드되는지 확인하는 테스트입니다.

## 테스트 방법

### 1. 애플리케이션 재시작 (thread-safe 로딩 적용 확인)

```bash
# 애플리케이션 재시작
docker-compose restart yh

# 재시작 확인
docker logs feedlyai-work-yh --tail 20
```

### 2. Variants 생성 및 동시 트리거

기존 테스트 스크립트를 사용하여 여러 variants를 생성하고 동시에 트리거:

```bash
# 3개 variants 생성 및 트리거
python3 test/test_job_variants_pipeline.py --jobs 1 --variants-per-job 3
```

또는 더 많은 variants로 테스트:

```bash
# 5개 variants로 테스트
python3 test/test_job_variants_pipeline.py --jobs 1 --variants-per-job 5
```

### 3. 모델 로딩 횟수 확인

트리거 후 일정 시간(예: 2-3분) 대기한 후 로그 확인:

```bash
# Docker 로그에서 직접 확인
docker logs feedlyai-work-yh 2>&1 | grep -c "Loading LLaVa model"

# 또는 실시간 모니터링
docker logs -f feedlyai-work-yh 2>&1 | grep "Loading LLaVa model"
```

## 예상 결과

### ✅ 성공 케이스

```
📈 주요 지표:
  - 모델 로딩 시작: 1회
  - Checkpoint 로딩: 여러 회 (각 shard 진행률 표시)
  - 모델 로딩 완료: 1회
  - Meta tensor 오류: 0회

🔍 판단:
  ✅ 모델 로딩 시작이 1회만 발생했습니다!
     → Thread-safe 로딩이 정상적으로 작동합니다.
```

### ❌ 실패 케이스

```
📈 주요 지표:
  - 모델 로딩 시작: 3회 이상
  - Meta tensor 오류: 여러 회

🔍 판단:
  ❌ 모델 로딩 시작이 여러 회 발생했습니다
     → Thread-safe 로딩이 제대로 작동하지 않을 수 있습니다.
```

## 주의사항

1. **애플리케이션 재시작 필요**: Thread-safe 로딩 코드가 적용되려면 애플리케이션을 재시작해야 합니다.

2. **모델 로딩 시간**: 모델 로딩은 보통 1-2분 정도 소요됩니다. 테스트 전에 충분한 시간을 두세요.

3. **로그 시간 범위**: `--since` 옵션으로 로그 확인 시간 범위를 조정할 수 있습니다.

4. **Checkpoint 로딩 메시지**: "Loading checkpoint shards" 메시지는 여러 번 나타날 수 있지만, 이는 각 shard의 진행률 표시일 뿐 실제로는 한 번만 로드됩니다.

## 문제 해결

### 모델이 여러 번 로드되는 경우

1. `services/llava_service.py`에서 `_model_lock`이 제대로 사용되고 있는지 확인
2. Double-checked locking 패턴이 올바르게 구현되었는지 확인
3. 애플리케이션이 재시작되었는지 확인

### Meta tensor 오류 발생

1. PyTorch 버전 확인
2. `torch.nn.Module.to_empty()` 사용 여부 확인
3. 모델 로딩 로직에서 device mapping 확인

## 관련 파일

- `services/llava_service.py`: Thread-safe 모델 로딩 구현
- `test/test_thread_safe_model_loading.py`: 완전 자동화 테스트 스크립트
- `test/test_job_variants_pipeline.py`: Variants 생성 및 트리거 테스트

## 빠른 테스트 방법

가장 간단한 방법 (이미 성공한 테스트):

```bash
docker exec feedlyai-work-yh python3 -c "
import threading
import time
from services.llava_service import get_llava_model

results = []
lock = threading.Lock()

def request_model(thread_id):
    try:
        start_time = time.time()
        processor, model = get_llava_model()
        end_time = time.time()
        with lock:
            results.append({
                'thread_id': thread_id,
                'time': end_time - start_time,
                'model_id': id(model)
            })
            print(f'[Thread {thread_id}] 모델 로딩 완료 ({end_time - start_time:.2f}초)')
    except Exception as e:
        print(f'[Thread {thread_id}] 오류: {e}')

threads = []
for i in range(3):
    t = threading.Thread(target=request_model, args=(i+1,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

model_ids = [r.get('model_id') for r in results if 'model_id' in r]
unique_model_ids = len(set(model_ids)) if model_ids else 0
print(f'고유 모델 인스턴스: {unique_model_ids}개 (예상: 1개)')
"
```


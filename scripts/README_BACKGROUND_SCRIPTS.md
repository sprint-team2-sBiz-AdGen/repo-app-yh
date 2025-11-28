# 백그라운드 스크립트 사용 가이드

## 📋 개요

Job Variants 기반 파이프라인을 롱런 테스트하기 위한 백그라운드 스크립트입니다.

### 스크립트 목록

1. **`background_job_creator.py`**: 주기적으로 Job과 Job Variants를 생성하고 트리거를 발동
2. **`background_monitor_variants.py`**: 생성된 Job의 Variants 파이프라인 진행 상황을 모니터링

---

## 🚀 빠른 시작

### 자동 실행 (권장)

```bash
# 두 스크립트를 함께 실행
./scripts/run_background_test.sh --tenant-id longrun_test --create-interval 60

# 로그 확인
tail -f /tmp/job_creator.log
tail -f /tmp/job_monitor.log

# 종료
./scripts/stop_background_test.sh
```

### 수동 실행

```bash
# 터미널 1: Job 생성 스크립트
python scripts/background_job_creator.py \
    --tenant-id "longrun_test" \
    --create-interval 60 \
    --variants-count 3

# 터미널 2: 모니터링 스크립트
python scripts/background_monitor_variants.py \
    --tenant-id "longrun_test" \
    --check-interval 30 \
    --max-wait-minutes 20 \
    --scan-interval 10
```

---

## 📝 스크립트 상세 설명

### 1. `background_job_creator.py`

**기능**: 주기적으로 Job과 Job Variants를 생성하고 파이프라인을 시작합니다.

**주요 동작**:
- 설정된 간격마다 새로운 Job 생성
- 각 Job에 대해 지정된 개수의 Variants 생성
- 생성 후 자동으로 트리거 발동하여 파이프라인 시작
- 생성 통계 및 로그 출력

**사용 예시**:
```bash
python scripts/background_job_creator.py \
    --tenant-id "my_tenant" \
    --create-interval 60 \
    --variants-count 3
```

**파라미터**:
- `--tenant-id`: Tenant ID (기본: `background_job_creator_tenant`)
- `--create-interval`: Job 생성 간격 (초, 기본: 60)
- `--variants-count`: 각 Job당 생성할 Variant 개수 (기본: 3)

**출력 로그 예시**:
```
2025-11-28 12:00:00 - INFO - 새로운 job 생성 시작 (variants: 3개)...
2025-11-28 12:00:05 - INFO - ✓ Job 생성 완료: a1b2c3d4... (tenant: my_tenant, variants: 3개)
2025-11-28 12:00:06 - INFO - [Job a1b2c3d4...] 트리거 발동 완료 (3개 variants)
2025-11-28 12:00:06 - INFO - 📊 통계: 총 1개 job 생성 (경과 시간: 6초, 평균 간격: 6초)
```

---

### 2. `background_monitor_variants.py`

**기능**: 생성된 Job의 Variants 파이프라인 진행 상황을 실시간으로 모니터링합니다.

**주요 동작**:
- 주기적으로 새로운 Job 스캔
- 각 Job의 모든 Variants 상태 추적
- 단계별 진행 상황 로그 출력
- 완료/실패/타임아웃 감지

**사용 예시**:
```bash
python scripts/background_monitor_variants.py \
    --tenant-id "my_tenant" \
    --check-interval 30 \
    --max-wait-minutes 20 \
    --scan-interval 10
```

**파라미터**:
- `--tenant-id`: 모니터링할 Tenant ID (기본: 모든 tenant)
- `--check-interval`: 상태 확인 간격 (초, 기본: 30)
- `--max-wait-minutes`: 최대 대기 시간 (분, 기본: 20)
- `--scan-interval`: 새 Job 스캔 간격 (초, 기본: 10)

**출력 로그 예시**:
```
2025-11-28 12:00:10 - INFO - 새로운 job 발견: a1b2c3d4... (tenant: my_tenant, created: 2025-11-28 12:00:05)
2025-11-28 12:00:10 - INFO - [Job a1b2c3d4...] 모니터링 시작
2025-11-28 12:00:40 - INFO - [Job a1b2c3d4...] [ 30초] Job 전체: vlm_analyze (running)
2025-11-28 12:00:40 - INFO - [Job a1b2c3d4...] [ 30초] Variant 1: vlm_analyze (done)
2025-11-28 12:00:40 - INFO - [Job a1b2c3d4...] [ 30초] Variant 2: vlm_analyze (running)
2025-11-28 12:05:00 - INFO - [Job a1b2c3d4...] ✅ 파이프라인 완료! (총 300초 소요, 3개 variants)
```

---

## 🔧 롱런 테스트 시나리오

### 시나리오 1: 기본 테스트 (60초 간격)

```bash
# Job 생성: 60초마다 1개씩 생성
# 모니터링: 30초마다 상태 확인, 10초마다 새 Job 스캔

./scripts/run_background_test.sh \
    --tenant-id longrun_test \
    --create-interval 60 \
    --variants-count 3 \
    --check-interval 30 \
    --max-wait-minutes 20
```

### 시나리오 2: 부하 테스트 (30초 간격)

```bash
# Job 생성: 30초마다 1개씩 생성 (더 빠른 생성)
# 모니터링: 15초마다 상태 확인

./scripts/run_background_test.sh \
    --tenant-id stress_test \
    --create-interval 30 \
    --variants-count 3 \
    --check-interval 15 \
    --max-wait-minutes 20
```

### 시나리오 3: 다중 Variants 테스트

```bash
# Job 생성: 각 Job당 5개 Variants 생성

./scripts/run_background_test.sh \
    --tenant-id multi_variants_test \
    --create-interval 60 \
    --variants-count 5 \
    --check-interval 30 \
    --max-wait-minutes 30
```

---

## 📊 로그 확인

### 실시간 로그 확인

```bash
# Job 생성 로그
tail -f /tmp/job_creator.log

# 모니터링 로그
tail -f /tmp/job_monitor.log

# 두 로그 동시 확인
tail -f /tmp/job_creator.log /tmp/job_monitor.log
```

### 로그 필터링

```bash
# 에러만 확인
grep -i error /tmp/job_creator.log
grep -i error /tmp/job_monitor.log

# 완료된 Job만 확인
grep "파이프라인 완료" /tmp/job_monitor.log

# 특정 Job ID 추적
grep "a1b2c3d4" /tmp/job_monitor.log
```

---

## 🛑 종료 방법

### 자동 스크립트 사용

```bash
./scripts/stop_background_test.sh
```

### 수동 종료

```bash
# 프로세스 ID 확인
ps aux | grep background_job_creator
ps aux | grep background_monitor_variants

# 프로세스 종료
pkill -f background_job_creator
pkill -f background_monitor_variants

# Docker 컨테이너 내에서 종료
docker exec feedlyai-work-yh pkill -f background_job_creator
docker exec feedlyai-work-yh pkill -f background_monitor_variants
```

---

## 🐳 Docker 환경에서 실행

### Docker 컨테이너 내에서 실행

```bash
# Job 생성 스크립트
docker exec -d feedlyai-work-yh bash -c "cd /app && python scripts/background_job_creator.py --tenant-id longrun_test --create-interval 60 --variants-count 3 > /tmp/job_creator.log 2>&1"

# 모니터링 스크립트
docker exec -d feedlyai-work-yh bash -c "cd /app && python scripts/background_monitor_variants.py --tenant-id longrun_test --check-interval 30 --max-wait-minutes 20 --scan-interval 10 > /tmp/job_monitor.log 2>&1"
```

### 로그 확인

```bash
# Docker 컨테이너 내 로그 확인
docker exec feedlyai-work-yh tail -f /tmp/job_creator.log
docker exec feedlyai-work-yh tail -f /tmp/job_monitor.log
```

### 프로세스 확인

```bash
# Docker 컨테이너 내 프로세스 확인
docker exec feedlyai-work-yh ps aux | grep background
```

---

## 📈 모니터링 지표

### 생성 통계

Job 생성 스크립트 종료 시 다음 통계가 출력됩니다:
- 총 생성된 Job 개수
- 총 실행 시간
- 평균 생성 간격
- 최근 생성된 Job 목록 (최대 10개)

### 모니터링 통계

모니터링 스크립트는 다음 정보를 실시간으로 출력합니다:
- 발견된 Job 개수
- 각 Job의 진행 상황
- 각 Variant의 단계별 상태
- 완료/실패/타임아웃 알림

---

## ⚠️ 주의사항

1. **리소스 관리**: 생성 간격을 너무 짧게 설정하면 시스템 리소스 부족이 발생할 수 있습니다.
2. **로그 파일**: 로그 파일이 계속 쌓이므로 주기적으로 정리하거나 로테이션을 설정하세요.
3. **데이터베이스**: 많은 Job을 생성하면 데이터베이스 용량이 증가할 수 있습니다.
4. **네트워크**: Docker 환경에서는 네트워크 설정을 확인하세요.

---

## 🔍 문제 해결

### Job이 생성되지 않는 경우

1. 데이터베이스 연결 확인
2. 이미지 파일 경로 확인 (`pipeline_test/` 디렉토리)
3. 로그 파일에서 에러 메시지 확인

### 모니터링이 Job을 감지하지 않는 경우

1. Tenant ID가 일치하는지 확인
2. `scan-interval`을 줄여서 더 자주 스캔
3. 데이터베이스에서 Job이 실제로 생성되었는지 확인

### 파이프라인이 진행되지 않는 경우

1. 트리거가 정상 작동하는지 확인
2. `job_state_listener` 서비스가 실행 중인지 확인
3. 로그에서 에러 메시지 확인

---

## 📚 관련 문서

- `ANALYSIS_JOB_VARIANTS_PIPELINE.md`: Job Variants 파이프라인 구현 문서
- `test/test_job_variants_pipeline.py`: 단일 테스트 스크립트

---

**작성일**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 1.0.0


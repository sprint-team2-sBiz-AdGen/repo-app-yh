# 백그라운드 모니터링 스크립트 가이드

## 📋 개요

`scripts/background_monitor.py`는 백그라운드에서 계속 실행되면서 새로운 `img_gen` 완료 상태의 job을 감지하고, 파이프라인 진행 상황을 모니터링하는 스크립트입니다.

**작성일**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 1.0.0

---

## 🎯 주요 기능

1. **지속 실행**: 종료 신호(Ctrl+C)를 받을 때까지 계속 실행
2. **자동 감지**: 최근 1시간 내 생성된 `img_gen` 완료 상태의 job을 자동 감지
3. **파이프라인 모니터링**: 감지된 job의 파이프라인 진행 상황을 실시간으로 추적
4. **다중 job 지원**: 여러 job을 동시에 모니터링
5. **자동 생성 옵션**: 테스트를 위해 주기적으로 새 job을 생성할 수 있음

---

## 🚀 사용 방법

### 기본 사용법

#### 방법 1: 기존 job 모니터링만 (새로운 job이 생성되면 자동 감지)

```bash
# 포그라운드 실행 (로그 확인 가능)
docker exec feedlyai-work-yh python3 scripts/background_monitor.py

# 백그라운드 실행
docker exec -d feedlyai-work-yh python3 scripts/background_monitor.py
```

#### 방법 2: 자동으로 job 생성하면서 모니터링

```bash
# 60초마다 새 job 생성 (기본값)
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create

# 백그라운드 실행
docker exec -d feedlyai-work-yh python3 scripts/background_monitor.py --auto-create
```

#### 방법 3: 자동 생성 간격 지정

```bash
# 120초(2분)마다 새 job 생성
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create --create-interval 120

# 30초마다 새 job 생성
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create --create-interval 30
```

---

## 📊 실행 옵션

### `--auto-create`

- **설명**: 자동으로 job을 생성하는 모드 활성화
- **기본값**: False
- **사용 예**: `--auto-create`

### `--create-interval`

- **설명**: 자동 생성 간격 (초)
- **기본값**: 60초
- **사용 예**: `--create-interval 120`

---

## 🔍 동작 방식

### 1. 초기화

스크립트가 시작되면:
- 종료 신호 핸들러 등록 (SIGINT, SIGTERM)
- 모니터링 중인 job 목록 초기화
- 설정 정보 출력

### 2. 메인 루프

스크립트는 다음을 반복합니다:

1. **자동 생성 모드인 경우**:
   - 설정된 간격마다 새 job 생성
   - 생성된 job의 상태를 업데이트하여 트리거 발동
   - 모니터링 목록에 추가

2. **새로운 job 찾기**:
   - 최근 1시간 내 생성된 `img_gen` 완료 상태의 job 검색
   - 아직 모니터링하지 않은 job을 발견하면 모니터링 목록에 추가

3. **모니터링 중인 job 상태 확인**:
   - 각 job의 현재 상태 확인
   - 단계 변경 시 로그 출력
   - 완료/실패/타임아웃 시 모니터링 목록에서 제거

### 3. 종료

- Ctrl+C 또는 종료 신호 수신 시 안전하게 종료
- 모니터링 중인 모든 job의 상태를 정리

---

## 📝 로그 출력 예시

### 시작 로그

```
============================================================
백그라운드 모니터링 시작
============================================================
자동 생성: True
생성 간격: 60초
종료하려면 Ctrl+C를 누르세요
============================================================
```

### Job 생성 로그

```
2025-11-28 15:00:00 - INFO - 새로운 job 생성 중...
2025-11-28 15:00:01 - INFO - ✓ Job 생성 완료: 3b87ab59-5d77-4904-ab7a-1669bdd64d47
2025-11-28 15:00:02 - INFO - ✓ 트리거 발동: 3b87ab59-5d77-4904-ab7a-1669bdd64d47
```

### Job 발견 로그

```
2025-11-28 15:01:00 - INFO - 새로운 job 발견: 32e2cfbe-962e-4df3-8391-5c55fbeb5628
```

### 파이프라인 진행 로그

```
2025-11-28 15:00:05 - INFO - [Job 3b87ab59...] [  5초] img_gen - Status: done
2025-11-28 15:02:30 - INFO - [Job 3b87ab59...] [150초] vlm_analyze - Status: done
2025-11-28 15:03:15 - INFO - [Job 3b87ab59...] [195초] yolo_detect - Status: done
2025-11-28 15:03:20 - INFO - [Job 3b87ab59...] [200초] planner - Status: done
2025-11-28 15:03:25 - INFO - [Job 3b87ab59...] [205초] overlay - Status: done
2025-11-28 15:05:00 - INFO - [Job 3b87ab59...] [300초] vlm_judge - Status: done
2025-11-28 15:05:30 - INFO - [Job 3b87ab59...] [330초] ocr_eval - Status: done
2025-11-28 15:05:35 - INFO - [Job 3b87ab59...] [335초] readability_eval - Status: done
2025-11-28 15:05:40 - INFO - [Job 3b87ab59...] [340초] iou_eval - Status: done
2025-11-28 15:05:40 - INFO - [Job 3b87ab59...] ✅ 파이프라인 완료! (총 340초 소요)
```

### 실패/타임아웃 로그

```
2025-11-28 15:10:00 - WARNING - [Job 3b87ab59...] ❌ 파이프라인 실패: vlm_analyze 단계에서 실패 (총 300초 소요)
2025-11-28 15:15:00 - WARNING - [Job 3b87ab59...] ⚠ 타임아웃: 10분 내에 파이프라인이 완료되지 않았습니다.
```

---

## 🔧 고급 사용법

### 백그라운드 실행 및 로그 확인

```bash
# 백그라운드로 실행
docker exec -d feedlyai-work-yh python3 scripts/background_monitor.py --auto-create

# 로그 확인 (Docker 컨테이너 로그)
docker logs feedlyai-work-yh | grep "백그라운드 모니터링"

# 실시간 로그 확인
docker logs -f feedlyai-work-yh | grep -E "백그라운드 모니터링|Job.*초"
```

### 여러 인스턴스 실행

```bash
# 서로 다른 tenant_id로 여러 인스턴스 실행 가능
# (코드 수정 필요: tenant_id 파라미터 추가)
```

### 프로세스 확인

```bash
# 실행 중인 프로세스 확인
docker exec feedlyai-work-yh ps aux | grep background_monitor

# 프로세스 종료
docker exec feedlyai-work-yh pkill -f background_monitor
```

---

## ⚙️ 설정 및 커스터마이징

### 모니터링 범위 변경

`find_new_jobs()` 함수에서 다음을 수정할 수 있습니다:

- **시간 범위**: `created_at > NOW() - INTERVAL '1 hour'` → 원하는 시간으로 변경
- **최대 개수**: `LIMIT 10` → 원하는 개수로 변경
- **Tenant ID**: 기본값 `"background_monitor_tenant"` → 원하는 tenant_id로 변경

### 모니터링 간격 조정

- **Job 상태 확인 간격**: `time.sleep(5)` → 원하는 초로 변경
- **새 job 검색 간격**: `time.sleep(5)` 또는 `time.sleep(2)` → 원하는 초로 변경

### 타임아웃 설정

`monitor_job()` 함수에서:

- **타임아웃 시간**: `600` (10분) → 원하는 초로 변경

---

## 🐛 문제 해결

### 문제 1: Job이 감지되지 않음

**원인**: 
- Tenant ID가 일치하지 않음
- Job이 1시간 이전에 생성됨
- Job의 `current_step`이 `img_gen`이 아님

**해결**:
- `find_new_jobs()` 함수의 tenant_id 확인
- 시간 범위 확인 (`INTERVAL '1 hour'`)
- Job 상태 확인

### 문제 2: 파이프라인이 진행되지 않음

**원인**:
- 백그라운드 리스너가 실행되지 않음
- PostgreSQL 트리거가 작동하지 않음

**해결**:
```bash
# 리스너 상태 확인
docker logs feedlyai-work-yh | grep "Job State Listener"

# 트리거 확인
docker exec feedlyai-work-yh python3 test/test_trigger_verification.py
```

### 문제 3: 스크립트가 종료되지 않음

**원인**:
- 모니터링 중인 job이 계속 실행 중
- 무한 루프

**해결**:
- Ctrl+C를 여러 번 누르기
- 프로세스 강제 종료: `docker exec feedlyai-work-yh pkill -f test_background_monitor`

---

## 📊 성능 고려사항

### 데이터베이스 쿼리 최적화

- **인덱스**: `jobs` 테이블의 `tenant_id`, `current_step`, `status`, `created_at`에 인덱스가 있는지 확인
- **쿼리 빈도**: 너무 자주 쿼리하지 않도록 적절한 간격 유지

### 리소스 사용

- **메모리**: 모니터링 중인 job 수가 많아지면 메모리 사용량 증가
- **CPU**: 모니터링 간격이 너무 짧으면 CPU 사용량 증가

---

## 🔄 백그라운드 리스너와의 관계

이 스크립트는 **백그라운드 리스너와 독립적으로** 작동합니다:

- **백그라운드 리스너**: FastAPI 애플리케이션의 lifespan 이벤트로 자동 시작, NOTIFY 이벤트를 받아 파이프라인 트리거
- **모니터링 스크립트**: job 상태를 주기적으로 확인하여 진행 상황을 로그로 출력

두 시스템이 함께 작동하여:
1. 리스너가 파이프라인을 자동으로 실행
2. 모니터링 스크립트가 진행 상황을 추적

---

## 📝 사용 시나리오

### 시나리오 1: 개발 중 테스트

```bash
# 자동으로 job 생성하면서 모니터링 (60초마다)
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create --create-interval 60
```

### 시나리오 2: 프로덕션 모니터링

```bash
# 기존 job만 모니터링 (새 job이 생성되면 자동 감지)
docker exec -d feedlyai-work-yh python3 scripts/background_monitor.py
```

### 시나리오 3: 부하 테스트

```bash
# 짧은 간격으로 job 생성 (30초마다)
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create --create-interval 30
```

---

## 🧪 테스트

### 단위 테스트

```bash
# 스크립트가 정상적으로 시작되는지 확인
docker exec feedlyai-work-yh python3 scripts/background_monitor.py --help
```

### 통합 테스트

```bash
# 자동 생성 모드로 1분 실행 후 종료
timeout 60 docker exec feedlyai-work-yh python3 scripts/background_monitor.py --auto-create --create-interval 30
```

---

## 📚 관련 문서

- `DOCS_BACKGROUND_EXECUTION.md`: 백그라운드 실행 가이드
- `DOCS_PIPELINE_COMPLETE.md`: 파이프라인 전체 분석 문서
- `DOCS_JOB_STATE_LISTENER.md`: Job State Listener 사용 가이드

---

## ❓ FAQ

**Q: 이 스크립트를 프로덕션에서 사용해도 되나요?**  
A: 모니터링 목적으로는 사용 가능하지만, 자동 생성 모드(`--auto-create`)는 테스트 환경에서만 사용하는 것을 권장합니다.

**Q: 여러 인스턴스를 동시에 실행할 수 있나요?**  
A: 네, 가능합니다. 하지만 같은 tenant_id를 사용하면 중복 모니터링이 발생할 수 있으므로 주의하세요.

**Q: 스크립트를 종료해도 파이프라인은 계속 실행되나요?**  
A: 네, 파이프라인은 백그라운드 리스너에 의해 자동으로 실행되므로, 모니터링 스크립트를 종료해도 파이프라인은 계속 진행됩니다.

**Q: 모니터링 중인 job 목록을 확인할 수 있나요?**  
A: 현재는 로그를 통해서만 확인 가능합니다. 향후 개선 예정입니다.

---

## 🔄 변경 이력

### v1.0.0 (2025-11-28)
- 초기 버전
- 기본 모니터링 기능
- 자동 생성 옵션
- 다중 job 모니터링 지원

---

**최종 업데이트**: 2025-11-28  
**문서 버전**: 1.0.0


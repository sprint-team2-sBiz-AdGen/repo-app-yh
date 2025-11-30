# Job이 iou_eval, done으로 업데이트되지 않는 문제 분석

## 🔍 문제 상황

### 증상
- **Job ID**: `9bf79f72-ebdd-4a2c-9094-670d5fc8efb8`
- **Job 상태**: `status = 'running'`, `current_step = 'iou_eval'`
- **Variants 상태**: 모든 variants가 `iou_eval, done` (3개 모두 완료)
- **문제**: Job이 `done`으로 업데이트되지 않음

### 발생 시점
- Variants가 거의 동시에 완료됨 (약 0.1초 차이)
  - Variant 1: `2025-11-29 01:11:09.787740`
  - Variant 2: `2025-11-29 01:11:09.921800`
  - Variant 3: `2025-11-29 01:11:09.928518`

---

## 📊 트리거 함수 분석

### 트리거 조건
```sql
CREATE TRIGGER check_all_variants_done_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    WHEN (NEW.status = 'done' OR NEW.status = 'failed')
    EXECUTE FUNCTION check_all_variants_done();
```

**중요**: 트리거는 각 variant가 `done` 또는 `failed`로 변경될 때마다 실행됩니다.

### iou_eval 특별 처리 로직
```sql
IF NEW.current_step = 'iou_eval' AND NEW.status = 'done' THEN
    -- iou_eval에서 done인 variant 개수 확인
    SELECT COUNT(*) INTO iou_eval_done_count
    FROM jobs_variants
    WHERE job_id = NEW.job_id
      AND current_step = 'iou_eval'
      AND status = 'done';
    
    -- 모든 variants가 iou_eval, done인 경우에만 job을 done으로 업데이트
    IF iou_eval_done_count = total_count 
       AND running_count = 0 
       AND queued_count = 0 
       AND failed_count = 0 THEN
        job_status := 'done';
        job_current_step := 'iou_eval';
    ELSE
        job_status := 'running';
        job_current_step := 'iou_eval';
    END IF;
END IF;
```

---

## 🔍 가능한 원인 분석

### 원인 1: 트리거 실행 시점 문제 (가능성 높음)

**시나리오**:
1. Variant 1이 `iou_eval, done`으로 변경 → 트리거 실행
   - 이 시점: `iou_eval_done_count = 1`, `total_count = 3`
   - 조건 불만족 → Job을 `running`으로 유지
2. Variant 2가 `iou_eval, done`으로 변경 → 트리거 실행
   - 이 시점: `iou_eval_done_count = 2`, `total_count = 3`
   - 조건 불만족 → Job을 `running`으로 유지
3. Variant 3이 `iou_eval, done`으로 변경 → 트리거 실행
   - 이 시점: `iou_eval_done_count = 3`, `total_count = 3`
   - 조건 만족 → Job을 `done`으로 업데이트 **해야 함**

**문제**: Variant 3의 트리거가 실행되었어야 하는데, Job이 `done`으로 업데이트되지 않았다는 것은:
- 트리거가 실행되지 않았거나
- 트리거가 실행되었지만 조건을 만족하지 못했거나
- UPDATE 문이 실행되지 않았을 가능성

### 원인 2: 트랜잭션 동시성 문제

**시나리오**:
- 여러 variants가 거의 동시에 업데이트됨
- 각 트리거가 서로 다른 트랜잭션에서 실행됨
- 트리거 실행 시점에 다른 variants의 상태가 아직 커밋되지 않았을 수 있음

**하지만**: PostgreSQL의 트리거는 같은 트랜잭션 내에서 실행되므로, 이 문제는 발생하지 않아야 함.

### 원인 3: UPDATE 문 조건 불만족

```sql
UPDATE jobs 
SET status = job_status,
    current_step = job_current_step,
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = NEW.job_id
  AND (status IS DISTINCT FROM job_status 
       OR current_step IS DISTINCT FROM job_current_step);
```

**문제**: 만약 `job_status = 'running'`이고 현재 Job의 `status`도 `'running'`이면, UPDATE 문이 실행되지 않음.

**하지만**: 마지막 variant의 트리거에서는 `job_status = 'done'`이어야 하므로, 이 문제는 발생하지 않아야 함.

---

## ✅ 해결 방안

### 방안 1: 트리거 함수에 로깅 추가 (완료)

**목적**: 트리거가 실행되었는지, 조건을 만족했는지 확인

**구현**:
```sql
-- iou_eval 단계 특별 처리
IF NEW.current_step = 'iou_eval' AND NEW.status = 'done' THEN
    -- ... (기존 로직) ...
    
    -- 로깅 추가
    RAISE NOTICE '[TRIGGER] iou_eval done 체크: job_id=%, variant_id=%, iou_done=%, total=%, running=%, queued=%, failed=%', 
        NEW.job_id, NEW.job_variants_id, iou_eval_done_count, total_count, running_count, queued_count, failed_count;
    
    IF iou_eval_done_count = total_count AND running_count = 0 AND queued_count = 0 AND failed_count = 0 THEN
        job_status := 'done';
        job_current_step := 'iou_eval';
        RAISE NOTICE '[TRIGGER] ✅ Job을 done으로 업데이트: job_id=%', NEW.job_id;
    ELSE
        job_status := 'running';
        job_current_step := 'iou_eval';
        RAISE NOTICE '[TRIGGER] ❌ Job을 done으로 업데이트하지 않음: job_id=%, 조건 불만족', NEW.job_id;
    END IF;
END IF;
```

**확인 방법**:
```bash
# PostgreSQL 로그 확인
docker logs feedlyai-postgres | grep "\[TRIGGER\]"
```

### 방안 2: 수동 복구 로직 추가 (✅ 구현 완료)

**목적**: 트리거가 작동하지 않는 경우를 대비하여 주기적으로 확인하고 수정

**구현 위치**: `services/job_state_listener.py`

**구현 내용**:
- `_periodic_recovery_check()`: 주기적으로 실행되는 백그라운드 태스크 (기본 1분 간격)
- `_check_and_fix_iou_eval_jobs()`: iou_eval 단계에서 모든 variants가 done인데 job이 done이 아닌 경우 수정

**동작 방식**:
1. 리스너 시작 시 백그라운드 태스크로 `_periodic_recovery_check()` 실행
2. 매 1분마다 (기본값) `_check_and_fix_iou_eval_jobs()` 호출
3. 다음 조건을 만족하는 job 찾기:
   - `current_step = 'iou_eval'`
   - `status = 'running'`
   - 모든 variants가 `iou_eval, done`
   - `failed`, `running`, `queued` variant 없음
4. 조건을 만족하는 job을 `done`으로 업데이트

**로깅**:
- 복구 대상 발견 시: `WARNING` 레벨
- 복구 완료 시: `INFO` 레벨 (job_id, variants 개수 포함)
- 오류 발생 시: `ERROR` 레벨

**설정**:
- 체크 간격: `self.recovery_check_interval = 60` (초, 기본 1분)
- 환경 변수로 변경 가능하도록 확장 가능

### 방안 3: 트리거 실행 보장

**목적**: 마지막 variant가 완료될 때 트리거가 확실히 실행되도록 보장

**구현**: 
- 트리거 함수에서 `iou_eval_done_count`를 계산할 때, `NEW` 레코드가 이미 포함되어 있는지 확인
- 현재 로직은 이미 `NEW` 레코드를 포함하여 계산하므로 문제 없음

**하지만**: 트리거가 실행되지 않는 경우를 대비하여, 주기적으로 확인하는 로직 추가 권장

---

## 🔧 구현 체크리스트

### Phase 1: 디버깅 (완료)
- [x] 트리거 함수에 로깅 추가
- [ ] PostgreSQL 로그 확인하여 트리거 실행 여부 확인
- [ ] 트리거 실행 시점의 데이터 상태 확인

### Phase 2: 수동 복구 로직 (✅ 완료)
- [x] `_check_and_fix_iou_eval_jobs()` 함수 구현
- [x] 주기적으로 실행하는 백그라운드 태스크 추가 (1분마다)
- [x] 리스너 시작/중지 시 태스크 관리
- [x] 로깅 및 오류 처리

### Phase 3: 근본 원인 해결
- [ ] 트리거가 실행되지 않는 원인 파악
- [ ] 트리거 실행 보장 메커니즘 추가
- [ ] 테스트 및 검증

---

## 📝 참고사항

### 트리거 실행 순서
1. Variant 1 업데이트 → 트리거 실행 → Job 상태 확인 → 조건 불만족 → `running` 유지
2. Variant 2 업데이트 → 트리거 실행 → Job 상태 확인 → 조건 불만족 → `running` 유지
3. Variant 3 업데이트 → 트리거 실행 → Job 상태 확인 → 조건 만족 → `done`으로 업데이트 **해야 함**

### 트리거 실행 보장
- PostgreSQL 트리거는 트랜잭션 내에서 실행되므로, UPDATE가 커밋되면 트리거도 실행됨
- 트리거가 실행되지 않는 경우는 매우 드뭄
- 대부분의 경우 트리거가 실행되었지만 조건을 만족하지 못했을 가능성이 높음

### 로깅 확인 방법
```bash
# PostgreSQL 로그 확인
docker logs feedlyai-postgres --since 1h | grep "\[TRIGGER\]"

# 또는 실시간 모니터링
docker logs -f feedlyai-postgres | grep "\[TRIGGER\]"
```

---

---

## ✅ 최종 해결 방안 요약

### 구현 완료 사항

1. **트리거 함수 로깅 추가** (✅ 완료)
   - `iou_eval` 단계 처리 시 상세 로깅
   - 트리거 실행 여부 및 조건 만족 여부 확인 가능
   - PostgreSQL 로그에서 `[TRIGGER]` 태그로 확인

2. **수동 복구 로직 추가** (✅ 완료)
   - 주기적 백그라운드 체크 (기본 1분 간격)
   - 트리거가 작동하지 않는 경우 자동 복구
   - 최대 1분 내에 문제 해결

### 동작 보장

- **1차 방어**: PostgreSQL 트리거 (실시간)
- **2차 방어**: 수동 복구 로직 (주기적 체크)

두 가지 메커니즘으로 문제 발생 시 자동 복구가 보장됩니다.

---

**작성일**: 2025-11-29  
**최종 업데이트**: 2025-11-29  
**작성자**: LEEYH205  
**버전**: 1.1.0


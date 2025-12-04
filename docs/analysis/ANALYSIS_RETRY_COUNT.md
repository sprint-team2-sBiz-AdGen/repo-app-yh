# Retry Count 컬럼 추가 분석

## 🎯 목적

`jobs` 테이블과 `jobs_variants` 테이블에 `retry_count` 컬럼을 추가하여 재시도 횟수를 추적하고 분석에 활용합니다.

---

## 📊 구현 사항

### 1. 스키마 변경

**파일**: `db/init/04_add_retry_count.sql`

**변경 내용**:
- `jobs` 테이블에 `retry_count INTEGER DEFAULT 0` 컬럼 추가
- `jobs_variants` 테이블에 `retry_count INTEGER DEFAULT 0` 컬럼 추가
- 인덱스 추가 (조회 성능 향상)

**인덱스**:
- `idx_jobs_retry_count`: jobs.retry_count
- `idx_jobs_status_retry_count`: jobs(status, retry_count)
- `idx_jobs_variants_retry_count`: jobs_variants.retry_count
- `idx_jobs_variants_status_retry_count`: jobs_variants(status, retry_count)
- `idx_jobs_variants_job_id_retry_count`: jobs_variants(job_id, retry_count)

### 2. 재시도 로직 업데이트

**파일**: `services/job_state_listener.py`

**업데이트된 함수**:

#### 2-1. `_recover_stuck_variants()` - 뒤처진 variant 재시작

**위치**: Variant가 `done` 상태이고 Job보다 뒤처진 경우

```python
# retry_count 증가
await conn.execute("""
    UPDATE jobs_variants
    SET retry_count = retry_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = $1
""", variant_id)
```

**로깅**: `retry_count` 포함하여 로깅

#### 2-2. `_recover_stuck_variants()` - failed variant 재시도

**위치**: Variant가 `failed` 상태인 경우

```python
# retry_count 증가 및 failed 상태를 done으로 변경
await conn.execute("""
    UPDATE jobs_variants
    SET status = 'done',
        retry_count = retry_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = $1
""", variant_id)
```

**로깅**: `retry_count` 포함하여 로깅

#### 2-3. `_process_job_variant_state_change()` - 멈춘 variant 재시도

**위치**: 5분 이상 업데이트되지 않은 done 상태 variant

```python
# retry_count 증가 및 상태를 다시 업데이트하여 트리거 발동
await conn.execute("""
    UPDATE jobs_variants
    SET retry_count = retry_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = $1
""", uuid.UUID(stuck_id))
```

**로깅**: `retry_count` 포함하여 로깅

#### 2-4. `_check_and_fix_iou_eval_jobs()` - 수동 복구

**위치**: iou_eval 단계에서 모든 variants가 done인데 job이 done이 아닌 경우

```python
# Job을 done으로 업데이트 (수동 복구이므로 retry_count 증가)
result = await conn.execute("""
    UPDATE jobs
    SET status = 'done',
        current_step = 'iou_eval',
        retry_count = retry_count + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE job_id = $1
      AND status = 'running'
      AND current_step = 'iou_eval'
""", job_id)
```

**로깅**: `retry_count` 포함하여 로깅

---

## 📈 활용 방안

### 1. 문제 분석

**재시도가 많은 Job/Variant 식별**:
```sql
-- 재시도가 많은 job 조회
SELECT job_id, status, current_step, retry_count, created_at, updated_at
FROM jobs
WHERE retry_count > 0
ORDER BY retry_count DESC, updated_at DESC
LIMIT 10;

-- 재시도가 많은 variant 조회
SELECT 
    jv.job_variants_id,
    jv.job_id,
    jv.creation_order,
    jv.status,
    jv.current_step,
    jv.retry_count,
    j.status as job_status,
    j.current_step as job_current_step
FROM jobs_variants jv
INNER JOIN jobs j ON jv.job_id = j.job_id
WHERE jv.retry_count > 0
ORDER BY jv.retry_count DESC, jv.updated_at DESC
LIMIT 20;
```

### 2. 통계 분석

**재시도 통계**:
```sql
-- Job별 재시도 통계
SELECT 
    COUNT(*) as total_jobs,
    COUNT(*) FILTER (WHERE retry_count = 0) as no_retry,
    COUNT(*) FILTER (WHERE retry_count > 0) as has_retry,
    COUNT(*) FILTER (WHERE retry_count >= 3) as high_retry,
    AVG(retry_count) as avg_retry_count,
    MAX(retry_count) as max_retry_count
FROM jobs
WHERE created_at >= NOW() - INTERVAL '7 days';

-- Variant별 재시도 통계
SELECT 
    COUNT(*) as total_variants,
    COUNT(*) FILTER (WHERE retry_count = 0) as no_retry,
    COUNT(*) FILTER (WHERE retry_count > 0) as has_retry,
    COUNT(*) FILTER (WHERE retry_count >= 3) as high_retry,
    AVG(retry_count) as avg_retry_count,
    MAX(retry_count) as max_retry_count
FROM jobs_variants
WHERE created_at >= NOW() - INTERVAL '7 days';
```

### 3. 최대 재시도 횟수 제한

**구현 예시**:
```python
# 최대 재시도 횟수 (예: 3회)
MAX_RETRY_COUNT = 3

# 재시도 전 확인
current_retry = await conn.fetchval("""
    SELECT retry_count
    FROM jobs_variants
    WHERE job_variants_id = $1
""", variant_id)

if current_retry >= MAX_RETRY_COUNT:
    logger.warning(
        f"최대 재시도 횟수 초과: job_variants_id={variant_id}, "
        f"retry_count={current_retry}"
    )
    # 추가 처리 (예: 알림, 수동 개입 필요)
    return
```

### 4. 모니터링 및 알림

**재시도가 많은 Job/Variant 모니터링**:
```sql
-- 재시도가 많은 job (알림 대상)
SELECT job_id, status, current_step, retry_count
FROM jobs
WHERE retry_count >= 3
  AND status IN ('running', 'failed')
  AND updated_at >= NOW() - INTERVAL '1 hour';

-- 재시도가 많은 variant (알림 대상)
SELECT 
    jv.job_variants_id,
    jv.job_id,
    jv.status,
    jv.current_step,
    jv.retry_count,
    j.status as job_status
FROM jobs_variants jv
INNER JOIN jobs j ON jv.job_id = j.job_id
WHERE jv.retry_count >= 3
  AND jv.status IN ('running', 'failed')
  AND jv.updated_at >= NOW() - INTERVAL '1 hour';
```

---

## 🔍 재시도 발생 시나리오

### 시나리오 1: 뒤처진 Variant 재시작

**조건**:
- Job이 `running` 상태이고 yh 파트 단계
- Variant가 Job의 `current_step`보다 뒤처짐
- Variant가 `done` 상태

**동작**:
1. Variant의 `retry_count` 증가
2. 다음 단계 트리거
3. 로그에 `retry_count` 포함

### 시나리오 2: Failed Variant 재시도

**조건**:
- Job이 `running` 또는 `failed` 상태이고 yh 파트 단계
- Variant가 `failed` 상태

**동작**:
1. Variant의 `retry_count` 증가
2. Variant 상태를 `done`으로 변경
3. 다음 단계 트리거
4. 로그에 `retry_count` 포함

### 시나리오 3: 멈춘 Variant 재시도

**조건**:
- Variant가 `done` 상태
- 5분 이상 업데이트되지 않음
- 같은 job의 다른 variant가 더 진행됨

**동작**:
1. Variant의 `retry_count` 증가
2. `updated_at` 업데이트하여 트리거 발동
3. 로그에 `retry_count` 포함

### 시나리오 4: 수동 복구 (iou_eval)

**조건**:
- `current_step = 'iou_eval'`
- `status = 'running'`
- 모든 variants가 `iou_eval, done`

**동작**:
1. Job의 `retry_count` 증가
2. Job 상태를 `done`으로 업데이트
3. 로그에 `retry_count` 포함

---

## 📊 예상 효과

### 1. 문제 분석 개선

- **재시도 패턴 파악**: 어떤 단계에서 재시도가 많이 발생하는지 분석 가능
- **문제 Job/Variant 식별**: 재시도가 많은 항목을 빠르게 찾을 수 있음
- **근본 원인 분석**: 재시도가 발생하는 원인을 데이터로 추적 가능

### 2. 시스템 안정성 향상

- **최대 재시도 제한**: 무한 재시도 방지
- **모니터링 강화**: 재시도가 많은 항목에 대한 알림 가능
- **성능 최적화**: 재시도가 많은 단계를 식별하여 개선 가능

### 3. 통계 및 리포팅

- **재시도율 계산**: 전체 Job/Variant 중 재시도가 발생한 비율
- **트렌드 분석**: 시간에 따른 재시도 패턴 분석
- **성능 지표**: 재시도율을 성능 지표로 활용

---

## 🔧 향후 개선 사항

### 1. 최대 재시도 횟수 제한

- 환경 변수로 설정 가능하도록 구현
- 최대 횟수 초과 시 알림 또는 수동 개입 필요 상태로 표시

### 2. 재시도 원인 추적

- `retry_reason` 컬럼 추가 고려
- 재시도가 발생한 이유를 기록 (예: 'stuck', 'failed', 'manual_recovery')

### 3. 재시도 히스토리

- 별도 테이블에 재시도 이력 저장
- 재시도 시점, 이유, 결과 등을 기록

### 4. 대시보드 통합

- 재시도 통계를 대시보드에 표시
- 실시간 모니터링 및 알림

---

## 📝 참고사항

### 주의사항

1. **재시도 카운트 증가 시점**: 재시도 시도 시점에 증가 (성공 여부와 무관)
2. **트랜잭션**: retry_count 증가는 재시도 로직과 같은 트랜잭션 내에서 실행
3. **인덱스**: 조회 성능을 위해 인덱스 추가됨

### 데이터 마이그레이션

- 기존 레코드의 `retry_count`는 `0`으로 초기화됨 (DEFAULT 0)
- 마이그레이션 파일 실행 시 기존 데이터에 영향 없음

---

**작성일**: 2025-11-29  
**작성자**: LEEYH205  
**버전**: 1.0.0


# YE 파트 트리거 가이드

## 📋 개요

이 문서는 YE 파트(이미지 생성) 개발자가 파이프라인 자동 트리거 메커니즘을 이해하고 구현하는 데 도움을 주기 위해 작성되었습니다.

**작성일**: 2025-12-02  
**버전**: 1.1.0  
**작성자**: LEEYH205

---

## 🎯 YE 파트의 역할

YE 파트는 다음 단계를 수행합니다:

1. **입력**: `user_img_input (done)` 상태의 `jobs_variants` 레코드 수신
2. **처리**: `img_gen` 단계 실행 (실제 이미지 생성)
3. **출력**: `img_gen (done)` 상태로 업데이트 → **자동 트리거 발동**

---

## 🔄 전체 흐름 (간단 버전)

```
[1] background_ye_pipeline_test.py
    ↓
    user_img_input (done) 상태로 Job 생성
    ↓
[2] YE 파트 코드
    ↓
    user_img_input (done) 상태의 variants 조회
    ↓
    img_gen 실행 (이미지 생성)
    ↓
    jobs_variants 상태 업데이트: img_gen (done)
    ↓
[3] PostgreSQL 트리거 (자동)
    ↓
    NOTIFY 이벤트 발행
    ↓
[4] FastAPI 리스너 (자동)
    ↓
    이벤트 감지
    ↓
[5] pipeline_trigger.py (자동)
    ↓
    다음 단계 API 호출: /api/yh/llava/stage1/validate
    ↓
[6] YH 파트 파이프라인 자동 진행
    ↓
    (vlm_analyze → yolo_detect → ... → 완료)
```

---

## 💻 구현 방법

### 1단계: 처리할 Variants 조회

YE 파트는 `user_img_input (done)` 상태의 variants를 조회해야 합니다.

```python
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # user_img_input (done) 상태의 variants 조회
    variants = db.execute(text("""
        SELECT 
            jv.job_variants_id,
            jv.job_id,
            jv.img_asset_id,
            jv.status,
            jv.current_step
        FROM jobs_variants jv
        WHERE jv.current_step = 'user_img_input'
            AND jv.status = 'done'
        ORDER BY jv.created_at ASC
        LIMIT 10  -- 한 번에 처리할 개수
    """)).fetchall()
    
    for variant in variants:
        job_variants_id = variant[0]
        job_id = variant[1]
        img_asset_id = variant[2]
        
        # img_gen 처리
        process_img_gen(db, job_variants_id, img_asset_id)
finally:
    db.close()
```

### 2단계: img_gen 실행 및 상태 업데이트

**핵심**: 상태를 `img_gen (done)`으로 업데이트하면 **자동으로 트리거가 발동**됩니다.

```python
def process_img_gen(db, job_variants_id: str, img_asset_id: str):
    """img_gen 처리 및 상태 업데이트"""
    
    # 1. img_gen 실행 중 상태로 변경 (선택적)
    db.execute(text("""
        UPDATE jobs_variants
        SET status = 'running',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id})
    db.commit()
    
    # 2. 실제 이미지 생성 (YE 파트의 실제 로직)
    # 예시:
    # generated_image = your_image_generation_function(img_asset_id)
    # save_generated_image(generated_image)
    
    # 3. ⭐ 중요: img_gen 완료 상태로 업데이트 (이것이 트리거를 발동시킵니다!)
    db.execute(text("""
        UPDATE jobs_variants
        SET status = 'done',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id})
    db.commit()
    
    # 4. 완료! PostgreSQL 트리거가 자동으로 발동되어
    #    YH 파트 파이프라인이 자동으로 시작됩니다.
```

---

## 🔍 자동 트리거 메커니즘 (상세)

### 트리거 발동 조건

다음 조건을 만족하면 **자동으로 트리거가 발동**됩니다:

1. `jobs_variants` 테이블의 레코드가 업데이트됨
2. `current_step` 또는 `status`가 실제로 변경됨
3. `status = 'done'`이고 `current_step = 'img_gen'`

### 트리거 동작 순서

1. **PostgreSQL 트리거** (`db/init/03_job_variants_state_notify_trigger.sql`)
   - `jobs_variants` 테이블 업데이트 감지
   - `pg_notify('job_variant_state_changed', json_data)` 실행

2. **FastAPI 리스너** (`services/job_state_listener.py`)
   - PostgreSQL `LISTEN`으로 이벤트 수신
   - `_process_job_variant_state_change()` 호출

3. **파이프라인 트리거** (`services/pipeline_trigger.py`)
   - `current_step='img_gen'`, `status='done'` 확인
   - 다음 단계: `vlm_analyze`
   - API 호출: `POST /api/yh/llava/stage1/validate`

4. **YH 파트 파이프라인 자동 진행**
   - 각 단계가 완료되면 다음 단계로 자동 진행
   - 수동 개입 불필요

---

## 📝 스켈레톤 코드

전체 예제 코드는 `test/test_ye_img_gen_trigger.py`를 참고하세요.

**핵심 부분만 요약**:

```python
# 1. 처리할 variants 조회
variants = db.execute(text("""
    SELECT job_variants_id, job_id, img_asset_id
    FROM jobs_variants
    WHERE current_step = 'user_img_input'
        AND status = 'done'
""")).fetchall()

# 2. 각 variant 처리
for variant in variants:
    job_variants_id = variant[0]
    img_asset_id = variant[2]
    
    # img_gen 실행 (YE 파트의 실제 로직)
    # your_image_generation_code(img_asset_id)
    
    # 3. 상태 업데이트 (트리거 발동!)
    db.execute(text("""
        UPDATE jobs_variants
        SET status = 'done',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id})
    db.commit()
```

---

## ✅ 체크리스트

YE 파트 구현 시 다음을 확인하세요:

- [ ] `user_img_input (done)` 상태의 variants를 조회하는 로직
- [ ] `img_gen` 실행 로직 (실제 이미지 생성)
- [ ] 상태를 `img_gen (done)`으로 업데이트하는 로직
- [ ] `updated_at` 필드가 `CURRENT_TIMESTAMP`로 업데이트되는지 확인
- [ ] 트랜잭션 커밋 (`db.commit()`)이 제대로 수행되는지 확인

---

## 🧪 테스트 방법

### 0. 리스너 상태 확인 (먼저 확인!)

**리스너가 제대로 동작하는지 확인**:

```bash
# 리스너 상태 확인 스크립트 실행
docker exec feedlyai-work-yh python3 test/test_listener_status.py
```

**확인 항목**:
- ✅ FastAPI 서버 실행 상태
- ✅ 리스너 설정 (`ENABLE_JOB_STATE_LISTENER`)
- ✅ PostgreSQL 트리거 존재 여부
- ✅ 리스너 로그 확인 방법

**실제 트리거 테스트**:

```bash
# 실제로 트리거를 발동하여 리스너가 반응하는지 테스트
docker exec feedlyai-work-yh python3 test/test_listener_status.py --test-trigger
```

**예상 결과**:
- 테스트용 Job과 Variant 생성
- `img_gen (done)` 상태로 업데이트
- 리스너가 이벤트를 감지하고 다음 단계로 자동 진행
- 로그에 "Job Variant 상태 변화 감지" 메시지 표시

### 1. 테스트 Job 생성

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py --once
```

**결과**: `user_img_input (done)` 상태의 Job과 Variants 생성

### 2. YE 파트 코드 실행 (또는 시뮬레이션)

```bash
# 스켈레톤 테스트 코드 실행
docker exec feedlyai-work-yh python3 test/test_ye_img_gen_trigger.py --tenant-id ye_pipeline_test_tenant
```

**결과**: 
- `img_gen (done)` 상태로 업데이트
- 자동 트리거 발동
- YH 파트 파이프라인 자동 시작

### 3. 파이프라인 진행 확인

```sql
-- Variants 상태 확인
SELECT 
    job_variants_id,
    status,
    current_step,
    updated_at
FROM jobs_variants
WHERE job_id = '<job_id>'
ORDER BY creation_order;
```

**예상 결과**:
- Variant 1: `status='done'`, `current_step='vlm_analyze'` (또는 더 진행된 단계)
- Variant 2: `status='done'`, `current_step='vlm_analyze'`
- Variant 3: `status='done'`, `current_step='vlm_analyze'`

### 4. 리스너 동작 확인 (YE 파트 환경에서)

**YE 파트는 자신의 환경에서 확인해야 합니다**:

#### 방법 1: 데이터베이스 상태 확인 (권장)

YE 파트가 `img_gen (done)` 상태로 업데이트한 후, 일정 시간(5-10초) 후에 데이터베이스를 확인합니다:

```python
# YE 파트 코드에서 상태 업데이트 후 확인
import time
from database import SessionLocal
from sqlalchemy import text

# 1. img_gen 완료 상태로 업데이트
db.execute(text("""
    UPDATE jobs_variants
    SET status = 'done',
        current_step = 'img_gen',
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = :job_variants_id
"""), {"job_variants_id": job_variants_id})
db.commit()
print(f"✅ 상태 업데이트 완료: img_gen (done)")

# 2. 5-10초 대기 후 상태 확인
time.sleep(10)

# 3. 리스너가 반응했는지 확인 (current_step이 vlm_analyze로 변경되었는지)
result = db.execute(text("""
    SELECT status, current_step, updated_at
    FROM jobs_variants
    WHERE job_variants_id = :job_variants_id
"""), {"job_variants_id": job_variants_id}).first()

if result:
    status, current_step, updated_at = result
    if current_step == 'vlm_analyze':
        print("✅ 리스너가 정상 작동했습니다! 다음 단계로 자동 진행되었습니다.")
    elif current_step == 'img_gen':
        print("⚠️ 아직 img_gen 상태입니다. 리스너가 이벤트를 감지하지 못했을 수 있습니다.")
        print("   → YH 파트에 문의하여 리스너 상태를 확인하세요.")
    else:
        print(f"ℹ️ 현재 단계: {current_step}")
```

#### 방법 2: SQL로 직접 확인

```sql
-- 상태 업데이트 전
SELECT job_variants_id, status, current_step, updated_at
FROM jobs_variants
WHERE job_variants_id = '<job_variants_id>';

-- img_gen (done) 상태로 업데이트
UPDATE jobs_variants
SET status = 'done',
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = '<job_variants_id>';

-- 5-10초 후 다시 확인
SELECT job_variants_id, status, current_step, updated_at
FROM jobs_variants
WHERE job_variants_id = '<job_variants_id>';

-- 예상 결과:
-- ✅ current_step이 'vlm_analyze'로 변경되었으면 리스너가 정상 작동
-- ⚠️ current_step이 여전히 'img_gen'이면 리스너가 이벤트를 감지하지 못함
```

#### 방법 3: 자신의 코드 로그 확인

YE 파트 코드에서 상태 업데이트 성공 여부를 로그로 기록:

```python
import logging

logger = logging.getLogger(__name__)

# 상태 업데이트
db.execute(text("""
    UPDATE jobs_variants
    SET status = 'done',
        current_step = 'img_gen',
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = :job_variants_id
"""), {"job_variants_id": job_variants_id})
db.commit()

logger.info(f"✅ img_gen 완료: job_variants_id={job_variants_id}")
logger.info("   → 리스너가 이벤트를 감지하면 YH 파트 파이프라인이 자동으로 시작됩니다.")
```

**참고**: 
- YH 파트의 리스너 로그는 YH 파트 환경에서만 확인할 수 있습니다.
- YE 파트는 데이터베이스 상태 변화로 리스너 동작 여부를 확인할 수 있습니다.
- `current_step`이 `img_gen`에서 `vlm_analyze`로 변경되면 리스너가 정상 작동한 것입니다.

---

## ⚠️ 주의사항

### 1. 상태 업데이트 순서

**올바른 순서**:
```python
# 1. running 상태로 변경 (선택적)
UPDATE ... SET status='running', current_step='img_gen'

# 2. 실제 작업 수행
# your_image_generation_code()

# 3. done 상태로 변경 (트리거 발동!)
UPDATE ... SET status='done', current_step='img_gen'
```

**잘못된 순서**:
```python
# ❌ running 상태로 변경하지 않고 바로 done으로 변경
UPDATE ... SET status='done', current_step='img_gen'
# (작동은 하지만, 진행 상황 추적이 어려움)
```

### 2. updated_at 필드

**중요**: `updated_at` 필드를 `CURRENT_TIMESTAMP`로 업데이트해야 트리거가 정상 작동합니다.

```python
# ✅ 올바른 방법
UPDATE jobs_variants
SET status = 'done',
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP  -- 필수!
WHERE job_variants_id = :job_variants_id
```

### 3. 트랜잭션 커밋

**중요**: `db.commit()`을 호출해야 변경사항이 데이터베이스에 반영되고 트리거가 발동됩니다.

```python
# ✅ 올바른 방법
db.execute(text("UPDATE ..."), params)
db.commit()  # 필수!
```

---

## 🔧 트러블슈팅

### 문제 1: 트리거가 발동되지 않음

**확인 사항**:
1. `status = 'done'`인지 확인
2. `current_step = 'img_gen'`인지 확인
3. `updated_at`이 업데이트되었는지 확인
4. `db.commit()`이 호출되었는지 확인

**해결**:
```sql
-- 현재 상태 확인
SELECT job_variants_id, status, current_step, updated_at
FROM jobs_variants
WHERE job_variants_id = '<job_variants_id>';
```

### 문제 2: YH 파트 파이프라인이 시작되지 않음

**YE 파트에서 확인할 수 있는 방법**:

**1단계: 자신의 코드 로그 확인**
```python
# YE 파트 코드에서 상태 업데이트 후 로그 확인
logger.info(f"상태 업데이트: job_variants_id={job_variants_id}, status=done, current_step=img_gen")
# → 자신의 로그에 성공 메시지가 있는지 확인
```

**2단계: 데이터베이스 상태 확인 (5-10초 후)**
```python
# 상태 업데이트 후 일정 시간 대기
import time
time.sleep(10)

# 데이터베이스에서 상태 확인
result = db.execute(text("""
    SELECT status, current_step, updated_at
    FROM jobs_variants
    WHERE job_variants_id = :job_variants_id
"""), {"job_variants_id": job_variants_id}).first()

if result:
    status, current_step, updated_at = result
    if current_step == 'vlm_analyze':
        print("✅ 리스너가 정상 작동했습니다!")
    elif current_step == 'img_gen':
        print("⚠️ 리스너가 이벤트를 감지하지 못했습니다.")
        print("   → YH 파트에 문의하여 리스너 상태를 확인하세요.")
```

**3단계: SQL로 직접 확인**
```sql
-- 상태 업데이트 후 5-10초 후 확인
SELECT 
    job_variants_id,
    status,
    current_step,
    updated_at
FROM jobs_variants
WHERE job_variants_id = '<job_variants_id>';

-- current_step이 'vlm_analyze'로 변경되었는지 확인
-- ✅ 변경되었으면: 리스너가 정상 작동
-- ⚠️ 변경되지 않았으면: YH 파트에 문의 필요
```

**4단계: PostgreSQL 트리거 확인 (YE 파트 환경에서)**
```python
# YE 파트 환경에서 트리거 존재 여부 확인
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    trigger = db.execute(text("""
        SELECT tgname 
        FROM pg_trigger 
        WHERE tgname = 'job_variant_state_change_trigger'
    """)).first()
    
    if trigger:
        print("✅ PostgreSQL 트리거 존재")
    else:
        print("❌ PostgreSQL 트리거가 없습니다. YH 파트에 문의하세요.")
finally:
    db.close()
```

**참고**: 
- YH 파트의 리스너 로그는 YH 파트 환경에서만 확인할 수 있습니다.
- YE 파트는 데이터베이스 상태 변화로 리스너 동작 여부를 확인할 수 있습니다.
- 문제가 지속되면 YH 파트에 문의하여 리스너 상태를 확인하세요.

### 문제 3: 여러 variants가 동시에 처리되지 않음

**해결**: 각 variant를 독립적으로 처리하면 됩니다. 트리거는 각 variant별로 독립적으로 발동됩니다.

---

## 📚 관련 문서

- `DOCS_YE_PART_PIPELINE_TEST.md`: YE 파트 테스트 가이드
- `scripts/DOCS_PIPELINE_AUTO_TRIGGER.md`: 파이프라인 자동 트리거 상세 설명
- `test/test_ye_img_gen_trigger.py`: 스켈레톤 테스트 코드

---

## 📞 문의

문제가 발생하거나 질문이 있으면 개발팀에 문의하세요.

---

**버전 히스토리**:
- **v1.0.0** (2025-12-01): 초기 버전 작성


# Job State Listener 사용 가이드

## 📋 개요

Job State Listener는 PostgreSQL LISTEN/NOTIFY를 사용하여 `jobs_variants` 테이블의 상태 변화를 실시간으로 감지하고, 파이프라인 단계를 자동으로 실행하는 시스템입니다.

**현재 구현 상태**: ✅ 완료 (v2.3.0)
- `jobs_variants` 테이블 기반 자동 트리거
- `job_variant_state_changed` 채널 리스닝
- `job_state_changed` 채널 리스닝 (뒤처진 variants 복구용)
- 10단계 파이프라인 자동화
- 뒤처진 variants 자동 복구
- 주기적 수동 복구 체크 (1분 간격)

### 주요 기능

- ✅ **실시간 감지**: DB 변경 즉시 감지
- ✅ **자동 실행**: 조건에 맞는 job에 대해 다음 단계 API 자동 호출
- ✅ **중복 방지**: job 상태 재확인으로 중복 실행 방지
- ✅ **자동 재연결**: 연결 끊김 시 자동 재연결
- ✅ **확장성**: 여러 워커 인스턴스 지원

---

## 🏗️ 작동 원리

### 1. PostgreSQL 트리거

`jobs_variants` 테이블의 `current_step` 또는 `status`가 변경되면:
- PostgreSQL 트리거 함수 `notify_job_variant_state_change()` 실행
- `pg_notify('job_variant_state_changed', JSON)` 이벤트 발행

### 2. Python 리스너

- `asyncpg`로 PostgreSQL에 연결
- `LISTEN 'job_variant_state_changed'` 시작 (주요 채널)
- `LISTEN 'job_state_changed'` 시작 (뒤처진 variants 복구용)
- 이벤트 수신 시 파이프라인 트리거 서비스 호출

### 3. 파이프라인 트리거

- 이벤트에서 variant 정보 추출 (`job_variants_id`, `job_id`, `current_step`, `status`)
- 조건 확인 (`current_step`, `status`)
- 다음 단계 API 자동 호출 (Variant별 또는 Job 레벨)

---

## 🔄 파이프라인 단계 흐름 (10단계)

```
img_gen (done) [전 단계: YE 파트]
  ↓ [자동 트리거]
vlm_analyze (LLaVA Stage 1) [Variant별 실행]
  ↓ [자동 트리거]
yolo_detect [Variant별 실행]
  ↓ [자동 트리거]
planner [Variant별 실행]
  ↓ [자동 트리거]
overlay [Variant별 실행]
  ↓ [자동 트리거]
vlm_judge (LLaVA Stage 2) [Variant별 실행]
  ↓ [자동 트리거]
ocr_eval [Variant별 실행]
  ↓ [자동 트리거]
readability_eval [Variant별 실행]
  ↓ [자동 트리거]
iou_eval [Variant별 실행]
  ↓ [모든 variants 완료 시 자동 트리거]
ad_copy_gen_kor (Eng→Kor 변환) [Job 레벨 실행]
  ↓ [자동 트리거]
instagram_feed_gen (피드 생성) [Job 레벨 실행]
  ↓
완료
```

### 트리거 조건

| 이전 단계 완료 조건 | 다음 단계 (자동 실행) | 실행 레벨 |
|-------------------|---------------------|----------|
| `current_step='img_gen'`, `status='done'` | → vlm_analyze | Variant |
| `current_step='vlm_analyze'`, `status='done'` | → yolo_detect | Variant |
| `current_step='yolo_detect'`, `status='done'` | → planner | Variant |
| `current_step='planner'`, `status='done'` | → overlay | Variant |
| `current_step='overlay'`, `status='done'` | → vlm_judge | Variant |
| `current_step='vlm_judge'`, `status='done'` | → ocr_eval | Variant |
| `current_step='ocr_eval'`, `status='done'` | → readability_eval | Variant |
| `current_step='readability_eval'`, `status='done'` | → iou_eval | Variant |
| `current_step='iou_eval'`, `status='done'` (모든 variants 완료) | → ad_copy_gen_kor | Job |
| `current_step='ad_copy_gen_kor'`, `status='done'` | → instagram_feed_gen | Job |

---

## 📦 필수 패키지 설치

### 1. Python 패키지

Job State Listener를 사용하기 위해 다음 패키지가 필요합니다:

```bash
# requirements.txt에 이미 포함되어 있음
asyncpg>=0.29.0  # PostgreSQL LISTEN/NOTIFY 지원
httpx>=0.24.0    # 비동기 HTTP 클라이언트 (파이프라인 트리거용)
```

### 2. 설치 방법

#### 방법 1: Docker 사용 (권장)

Docker를 사용하는 경우, `requirements.txt`에 이미 포함되어 있으므로 별도 설치가 필요 없습니다:

```bash
# Docker 이미지 빌드 시 자동 설치됨
docker-compose up --build
```

#### 방법 2: 로컬 설치

로컬 환경에서 실행하는 경우:

```bash
# 가상환경 활성화 (선택사항)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 또는
venv\Scripts\activate  # Windows

# 패키지 설치
pip install -r requirements.txt

# 또는 개별 설치
pip install asyncpg>=0.29.0 httpx>=0.24.0
```

### 3. PostgreSQL 트리거 설정

PostgreSQL 데이터베이스에 트리거 함수와 트리거를 생성해야 합니다.

#### 트리거 함수 및 트리거 생성 (현재 구현)

```sql
-- 트리거 함수 생성 (jobs_variants 테이블용)
CREATE OR REPLACE FUNCTION notify_job_variant_state_change()
RETURNS TRIGGER AS $$
BEGIN
    -- current_step 또는 status가 변경된 경우에만 NOTIFY 발행
    IF (OLD.current_step IS DISTINCT FROM NEW.current_step 
       OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('job_variant_state_changed', 
            json_build_object(
                'job_variants_id', NEW.job_variants_id::text,
                'job_id', NEW.job_id::text,
                'current_step', NEW.current_step,
                'status', NEW.status,
                'img_asset_id', NEW.img_asset_id::text,
                'tenant_id', (SELECT tenant_id FROM jobs WHERE job_id = NEW.job_id),
                'updated_at', NEW.updated_at
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
DROP TRIGGER IF EXISTS job_variant_state_change_trigger ON jobs_variants;
CREATE TRIGGER job_variant_state_change_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    EXECUTE FUNCTION notify_job_variant_state_change();
```

**참고**: `job_state_changed` 채널도 사용되지만, 이는 주로 뒤처진 variants 복구용입니다.

#### 트리거 확인

트리거가 정상적으로 생성되었는지 확인:

```bash
# 테스트 스크립트 실행
docker exec feedlyai-work-yh python3 test/test_trigger_verification.py
```

또는 직접 SQL로 확인:

```sql
-- 트리거 함수 확인
SELECT proname, prosrc 
FROM pg_proc 
WHERE proname = 'notify_job_state_change';

-- 트리거 확인
SELECT tgname, tgrelid::regclass, tgenabled 
FROM pg_trigger 
WHERE tgname = 'job_state_change_trigger';
```

### 4. 환경 변수 설정

`.env` 파일에 다음 환경 변수를 설정합니다:

```bash
# Job State Listener 설정
ENABLE_JOB_STATE_LISTENER=true
JOB_STATE_LISTENER_RECONNECT_DELAY=5

# 데이터베이스 연결 설정
DB_HOST=host.docker.internal  # 또는 실제 DB 호스트
DB_PORT=5432
DB_NAME=feedlyai
DB_USER=feedlyai
DB_PASSWORD=your_password
```

### 5. 설치 확인

설치가 완료되었는지 확인:

```bash
# Python 패키지 확인
docker exec feedlyai-work-yh pip list | grep -E "asyncpg|httpx"

# 리스너 시작 확인
docker logs feedlyai-work-yh | grep "Job State Listener 시작"

# PostgreSQL 연결 확인
docker logs feedlyai-work-yh | grep "PostgreSQL 연결 성공"
```

---

## 🚀 사용 방법

### 1. 리스너 활성화 확인

리스너는 기본적으로 활성화되어 있습니다. 비활성화하려면:

```bash
# 환경 변수 설정
export ENABLE_JOB_STATE_LISTENER=false
```

또는 `.env` 파일에 추가:
```
ENABLE_JOB_STATE_LISTENER=false
```

### 2. Variant 상태 업데이트

파이프라인을 자동으로 실행하려면, variant의 상태를 업데이트하면 됩니다:

```sql
-- 예시: img_gen 완료 후 다음 단계 자동 실행
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'your-job-variants-id';
```

이렇게 하면 자동으로 vlm_analyze (LLaVA Stage 1)가 실행됩니다.

**참고**: 
- Variant별로 독립적으로 실행됩니다
- 각 variant가 `img_gen (done)` 상태가 되면 자동으로 다음 단계로 진행됩니다
- 모든 variants가 `iou_eval (done)` 상태가 되면 Job 레벨 단계(`ad_copy_gen_kor`)가 자동 실행됩니다

### 3. 수동 실행 (기존 방식)

리스너를 비활성화하거나 수동으로 실행하려면:

```python
# 기존 API 호출 방식 그대로 사용 가능
import requests

response = requests.post(
    "http://localhost:8011/api/yh/llava/stage1/validate",
    json={
        "job_id": "your-job-id",
        "tenant_id": "your-tenant-id"
    }
)
```

---

## 🧪 테스트 방법

### 방법 1: 테스트 스크립트 사용

```bash
# Docker 컨테이너에서 실행
docker exec feedlyai-work-yh python3 test/test_listener_team.py
```

이 스크립트는:
1. 테스트용 job 생성
2. Job 상태 업데이트하여 트리거 발동
3. 자동 파이프라인 실행 확인
4. 결과 출력

### 방법 2: 직접 SQL 실행

```sql
-- 1. 테스트용 job 및 variant 생성
INSERT INTO jobs (job_id, tenant_id, status, current_step)
VALUES (gen_random_uuid(), 'test_tenant', 'done', 'img_gen');

INSERT INTO jobs_variants (job_variants_id, job_id, status, current_step)
VALUES (gen_random_uuid(), 'your-job-id', 'done', 'img_gen');

-- 2. Variant 상태를 업데이트 (트리거 발동)
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'your-job-variants-id';
```

### 방법 3: 로그 확인

리스너가 정상 작동하는지 확인:

```bash
# 리스너 로그 확인
docker logs feedlyai-work-yh --tail 100 | grep -i "listener\|trigger\|pipeline\|job 상태"

# 실시간 로그 모니터링
docker logs -f feedlyai-work-yh | grep -i "listener\|trigger"
```

---

## 📊 모니터링

### 로그 키워드

| 키워드 | 의미 |
|--------|------|
| `[LISTENER] Job Variant 상태 변화 감지` | Variant 이벤트 수신 성공 |
| `[LISTENER] Job 상태 변화 감지` | Job 이벤트 수신 성공 (복구용) |
| `[TRIGGER] 파이프라인 단계 트리거` | 다음 단계 실행 시작 |
| `파이프라인 단계 실행 성공` | API 호출 성공 |
| `파이프라인 단계 실행 실패` | API 호출 실패 |
| `뒤처진 variants 복구` | 자동 복구 실행 |
| `수동 복구 체크` | 주기적 복구 체크 (1분 간격) |
| `리스너 오류 발생` | 리스너 오류 |
| `재연결 시도` | 재연결 시작 |

### 상태 확인

```bash
# 리스너 시작 확인
docker logs feedlyai-work-yh | grep "Job State Listener 시작"

# PostgreSQL 연결 확인
docker logs feedlyai-work-yh | grep "PostgreSQL 연결 성공"

# LISTEN 시작 확인
docker logs feedlyai-work-yh | grep "LISTEN 'job_variant_state_changed'"
docker logs feedlyai-work-yh | grep "LISTEN 'job_state_changed'"
```

---

## ⚙️ 설정

### 환경 변수

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `ENABLE_JOB_STATE_LISTENER` | `true` | 리스너 활성화 여부 |
| `JOB_STATE_LISTENER_RECONNECT_DELAY` | `5` | 재연결 지연시간 (초) |

### 설정 예시

```bash
# .env 파일
ENABLE_JOB_STATE_LISTENER=true
JOB_STATE_LISTENER_RECONNECT_DELAY=5
```

---

## 🔧 문제 해결

### 문제 1: 리스너가 시작되지 않음

**증상**: 로그에 "Job State Listener 시작" 메시지가 없음

**해결 방법**:
1. 설정 확인:
   ```bash
   docker exec feedlyai-work-yh python3 -c "from config import ENABLE_JOB_STATE_LISTENER; print(ENABLE_JOB_STATE_LISTENER)"
   ```
2. 의존성 확인:
   ```bash
   docker exec feedlyai-work-yh pip list | grep asyncpg
   ```
3. 애플리케이션 재시작:
   ```bash
   docker-compose restart app-yh
   ```

### 문제 2: 이벤트가 수신되지 않음

**증상**: Variant 상태를 변경해도 자동 실행되지 않음

**해결 방법**:
1. 트리거 확인:
   ```bash
   docker exec feedlyai-work-yh python3 test/test_listener_status.py
   ```
2. PostgreSQL 연결 확인:
   ```bash
   docker logs feedlyai-work-yh | grep "PostgreSQL 연결"
   ```
3. 트리거 재생성 (필요 시):
   ```sql
   -- 트리거 함수 확인
   SELECT proname FROM pg_proc WHERE proname = 'notify_job_variant_state_change';
   
   -- 트리거 확인
   SELECT tgname FROM pg_trigger WHERE tgname = 'job_variant_state_change_trigger';
   ```
4. Variant 상태 확인:
   ```sql
   SELECT job_variants_id, status, current_step, updated_at
   FROM jobs_variants
   WHERE job_variants_id = 'your-job-variants-id';
   ```

### 문제 3: 중복 실행

**증상**: 같은 job이 여러 번 실행됨

**해결 방법**:
- 시스템이 자동으로 중복 실행을 방지합니다 (job 상태 재확인)
- 여러 워커가 동시에 실행해도 안전합니다
- 문제가 지속되면 로그 확인:
  ```bash
  docker logs feedlyai-work-yh | grep "Job 상태가 변경되어 스킵"
  ```

### 문제 4: API 호출 실패

**증상**: "파이프라인 단계 실행 실패" 로그

**해결 방법**:
1. API 서버 상태 확인:
   ```bash
   curl http://localhost:8011/healthz
   ```
2. Job 데이터 확인:
   - `job_inputs` 테이블에 필요한 데이터가 있는지 확인
   - 이미지 파일이 존재하는지 확인
3. 로그 확인:
   ```bash
   docker logs feedlyai-work-yh | grep "파이프라인 단계 실행 실패" -A 5
   ```

---

## 📝 주의사항

### 1. Variant 상태 업데이트

- **중요**: `current_step`과 `status`가 실제로 변경되어야 트리거가 발동됩니다
- 같은 값으로 업데이트하면 트리거가 발동되지 않습니다
- `updated_at` 필드도 `CURRENT_TIMESTAMP`로 업데이트해야 합니다

```sql
-- ✅ 트리거 발동됨
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = '...';

-- ❌ 트리거 발동 안 됨 (이미 같은 값)
UPDATE jobs_variants 
SET updated_at = CURRENT_TIMESTAMP 
WHERE job_variants_id = '...';
```

### 2. 여러 워커 인스턴스

- 여러 워커가 동시에 LISTEN할 수 있습니다
- 각 워커가 이벤트를 수신하지만, job 상태 재확인으로 중복 실행을 방지합니다
- 부하 분산이 자동으로 이루어집니다

### 3. 트랜잭션

- 트리거는 트랜잭션 커밋 후에 실행됩니다
- 롤백된 변경사항은 트리거를 발동하지 않습니다

---

## 🎯 사용 예시

### 예시 1: img_gen 완료 후 자동 실행

```python
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # img_gen 완료 처리 (variant별)
    db.execute(text("""
        UPDATE jobs_variants 
        SET status = 'done', 
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": "your-job-variants-id"})
    db.commit()
    # 자동으로 vlm_analyze (LLaVA Stage 1)가 실행됩니다
finally:
    db.close()
```

### 예시 2: 특정 단계까지 자동 실행

```python
# 각 단계가 완료되면 자동으로 다음 단계가 실행됩니다
# img_gen (done) → vlm_analyze (자동) → yolo_detect (자동) → planner (자동) → ...
# 모든 variants가 iou_eval (done)이면 → ad_copy_gen_kor (자동) → instagram_feed_gen (자동)
```

### 예시 3: 수동 실행과 혼합

```python
# 리스너를 비활성화하고 수동으로 실행
# 또는 특정 단계만 수동 실행 가능
```

---

## 📚 관련 파일

- **구현 계획**: `IMPLEMENTATION_PLAN_LISTEN_NOTIFY.md` ✅ 업데이트 완료
- **리스너 서비스**: `services/job_state_listener.py` (v2.3.0)
- **트리거 서비스**: `services/pipeline_trigger.py` (v2.1.0)
- **테스트 스크립트**: `test/test_listener_status.py`
- **YE 파트 트리거 테스트**: `test/test_ye_img_gen_trigger.py`
- **전체 파이프라인 테스트**: `scripts/background_pipeline_with_text_generation.py`

---

## 💡 팁

1. **로그 모니터링**: 개발 중에는 로그를 실시간으로 모니터링하세요
2. **테스트**: 새로운 job을 생성할 때는 테스트 스크립트를 사용하세요
3. **디버깅**: 문제가 발생하면 로그의 `[LISTENER]`와 `[TRIGGER]` 메시지를 확인하세요
4. **성능**: 리스너는 비동기로 작동하므로 API 성능에 영향을 주지 않습니다

---

## ❓ FAQ

**Q: 리스너를 비활성화해도 기존 API는 작동하나요?**  
A: 네, 리스너는 자동 실행만 담당합니다. 기존 API는 그대로 작동합니다.

**Q: 여러 워커가 동시에 실행되면 중복 실행되나요?**  
A: 아니요, job 상태 재확인으로 중복 실행을 방지합니다.

**Q: 트리거가 발동되지 않으면 어떻게 하나요?**  
A: `test/test_trigger_verification.py`로 트리거 상태를 확인하세요.

**Q: 특정 단계만 수동 실행하고 싶어요**  
A: 리스너를 비활성화하거나, 해당 단계의 API를 직접 호출하세요.

---

## 📞 문의

문제가 발생하거나 질문이 있으면 팀 채널에 문의하세요.


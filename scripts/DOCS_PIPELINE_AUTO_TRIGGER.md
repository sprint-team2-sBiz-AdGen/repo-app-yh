# 파이프라인 자동 트리거 동작 원리

## 📋 개요

Job Variants 기반 파이프라인은 **PostgreSQL LISTEN/NOTIFY**와 **FastAPI 리스너**를 통해 완전 자동화되어 있습니다. 별도의 백그라운드 스크립트 없이도 데이터베이스 상태 변화를 감지하여 자동으로 다음 단계를 실행합니다.

---

## 🔄 전체 동작 흐름

```
1. Job 생성 (background_job_creator.py)
   ↓
2. Variants 상태 업데이트 (trigger_job_variants)
   ↓
3. PostgreSQL 트리거 발동 (NOTIFY)
   ↓
4. FastAPI 리스너 감지 (job_state_listener.py)
   ↓
5. 파이프라인 트리거 (pipeline_trigger.py)
   ↓
6. API 엔드포인트 호출 (자동)
   ↓
7. 다음 단계 상태 업데이트
   ↓
8. (3번부터 반복)
```

---

## 📝 상세 동작 원리

### 1단계: Job 및 Variants 생성

**스크립트**: `scripts/background_job_creator.py`

```python
# Job 생성
job_id = uuid.uuid4()
INSERT INTO jobs (job_id, tenant_id, status, current_step)
VALUES (job_id, tenant_id, 'running', 'vlm_analyze')

# Variants 생성 (3개)
FOR each variant:
    INSERT INTO jobs_variants (
        job_variants_id, job_id, img_asset_id, 
        status, current_step
    )
    VALUES (variant_id, job_id, img_asset_id, 'done', 'img_gen')
```

**결과**: 
- `jobs` 테이블에 1개 레코드 생성
- `jobs_variants` 테이블에 3개 레코드 생성
- 모든 variants는 `img_gen` 단계에서 `done` 상태

---

### 2단계: 트리거 발동

**함수**: `trigger_job_variants()` in `background_job_creator.py`

```python
def trigger_job_variants(job_id: str, job_variants: list):
    for variant in job_variants:
        # 1. running으로 변경
        UPDATE jobs_variants 
        SET status = 'running', current_step = 'img_gen'
        WHERE job_variants_id = variant_id
        
        # 2. done으로 변경 (트리거 발동)
        UPDATE jobs_variants 
        SET status = 'done', current_step = 'img_gen'
        WHERE job_variants_id = variant_id
```

**동작**:
- 각 variant의 상태를 `running` → `done`으로 변경
- `updated_at`이 업데이트되어 PostgreSQL 트리거가 발동

---

### 3단계: jobs_variants 업데이트 → 트리거 자동 실행 (DB 내부)

**파일**: `db/init/03_job_variants_state_notify_trigger.sql`

#### 3-1. UPDATE 문 실행

```python
# 예시: API 엔드포인트에서 상태 업데이트
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'vlm_analyze',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'xxx-xxx-xxx'
```

**PostgreSQL 내부 동작**:
1. `UPDATE` 문이 실행되면 PostgreSQL은 **트랜잭션 내에서** 다음을 수행:
   - `OLD` 레코드: 업데이트 전 값 (`OLD.status`, `OLD.current_step`)
   - `NEW` 레코드: 업데이트 후 값 (`NEW.status`, `NEW.current_step`)
   - 두 값을 비교하여 변경 여부 확인

#### 3-2. 트리거 자동 실행

**트리거 정의**:
```sql
CREATE TRIGGER job_variant_state_change_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    EXECUTE FUNCTION notify_job_variant_state_change();
```

**트리거 실행 시점**:
- `AFTER UPDATE`: UPDATE 문이 **성공적으로 완료된 후** 실행
- `FOR EACH ROW`: 업데이트된 **각 행마다** 실행 (3개 variant 업데이트 시 3번 실행)
- **트랜잭션 내부**: 트리거는 UPDATE와 같은 트랜잭션 내에서 실행됨

**트리거 함수 내부 로직**:
```sql
CREATE OR REPLACE FUNCTION notify_job_variant_state_change()
RETURNS TRIGGER AS $$
BEGIN
    -- 1. 변경 감지: status 또는 current_step이 실제로 변경되었는지 확인
    IF (OLD.current_step IS DISTINCT FROM NEW.current_step 
        OR OLD.status IS DISTINCT FROM NEW.status) THEN
        
        -- 2. jobs 테이블에서 tenant_id 조회 (NOTIFY 페이로드에 포함)
        -- 3. JSON 객체 생성
        -- 4. pg_notify() 함수 호출로 NOTIFY 이벤트 발행
        PERFORM pg_notify(
            'job_variant_state_changed',  -- 채널 이름
            json_build_object(
                'job_variants_id', NEW.job_variants_id::text,
                'job_id', NEW.job_id::text,
                'current_step', NEW.current_step,
                'status', NEW.status,
                'img_asset_id', NEW.img_asset_id::text,
                'tenant_id', (SELECT tenant_id FROM jobs WHERE job_id = NEW.job_id),
                'updated_at', NEW.updated_at
            )::text  -- JSON을 텍스트로 변환
        );
    END IF;
    
    RETURN NEW;  -- 업데이트된 레코드 반환
END;
$$ LANGUAGE plpgsql;
```

**중요 포인트**:
- ✅ **트랜잭션 원자성**: 트리거는 UPDATE와 같은 트랜잭션 내에서 실행되므로, UPDATE가 롤백되면 트리거도 롤백됨
- ✅ **변경 감지**: `IS DISTINCT FROM` 연산자로 NULL 값도 올바르게 처리
- ✅ **성능**: 조건문으로 불필요한 NOTIFY 방지 (실제 변경이 있을 때만 발행)

#### 3-3. 추가 트리거: jobs 테이블 자동 업데이트

**트리거 함수**: `check_all_variants_done()`

```sql
CREATE TRIGGER check_all_variants_done_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    WHEN (NEW.status = 'done' OR NEW.status = 'failed')
    EXECUTE FUNCTION check_all_variants_done();
```

**동작**:
- Variant의 `status`가 `done` 또는 `failed`로 변경될 때만 실행
- 모든 variants의 상태를 집계하여 `jobs` 테이블 자동 업데이트
- 예: 모든 variants가 `iou_eval`, `done`이면 `jobs.status = 'done'`으로 업데이트

---

### 4단계: NOTIFY 이벤트 발행

**PostgreSQL 내부 동작**:

#### 4-1. pg_notify() 함수 실행

```sql
PERFORM pg_notify('job_variant_state_changed', '{"job_variants_id":"...", ...}')
```

**PostgreSQL 내부 처리**:
1. **채널 등록**: `job_variant_state_changed` 채널에 이벤트 등록
2. **메시지 큐**: PostgreSQL의 내부 메시지 큐에 이벤트 저장
3. **리스너 알림**: 해당 채널을 `LISTEN` 중인 모든 연결에 즉시 알림
4. **비동기 전송**: 리스너가 있으면 즉시 전송, 없으면 큐에 저장 (리스너 연결 시 전달)

#### 4-2. NOTIFY 이벤트 페이로드

**JSON 형식**:
```json
{
  "job_variants_id": "1b859601-d08b-4755-b371-f88c2c962f52",
  "job_id": "a709a3ad-9287-4ceb-abbf-10a86dafd8b9",
  "current_step": "vlm_analyze",
  "status": "done",
  "img_asset_id": "xxx-xxx-xxx",
  "tenant_id": "test_sequential",
  "updated_at": "2025-11-29T00:44:39.403639+09:00"
}
```

**특징**:
- ✅ **텍스트 형식**: JSON을 텍스트로 변환하여 전송 (최대 8000 바이트)
- ✅ **트랜잭션 커밋 시 전송**: 트랜잭션이 커밋되어야 리스너에 전달됨
- ✅ **순서 보장**: 같은 트랜잭션 내에서 발행된 NOTIFY는 순서대로 전달됨

---

### 5단계: FastAPI 리스너가 실시간 감지

**파일**: `services/job_state_listener.py`

#### 5-1. 리스너 초기화 및 연결

**리스너 시작** (`main.py`의 `lifespan` 함수):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if ENABLE_JOB_STATE_LISTENER:
        from services.job_state_listener import start_listener
        await start_listener()  # 리스너 시작
    yield
    # Shutdown 시 stop_listener()
```

**리스너 연결** (`_connect_and_listen()`):
```python
async def _connect_and_listen(self):
    # 1. PostgreSQL 연결 (asyncpg 사용)
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    self.conn = await asyncpg.connect(asyncpg_url)
    
    # 2. LISTEN 시작 (채널 구독)
    await self.conn.add_listener(
        'job_variant_state_changed', 
        self._handle_variant_notification
    )
    
    # 3. 무한 루프로 대기 (연결 유지)
    while self.running:
        await asyncio.sleep(1)
```

**연결 특징**:
- ✅ **영구 연결**: FastAPI 서버가 실행되는 동안 계속 유지
- ✅ **비동기 I/O**: `asyncpg`를 사용하여 논블로킹 방식으로 동작
- ✅ **자동 재연결**: 연결이 끊기면 자동으로 재연결 시도

#### 5-2. NOTIFY 이벤트 수신

**이벤트 핸들러** (`_handle_variant_notification()`):
```python
def _handle_variant_notification(self, conn, pid, channel, payload):
    """NOTIFY 이벤트 핸들러 (동기 함수)"""
    try:
        # 1. JSON 페이로드 파싱
        data = json.loads(payload)
        
        # 2. 데이터 추출
        job_variants_id = data.get('job_variants_id')
        job_id = data.get('job_id')
        current_step = data.get('current_step')
        status = data.get('status')
        tenant_id = data.get('tenant_id')
        img_asset_id = data.get('img_asset_id')
        
        # 3. 로깅
        logger.info(
            f"Job Variant 상태 변화 감지: "
            f"job_variants_id={job_variants_id}, "
            f"job_id={job_id}, "
            f"current_step={current_step}, "
            f"status={status}"
        )
        
        # 4. 비동기 태스크로 처리 (이벤트 핸들러는 동기 함수이므로)
        task = asyncio.create_task(
            self._process_job_variant_state_change(
                job_variants_id=job_variants_id,
                job_id=job_id,
                current_step=current_step,
                status=status,
                tenant_id=tenant_id,
                img_asset_id=img_asset_id
            )
        )
        # 태스크 추적 (종료 시 완료 대기)
        self.pending_tasks.add(task)
        task.add_done_callback(self.pending_tasks.discard)
        
    except Exception as e:
        logger.error(f"이벤트 처리 오류: {e}", exc_info=True)
```

**이벤트 수신 특징**:
- ✅ **실시간**: PostgreSQL이 NOTIFY를 발행하면 **즉시** 수신 (폴링 지연 없음)
- ✅ **비동기 처리**: 이벤트 핸들러는 동기 함수이지만, 실제 처리는 비동기 태스크로 실행
- ✅ **병렬 처리**: 여러 NOTIFY 이벤트가 동시에 발생해도 각각 독립적으로 처리

#### 5-3. 상태 변화 처리

**처리 함수** (`_process_job_variant_state_change()`):
```python
async def _process_job_variant_state_change(
    self,
    job_variants_id: str,
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str,
    img_asset_id: str
):
    """Job Variant 상태 변화 처리 및 다음 단계 트리거"""
    try:
        from services.pipeline_trigger import trigger_next_pipeline_stage_for_variant
        
        # 파이프라인 트리거 호출
        await trigger_next_pipeline_stage_for_variant(
            job_variants_id=job_variants_id,
            job_id=job_id,
            current_step=current_step,
            status=status,
            tenant_id=tenant_id,
            img_asset_id=img_asset_id
        )
    except Exception as e:
        logger.error(
            f"파이프라인 트리거 오류: job_variants_id={job_variants_id}, error={e}",
            exc_info=True
        )
```

---

### 6단계: 파이프라인 트리거

**파일**: `services/pipeline_trigger.py`

#### 6-1. 다음 단계 결정

**함수**: `trigger_next_pipeline_stage_for_variant()`

```python
async def trigger_next_pipeline_stage_for_variant(
    job_variants_id: str,
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str,
    img_asset_id: str
):
    # 1. 파이프라인 단계 매핑에서 다음 단계 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    
    if not stage_info:
        logger.warning(f"다음 단계를 찾을 수 없음: {current_step}, {status}")
        return
    
    next_step = stage_info['next_step']
    api_endpoint = stage_info['api_endpoint']
    method = stage_info['method']
```

**파이프라인 단계 매핑**:
```python
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
        'method': 'POST',
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST',
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'method': 'POST',
    },
    # ... (계속)
}
```

#### 6-2. 필요한 데이터 조회

**overlay_id 조회** (필요한 경우):
```python
if stage_info.get('needs_overlay_id'):
    overlay_id = await _get_overlay_id_from_job_variant(job_variants_id)
    if not overlay_id:
        logger.warning(f"overlay_id를 찾을 수 없어 {next_step} 트리거를 건너뜁니다")
        return
```

**텍스트 및 proposal_id 조회** (필요한 경우):
```python
if stage_info.get('needs_text_and_proposal'):
    text, proposal_id = await _get_text_and_proposal_from_job_variant(job_variants_id)
```

#### 6-3. API 엔드포인트 호출

**HTTP 요청**:
```python
# 3. API 호출
try:
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            f"http://localhost:8000{api_endpoint}",
            json={
                "job_variants_id": job_variants_id,
                "overlay_id": overlay_id if stage_info.get('needs_overlay_id') else None,
                "text": text if stage_info.get('needs_text_and_proposal') else None,
                "proposal_id": proposal_id if stage_info.get('needs_text_and_proposal') else None,
                # ... (기타 필수 파라미터)
            }
        )
        response.raise_for_status()
        logger.info(
            f"[TRIGGER] 파이프라인 단계 트리거 (variant): "
            f"job_variants_id={job_variants_id}, next_step={next_step}"
        )
except httpx.HTTPError as e:
    logger.error(
        f"파이프라인 단계 실행 실패 (variant): "
        f"job_variants_id={job_variants_id}, next_step={next_step}, error={e}"
    )
    # 실패 시 variant 상태를 'failed'로 업데이트
    await _update_variant_status(job_variants_id, 'failed')
```

**API 호출 특징**:
- ✅ **비동기**: `httpx.AsyncClient`를 사용하여 논블로킹 방식
- ✅ **타임아웃**: 300초 타임아웃 설정 (LLaVA 모델 로딩 시간 고려)
- ✅ **에러 처리**: 실패 시 variant 상태를 `failed`로 업데이트

#### 6-4. 순환 구조 완성

**다음 단계 실행 후**:
1. API 엔드포인트가 실행 완료
2. `jobs_variants` 테이블 업데이트 (`status = 'done'`, `current_step = next_step`)
3. **다시 3단계로 돌아가서** 트리거가 자동 발동
4. 다음 단계로 자동 진행

**전체 흐름**:
```
jobs_variants 업데이트 
  ↓
트리거 자동 실행 (DB 내부)
  ↓
NOTIFY 이벤트 발행
  ↓
FastAPI 리스너가 실시간 감지
  ↓
파이프라인 트리거
  ↓
API 엔드포인트 호출
  ↓
jobs_variants 업데이트 (다시 처음으로)
```

---

### 4단계: FastAPI 리스너 감지

**파일**: `services/job_state_listener.py`

**리스너 시작**: `main.py`의 `lifespan` 함수에서 자동 시작

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if ENABLE_JOB_STATE_LISTENER:
        from services.job_state_listener import start_listener
        await start_listener()  # 리스너 시작
    yield
    # Shutdown 시 stop_listener()
```

**리스너 동작**:

```python
async def _connect_and_listen(self):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.add_listener('job_variant_state_changed', 
                           self._handle_variant_notification)
    
    # 무한 루프로 대기
    while self.running:
        await asyncio.sleep(1)
```

**이벤트 핸들러**:

```python
def _handle_variant_notification(self, conn, pid, channel, payload):
    data = json.loads(payload)
    job_variants_id = data.get('job_variants_id')
    job_id = data.get('job_id')
    current_step = data.get('current_step')
    status = data.get('status')
    
    # 비동기로 처리
    task = asyncio.create_task(
        self._process_job_variant_state_change(...)
    )
```

---

### 5단계: 파이프라인 트리거

**파일**: `services/pipeline_trigger.py`

**함수**: `trigger_next_pipeline_stage_for_variant()`

```python
async def trigger_next_pipeline_stage_for_variant(
    job_variants_id: str,
    job_id: str,
    current_step: str,
    status: str,
    tenant_id: str,
    img_asset_id: str
):
    # 1. 다음 단계 정보 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    next_step = stage_info['next_step']
    api_endpoint = stage_info['api_endpoint']
    
    # 2. 필요한 데이터 조회 (overlay_id, text, proposal_id 등)
    if stage_info.get('needs_overlay_id'):
        overlay_id = await _get_overlay_id_from_job_variant(job_variants_id)
    
    # 3. API 호출
    response = await httpx.post(
        f"http://localhost:8000{api_endpoint}",
        json={
            "job_variants_id": job_variants_id,
            ...
        }
    )
```

**파이프라인 단계 매핑**:

```python
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
    },
    # ... (계속)
}
```

---

### 6단계: API 엔드포인트 실행

**예시**: `routers/llava_stage1.py`

```python
@router.post("", response_model=LLaVaStage1Out)
def llava_stage1_validate(body: LLaVaStage1In, db: Session = Depends(get_db)):
    # 1. Job Variant 조회
    job_variant = db.query(JobVariant).filter(
        JobVariant.job_variants_id == body.job_variants_id
    ).first()
    
    # 2. 상태 업데이트 (running)
    job_variant.status = 'running'
    job_variant.current_step = 'vlm_analyze'
    db.commit()
    
    # 3. 실제 작업 수행 (LLaVA 모델 실행)
    result = llava_service.validate_image(...)
    
    # 4. 상태 업데이트 (done)
    job_variant.status = 'done'
    job_variant.current_step = 'vlm_analyze'
    db.commit()
    
    # 5. 트리거 자동 발동 (3단계로 돌아감)
    return result
```

**동작**:
- API 엔드포인트가 실행되면
- `jobs_variants` 테이블의 `status`와 `current_step`이 업데이트됨
- PostgreSQL 트리거가 다시 발동하여 다음 단계로 진행

---

## 🔁 순환 구조

```
┌─────────────────────────────────────────────────┐
│  API 엔드포인트 실행 완료                        │
│  (jobs_variants.status = 'done')                │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  PostgreSQL 트리거 발동                          │
│  (NOTIFY 'job_variant_state_changed')           │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  FastAPI 리스너 감지                             │
│  (job_state_listener.py)                        │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  파이프라인 트리거                               │
│  (pipeline_trigger.py)                          │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  다음 단계 API 호출                              │
│  (httpx.post)                                   │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│  API 엔드포인트 실행                             │
│  (routers/*.py)                                 │
└──────────────────┬──────────────────────────────┘
                   │
                   └───────────────┐
                                   │
                                   ▼
                          (다시 처음으로)
```

---

## 🎯 핵심 컴포넌트

### 1. PostgreSQL 트리거 (`03_job_variants_state_notify_trigger.sql`)

**역할**: 데이터베이스 상태 변화를 실시간으로 감지하여 NOTIFY 발행

**트리거 2개**:
- `notify_job_variant_state_change()`: Variant 상태 변화 시 NOTIFY
- `check_all_variants_done()`: 모든 variants 완료 시 `jobs` 테이블 자동 업데이트

### 2. FastAPI 리스너 (`services/job_state_listener.py`)

**역할**: PostgreSQL NOTIFY 이벤트를 감지하고 파이프라인 트리거

**주요 함수**:
- `start_listener()`: 리스너 시작 (애플리케이션 시작 시 자동 실행)
- `_connect_and_listen()`: PostgreSQL 연결 및 LISTEN
- `_handle_variant_notification()`: NOTIFY 이벤트 처리
- `_process_job_variant_state_change()`: Variant 상태 변화 처리
- `_recover_stuck_variants()`: 뒤처진 variants 복구

### 3. 파이프라인 트리거 (`services/pipeline_trigger.py`)

**역할**: 다음 단계 API 엔드포인트를 자동으로 호출

**주요 함수**:
- `trigger_next_pipeline_stage_for_variant()`: Variant 기반 파이프라인 트리거
- `_get_overlay_id_from_job_variant()`: Overlay ID 조회
- `_get_text_and_proposal_from_job_variant()`: 텍스트 및 Proposal 조회

### 4. FastAPI 애플리케이션 (`main.py`)

**역할**: 리스너를 애플리케이션 생명주기에 통합

**lifespan 이벤트**:
- Startup: `start_listener()` 호출
- Shutdown: `stop_listener()` 호출

---

## 📊 파이프라인 단계별 흐름

### 예시: `img_gen` → `vlm_analyze` → `yolo_detect`

```
1. img_gen 완료
   ├─ jobs_variants.status = 'done'
   ├─ jobs_variants.current_step = 'img_gen'
   └─ 트리거 발동

2. 리스너 감지
   ├─ NOTIFY 수신
   ├─ current_step='img_gen', status='done' 확인
   └─ 다음 단계: vlm_analyze

3. 파이프라인 트리거
   ├─ /api/yh/llava/stage1/validate 호출
   └─ job_variants_id 전달

4. LLaVA Stage 1 실행
   ├─ jobs_variants.status = 'running'
   ├─ LLaVA 모델 로딩 (GPU 사용)
   ├─ 이미지 분석 수행
   ├─ jobs_variants.status = 'done'
   ├─ jobs_variants.current_step = 'vlm_analyze'
   └─ 트리거 발동 (다시 1번으로)

5. yolo_detect 실행
   ├─ /api/yh/yolo/detect 호출
   └─ (반복...)
```

---

## 🔍 현재 실행 중인 프로세스 분석

### GPU 사용 중인 프로세스

**PID 12155**: FastAPI 서버 (python3.11)
- **역할**: FastAPI 애플리케이션 서버
- **내부 구성**:
  - `job_state_listener.py`: PostgreSQL NOTIFY 리스너
  - API 엔드포인트들: 파이프라인 단계 실행
  - LLaVA 모델: GPU에서 실행 중

**GPU 사용량**:
- 메모리: 10,620 MiB / 23,034 MiB
- 사용률: 19%
- 전력: 40W / 72W

### 실행 중인 백그라운드 스크립트

**없음**:
- `background_monitor.py`: 실행 안 됨
- `background_job_creator.py`: `--once` 옵션으로 종료됨

### 자동 동작 메커니즘

**FastAPI 서버 내부 리스너**가 자동으로 동작:
1. 애플리케이션 시작 시 `job_state_listener.py`가 자동 시작
2. PostgreSQL `job_variant_state_changed` 채널을 LISTEN
3. NOTIFY 이벤트를 감지하면 자동으로 파이프라인 트리거
4. 별도의 백그라운드 스크립트 없이도 완전 자동화

---

## 🆚 백그라운드 스크립트 vs 자동 트리거

### 백그라운드 스크립트 (`background_monitor.py`)

**역할**: 
- 주기적으로 데이터베이스를 폴링하여 상태 확인
- Job 생성 및 모니터링

**사용 시나리오**:
- 외부에서 Job을 생성하는 경우
- 모니터링 및 로깅이 필요한 경우
- 롱런 테스트

### 자동 트리거 (현재 동작 중)

**역할**:
- PostgreSQL NOTIFY를 통해 실시간 감지
- 자동으로 파이프라인 실행

**장점**:
- ✅ 실시간 반응 (폴링 지연 없음)
- ✅ 리소스 효율적 (이벤트 기반)
- ✅ 별도 스크립트 불필요
- ✅ FastAPI 서버와 통합

---

## 📝 주요 특징

### 1. 이벤트 기반 아키텍처

- **폴링 방식 아님**: 주기적으로 DB를 확인하지 않음
- **이벤트 기반**: 상태 변화가 발생하면 즉시 반응
- **효율적**: 리소스 사용 최소화

### 2. 완전 자동화

- **수동 개입 불필요**: Job 생성 후 자동으로 파이프라인 진행
- **백그라운드 스크립트 선택적**: 모니터링 목적으로만 사용 가능
- **FastAPI 서버 통합**: 애플리케이션과 함께 실행

### 3. 병렬 처리 지원

- **각 Variant 독립 실행**: 3개 variant가 동시에 진행
- **Thread-safe 모델 로딩**: LLaVA 모델은 한 번만 로드
- **독립적인 상태 관리**: 각 variant의 진행 상황 추적

### 4. 복구 메커니즘

- **뒤처진 Variant 감지**: Job이 진행 중인데 Variant가 뒤처진 경우
- **자동 재시작**: 다음 단계로 자동 트리거
- **실패 처리**: `failed` 상태도 재시도 가능

---

## 🔧 설정 및 활성화

### 리스너 활성화

**환경 변수**: `ENABLE_JOB_STATE_LISTENER=True`

**위치**: `config.py` 또는 `.env` 파일

```python
# config.py
ENABLE_JOB_STATE_LISTENER = os.getenv("ENABLE_JOB_STATE_LISTENER", "True") == "True"
```

### 리스너 시작

**위치**: `main.py`의 `lifespan` 함수

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if ENABLE_JOB_STATE_LISTENER:
        from services.job_state_listener import start_listener
        await start_listener()
    yield
    # Shutdown 시 stop_listener()
```

---

## 📊 현재 실행 중인 Job 예시

### Job 정보

- **Job ID**: `6c69b34f-f1f1-4eb6-95d4-17b50a1a5061`
- **Tenant ID**: `test_pipeline_monitor`
- **Status**: `running`
- **Current Step**: `vlm_analyze`

### Variants 상태

- **Variant 1**: `img_gen` (done) → `vlm_analyze` 진행 중
- **Variant 2**: `img_gen` (done) → `vlm_analyze` 진행 중
- **Variant 3**: `img_gen` (done) → `vlm_analyze` 진행 중

### 실행 흐름

1. `background_job_creator.py --once`로 job 생성
2. `trigger_job_variants()`가 트리거 발동
3. PostgreSQL 트리거가 NOTIFY 발행
4. FastAPI 리스너가 감지
5. `/api/yh/llava/stage1/validate` 자동 호출
6. LLaVA 모델이 GPU에서 로딩/실행 중

---

## 🎯 요약

### 핵심 포인트

1. **별도의 백그라운드 스크립트 불필요**
   - FastAPI 서버 내부 리스너가 자동 동작
   - `background_monitor.py`는 모니터링 목적으로만 사용

2. **완전 자동화된 파이프라인**
   - Job 생성 → 트리거 발동 → 자동 실행
   - 수동 개입 없이 모든 단계 자동 진행

3. **이벤트 기반 아키텍처**
   - PostgreSQL LISTEN/NOTIFY 사용
   - 실시간 반응, 리소스 효율적

4. **병렬 처리 지원**
   - 각 Variant가 독립적으로 실행
   - Thread-safe 모델 로딩

### 현재 GPU 사용 원인

- **FastAPI 서버** (PID 12155)가 실행 중
- **job_state_listener.py**가 NOTIFY를 감지
- **파이프라인 트리거**가 자동으로 API 호출
- **LLaVA 모델**이 GPU에서 로딩/실행 중

---

**작성일**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 1.0.0


# PostgreSQL LISTEN/NOTIFY 구현 계획

## 📋 개요

PostgreSQL LISTEN/NOTIFY를 사용하여 `jobs` 테이블의 상태 변화를 실시간으로 감지하고, 파이프라인 단계를 자동으로 실행하는 시스템을 구현합니다.

---

## 🎯 목표

1. **실시간 감지**: `jobs` 테이블의 `current_step` 또는 `status` 변경 시 즉시 감지
2. **자동 파이프라인 실행**: 조건에 맞는 job에 대해 다음 단계 API 자동 호출
3. **안정성**: 연결 끊김 시 자동 재연결, 중복 실행 방지
4. **확장성**: 여러 워커 인스턴스 지원

---

## 📊 현재 파이프라인 구조

### 파이프라인 단계 순서
```
img_gen (done) 
  → vlm_analyze (LLaVA Stage 1) [status: running → done]
  → yolo_detect [status: running → done]
  → planner [status: running → done]
  → overlay [status: running → done]
  → vlm_judge (LLaVA Stage 2) [status: running → done]
```

### 각 단계별 API 엔드포인트
| 단계 | current_step | API 엔드포인트 | 요청 필수 필드 |
|------|--------------|----------------|----------------|
| LLaVA Stage 1 | `vlm_analyze` | `POST /api/yh/llava/stage1/validate` | `job_id`, `tenant_id` |
| YOLO | `yolo_detect` | `POST /api/yh/yolo/detect` | `job_id`, `tenant_id` |
| Planner | `planner` | `POST /api/yh/planner` | `job_id`, `tenant_id` |
| Overlay | `overlay` | `POST /api/yh/overlay` | `job_id`, `tenant_id` |
| LLaVA Stage 2 | `vlm_judge` | `POST /api/yh/llava/stage2/judge` | `job_id`, `tenant_id` |

### 트리거 조건 매핑
| 이전 단계 완료 조건 | 다음 단계 |
|-------------------|----------|
| `current_step='img_gen'`, `status='done'` | → LLaVA Stage 1 |
| `current_step='vlm_analyze'`, `status='done'` | → YOLO |
| `current_step='yolo_detect'`, `status='done'` | → Planner |
| `current_step='planner'`, `status='done'` | → Overlay |
| `current_step='overlay'`, `status='done'` | → LLaVA Stage 2 |

---

## 🏗️ 구현 아키텍처

### 컴포넌트 구조
```
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │  jobs 테이블                                       │  │
│  │  - job_id (UUID)                                   │  │
│  │  - current_step (VARCHAR)                          │  │
│  │  - status (VARCHAR)                                │  │
│  └──────────────────────────────────────────────────┘  │
│           │                                             │
│           │ UPDATE 트리거                              │
│           ▼                                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │  notify_job_state_change() 함수                   │  │
│  │  - pg_notify('job_state_changed', JSON)           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                        │
                        │ NOTIFY 이벤트
                        ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI Application (app-yh)                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Job State Listener (Background Task)             │  │
│  │  - asyncpg로 LISTEN                               │  │
│  │  - 이벤트 수신 및 파싱                             │  │
│  │  - 조건 확인 및 API 호출                           │  │
│  └──────────────────────────────────────────────────┘  │
│           │                                             │
│           │ HTTP 요청                                   │
│           ▼                                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Pipeline Stage APIs                              │  │
│  │  - /api/yh/llava/stage1/validate                 │  │
│  │  - /api/yh/yolo/detect                           │  │
│  │  - /api/yh/planner                                │  │
│  │  - /api/yh/overlay                                │  │
│  │  - /api/yh/llava/stage2/judge                    │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 구현 단계

### Phase 1: PostgreSQL 트리거 및 함수 생성

#### 1.1 트리거 함수 작성
- **파일**: `db/init/02_job_state_notify_trigger.sql` (새로 생성)
- **내용**: 
  - `notify_job_state_change()` 함수 생성
  - `job_state_change_trigger` 트리거 생성
  - `current_step` 또는 `status` 변경 시에만 NOTIFY 발행

#### 1.2 트리거 적용
- Docker 컨테이너 시작 시 자동 실행되도록 `docker-compose.yml` 또는 DB 초기화 스크립트에 포함
- 또는 수동으로 SQL 실행

---

### Phase 2: Python LISTEN/NOTIFY 리스너 구현

#### 2.1 의존성 추가
- **파일**: `requirements.txt`
- **추가**: `asyncpg>=0.29.0` (PostgreSQL async 드라이버)

#### 2.2 리스너 서비스 모듈 생성
- **파일**: `services/job_state_listener.py` (새로 생성)
- **기능**:
  - `asyncpg`로 PostgreSQL 연결
  - `LISTEN 'job_state_changed'` 시작
  - 이벤트 수신 및 파싱
  - 조건 확인 및 다음 단계 API 호출
  - 재연결 로직
  - 에러 처리 및 로깅

#### 2.3 파이프라인 트리거 서비스
- **파일**: `services/pipeline_trigger.py` (새로 생성)
- **기능**:
  - 각 단계별 API 호출 함수
  - 중복 실행 방지 (job 상태 재확인)
  - HTTP 요청 및 에러 처리

---

### Phase 3: FastAPI 통합

#### 3.1 Startup 이벤트에 리스너 등록
- **파일**: `main.py`
- **변경사항**:
  - FastAPI `@app.on_event("startup")`에 리스너 시작
  - `@app.on_event("shutdown")`에 리스너 종료

#### 3.2 설정 추가
- **파일**: `config.py`
- **추가**:
  - `ENABLE_JOB_STATE_LISTENER` (기본값: `True`)
  - `JOB_STATE_LISTENER_RECONNECT_DELAY` (기본값: `5` 초)

---

### Phase 4: 테스트 및 검증

#### 4.1 단위 테스트
- 트리거 함수 테스트
- 리스너 연결 테스트
- 이벤트 수신 테스트

#### 4.2 통합 테스트
- 전체 파이프라인 자동 실행 테스트
- 재연결 시나리오 테스트
- 중복 실행 방지 테스트

---

## 🔧 상세 구현 사항

### 1. PostgreSQL 트리거 함수

```sql
-- db/init/02_job_state_notify_trigger.sql

-- 트리거 함수: jobs 테이블 변경 시 NOTIFY 발행
CREATE OR REPLACE FUNCTION notify_job_state_change()
RETURNS TRIGGER AS $$
BEGIN
    -- current_step 또는 status가 변경된 경우에만 NOTIFY 발행
    IF (OLD.current_step IS DISTINCT FROM NEW.current_step 
        OR OLD.status IS DISTINCT FROM NEW.status) THEN
        
        PERFORM pg_notify(
            'job_state_changed',
            json_build_object(
                'job_id', NEW.job_id::text,
                'current_step', NEW.current_step,
                'status', NEW.status,
                'tenant_id', NEW.tenant_id,
                'updated_at', NEW.updated_at
            )::text
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
DROP TRIGGER IF EXISTS job_state_change_trigger ON jobs;
CREATE TRIGGER job_state_change_trigger
    AFTER UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION notify_job_state_change();
```

---

### 2. Job State Listener 서비스

```python
# services/job_state_listener.py

import asyncio
import json
import logging
from typing import Optional
import asyncpg
from config import DATABASE_URL, JOB_STATE_LISTENER_RECONNECT_DELAY

logger = logging.getLogger(__name__)

class JobStateListener:
    """PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너"""
    
    def __init__(self):
        self.conn: Optional[asyncpg.Connection] = None
        self.running = False
        self.reconnect_delay = JOB_STATE_LISTENER_RECONNECT_DELAY
    
    async def start(self):
        """리스너 시작"""
        self.running = True
        await self._listen_loop()
    
    async def stop(self):
        """리스너 중지"""
        self.running = False
        if self.conn:
            await self.conn.close()
            self.conn = None
    
    async def _listen_loop(self):
        """리스너 메인 루프 (재연결 포함)"""
        while self.running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"리스너 오류 발생: {e}", exc_info=True)
                if self.running:
                    logger.info(f"{self.reconnect_delay}초 후 재연결 시도...")
                    await asyncio.sleep(self.reconnect_delay)
    
    async def _connect_and_listen(self):
        """PostgreSQL 연결 및 LISTEN 시작"""
        # DATABASE_URL에서 asyncpg 형식으로 변환
        # postgresql://user:pass@host:port/db -> postgres://user:pass@host:port/db
        asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
        
        self.conn = await asyncpg.connect(asyncpg_url)
        logger.info("PostgreSQL 연결 성공")
        
        # LISTEN 시작
        await self.conn.add_listener('job_state_changed', self._handle_notification)
        logger.info("LISTEN 'job_state_changed' 시작")
        
        # 연결이 끊길 때까지 대기
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            await self.conn.remove_listener('job_state_changed', self._handle_notification)
            await self.conn.close()
            self.conn = None
            logger.info("PostgreSQL 연결 종료")
    
    def _handle_notification(self, conn, pid, channel, payload):
        """NOTIFY 이벤트 핸들러"""
        try:
            # JSON 파싱
            data = json.loads(payload)
            job_id = data.get('job_id')
            current_step = data.get('current_step')
            status = data.get('status')
            tenant_id = data.get('tenant_id')
            
            logger.info(
                f"Job 상태 변화 감지: job_id={job_id}, "
                f"current_step={current_step}, status={status}"
            )
            
            # 비동기로 처리 (이벤트 핸들러는 동기 함수이므로)
            asyncio.create_task(
                self._process_job_state_change(job_id, current_step, status, tenant_id)
            )
            
        except Exception as e:
            logger.error(f"이벤트 처리 오류: {e}", exc_info=True)
    
    async def _process_job_state_change(
        self, 
        job_id: str, 
        current_step: Optional[str], 
        status: str,
        tenant_id: str
    ):
        """Job 상태 변화 처리 및 다음 단계 트리거"""
        from services.pipeline_trigger import trigger_next_pipeline_stage
        
        try:
            await trigger_next_pipeline_stage(
                job_id=job_id,
                current_step=current_step,
                status=status,
                tenant_id=tenant_id
            )
        except Exception as e:
            logger.error(
                f"파이프라인 트리거 오류: job_id={job_id}, error={e}",
                exc_info=True
            )


# 전역 리스너 인스턴스
_listener: Optional[JobStateListener] = None

async def start_listener():
    """리스너 시작 (FastAPI startup에서 호출)"""
    global _listener
    if _listener is None:
        _listener = JobStateListener()
        # 백그라운드 태스크로 시작
        asyncio.create_task(_listener.start())

async def stop_listener():
    """리스너 중지 (FastAPI shutdown에서 호출)"""
    global _listener
    if _listener:
        await _listener.stop()
        _listener = None
```

---

### 3. Pipeline Trigger 서비스

```python
# services/pipeline_trigger.py

import logging
import httpx
from typing import Optional
from config import HOST, PORT

logger = logging.getLogger(__name__)

# 파이프라인 단계 매핑
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
        'method': 'POST'
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST'
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'method': 'POST'
    },
    ('planner', 'done'): {
        'next_step': 'overlay',
        'api_endpoint': '/api/yh/overlay',
        'method': 'POST'
    },
    ('overlay', 'done'): {
        'next_step': 'vlm_judge',
        'api_endpoint': '/api/yh/llava/stage2/judge',
        'method': 'POST'
    },
}

async def trigger_next_pipeline_stage(
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str
):
    """다음 파이프라인 단계 트리거"""
    
    # 트리거 조건 확인
    if not current_step or status != 'done':
        return
    
    # 다음 단계 정보 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    if not stage_info:
        logger.debug(
            f"다음 단계 없음: job_id={job_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 중복 실행 방지: job 상태 재확인
    # (다른 워커가 이미 처리했을 수 있음)
    if not await _verify_job_state(job_id, current_step, status, tenant_id):
        logger.info(
            f"Job 상태가 변경되어 스킵: job_id={job_id}, "
            f"expected: current_step={current_step}, status={status}"
        )
        return
    
    # API 호출
    api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
    request_data = {
        'job_id': job_id,
        'tenant_id': tenant_id
    }
    
    logger.info(
        f"파이프라인 단계 트리거: job_id={job_id}, "
        f"next_step={stage_info['next_step']}, api={api_url}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(api_url, json=request_data)
            response.raise_for_status()
            logger.info(
                f"파이프라인 단계 실행 성공: job_id={job_id}, "
                f"next_step={stage_info['next_step']}"
            )
    except httpx.HTTPError as e:
        logger.error(
            f"파이프라인 단계 실행 실패: job_id={job_id}, "
            f"next_step={stage_info['next_step']}, error={e}"
        )
        raise

async def _verify_job_state(
    job_id: str,
    expected_step: str,
    expected_status: str,
    tenant_id: str
) -> bool:
    """Job 상태 재확인 (중복 실행 방지)"""
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT current_step, status, tenant_id
                FROM jobs
                WHERE job_id = $1
                """,
                job_id
            )
            
            if not row:
                return False
            
            # 상태 확인
            if (row['current_step'] == expected_step 
                and row['status'] == expected_status
                and row['tenant_id'] == tenant_id):
                return True
            
            return False
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Job 상태 확인 오류: {e}", exc_info=True)
        return False
```

---

### 4. FastAPI 통합

```python
# main.py (수정)

from contextlib import asynccontextmanager
from services.job_state_listener import start_listener, stop_listener
from config import ENABLE_JOB_STATE_LISTENER

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # Startup
    logger.info("애플리케이션 시작 중...")
    
    if ENABLE_JOB_STATE_LISTENER:
        logger.info("Job State Listener 시작...")
        await start_listener()
    
    yield
    
    # Shutdown
    logger.info("애플리케이션 종료 중...")
    
    if ENABLE_JOB_STATE_LISTENER:
        logger.info("Job State Listener 종료...")
        await stop_listener()

app = FastAPI(
    title=f"app-{PART_NAME} (Planner/Overlay/Eval)",
    root_path=ROOT_PATH,
    lifespan=lifespan  # lifespan 추가
)
```

---

### 5. 설정 추가

```python
# config.py (추가)

# Job State Listener 설정
ENABLE_JOB_STATE_LISTENER = os.getenv("ENABLE_JOB_STATE_LISTENER", "true").lower() in ("true", "1", "yes", "on")
JOB_STATE_LISTENER_RECONNECT_DELAY = int(os.getenv("JOB_STATE_LISTENER_RECONNECT_DELAY", "5"))
```

---

## 🧪 테스트 계획

### 1. 단위 테스트
- 트리거 함수 테스트 (SQL 직접 실행)
- 리스너 연결 테스트
- 이벤트 파싱 테스트

### 2. 통합 테스트
- 전체 파이프라인 자동 실행 테스트
- 재연결 시나리오 테스트
- 중복 실행 방지 테스트
- 여러 워커 동시 실행 테스트

### 3. 성능 테스트
- 이벤트 처리 지연시간 측정
- 동시 job 처리 성능

---

## ⚠️ 주의사항

### 1. 중복 실행 방지
- 이벤트 수신 후 즉시 job 상태 재확인
- 다른 워커가 이미 처리했을 수 있으므로 상태 확인 필수

### 2. 에러 처리
- API 호출 실패 시 로깅 및 모니터링
- 재시도 로직은 선택사항 (현재는 로깅만)

### 3. 연결 관리
- PostgreSQL 연결이 끊기면 자동 재연결
- 재연결 지연시간 설정 가능

### 4. 확장성
- 여러 워커 인스턴스가 동시에 LISTEN 가능
- 각 워커가 이벤트를 수신하지만, job 상태 재확인으로 중복 실행 방지

---

## 📦 파일 구조

```
feedlyai-work/
├── db/
│   └── init/
│       └── 02_job_state_notify_trigger.sql  (새로 생성)
├── services/
│   ├── job_state_listener.py  (새로 생성)
│   └── pipeline_trigger.py  (새로 생성)
├── main.py  (수정)
├── config.py  (수정)
└── requirements.txt  (수정)
```

---

## 🚀 배포 및 실행

### 1. 의존성 설치
```bash
pip install asyncpg>=0.29.0
```

### 2. 트리거 적용
```bash
# Docker 컨테이너에서 실행
docker exec -i feedlyai-db psql -U feedlyai -d feedlyai < db/init/02_job_state_notify_trigger.sql
```

### 3. 애플리케이션 재시작
```bash
docker-compose restart app-yh
```

### 4. 로그 확인
```bash
docker logs -f feedlyai-work-yh | grep -i "listener\|trigger\|pipeline"
```

---

## 📊 모니터링

### 로그 키워드
- `Job 상태 변화 감지`: 이벤트 수신
- `파이프라인 단계 트리거`: 다음 단계 실행 시작
- `파이프라인 단계 실행 성공`: API 호출 성공
- `파이프라인 단계 실행 실패`: API 호출 실패
- `리스너 오류 발생`: 리스너 오류
- `재연결 시도`: 재연결 시작

### 메트릭 (선택사항)
- 이벤트 수신 횟수
- 파이프라인 트리거 횟수
- API 호출 성공/실패 횟수
- 재연결 횟수

---

## 🔄 다음 단계

1. **구현 시작**: Phase 1부터 순차적으로 구현
2. **테스트**: 각 Phase별 테스트 수행
3. **모니터링**: 운영 환경에서 로그 및 메트릭 확인
4. **최적화**: 필요 시 성능 및 안정성 개선


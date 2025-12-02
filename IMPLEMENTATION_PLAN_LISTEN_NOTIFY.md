# PostgreSQL LISTEN/NOTIFY 구현 계획

## 📋 개요

PostgreSQL LISTEN/NOTIFY를 사용하여 `jobs_variants` 테이블의 상태 변화를 실시간으로 감지하고, 파이프라인 단계를 자동으로 실행하는 시스템입니다.

**현재 구현 상태**: ✅ 완료 (2025-12-01)
- `jobs_variants` 테이블 기반 자동 트리거
- `job_variant_state_changed` 채널 리스닝
- 10단계 파이프라인 자동화
- 뒤처진 variants 자동 복구
- 주기적 수동 복구 체크

---

## 🎯 목표

1. **실시간 감지**: `jobs_variants` 테이블의 `current_step` 또는 `status` 변경 시 즉시 감지
2. **자동 파이프라인 실행**: 조건에 맞는 variant에 대해 다음 단계 API 자동 호출
3. **안정성**: 연결 끊김 시 자동 재연결, 중복 실행 방지
4. **확장성**: 여러 워커 인스턴스 지원
5. **복구 메커니즘**: 뒤처진 variants 자동 복구, 주기적 수동 복구 체크

---

## 📊 현재 파이프라인 구조

### 파이프라인 단계 순서 (10단계)
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

### 각 단계별 API 엔드포인트
| 단계 | current_step | API 엔드포인트 | 실행 레벨 | 요청 필수 필드 |
|------|--------------|----------------|-----------|----------------|
| LLaVA Stage 1 | `vlm_analyze` | `POST /api/yh/llava/stage1/validate` | Variant | `job_variants_id`, `tenant_id` |
| YOLO | `yolo_detect` | `POST /api/yh/yolo/detect` | Variant | `job_variants_id`, `tenant_id` |
| Planner | `planner` | `POST /api/yh/planner` | Variant | `job_variants_id`, `tenant_id` |
| Overlay | `overlay` | `POST /api/yh/overlay` | Variant | `job_variants_id`, `text`, `proposal_id` |
| LLaVA Stage 2 | `vlm_judge` | `POST /api/yh/llava/stage2/judge` | Variant | `job_variants_id`, `overlay_id` |
| OCR 평가 | `ocr_eval` | `POST /api/yh/ocr/evaluate` | Variant | `job_variants_id`, `overlay_id` |
| 가독성 평가 | `readability_eval` | `POST /api/yh/readability/evaluate` | Variant | `job_variants_id`, `overlay_id` |
| IoU 평가 | `iou_eval` | `POST /api/yh/iou/evaluate` | Variant | `job_variants_id`, `overlay_id` |
| Eng→Kor 변환 | `ad_copy_gen_kor` | `POST /api/yh/gpt/eng-to-kor` | Job | `job_id`, `tenant_id` |
| 피드 생성 | `instagram_feed_gen` | `POST /api/yh/instagram/feed` | Job | `job_id`, `tenant_id` |

### 트리거 조건 매핑
| 이전 단계 완료 조건 | 다음 단계 | 실행 레벨 |
|-------------------|----------|----------|
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

## 🏗️ 구현 아키텍처

### 컴포넌트 구조
```
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                     │
│  ┌──────────────────────────────────────────────────┐  │
│  │  jobs_variants 테이블                             │  │
│  │  - job_variants_id (UUID)                        │  │
│  │  - job_id (UUID)                                  │  │
│  │  - current_step (VARCHAR)                         │  │
│  │  - status (VARCHAR)                               │  │
│  │  - img_asset_id (UUID)                            │  │
│  └──────────────────────────────────────────────────┘  │
│           │                                             │
│           │ UPDATE 트리거                              │
│           ▼                                             │
│  ┌──────────────────────────────────────────────────┐  │
│  │  notify_job_variant_state_change() 함수          │  │
│  │  - pg_notify('job_variant_state_changed', JSON) │  │
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
│  │  - job_variant_state_changed 채널 리스닝          │  │
│  │  - 이벤트 수신 및 파싱                             │  │
│  │  - 조건 확인 및 API 호출                           │  │
│  │  - 뒤처진 variants 자동 복구                       │  │
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
│  │  - /api/yh/ocr/evaluate                          │  │
│  │  - /api/yh/readability/evaluate                  │  │
│  │  - /api/yh/iou/evaluate                          │  │
│  │  - /api/yh/gpt/eng-to-kor                        │  │
│  │  - /api/yh/instagram/feed                        │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 📝 구현 단계

### Phase 1: PostgreSQL 트리거 및 함수 생성 ✅ 완료

#### 1.1 트리거 함수 작성
- **파일**: `db/init/03_job_variants_state_notify_trigger.sql` (구현 완료)
- **내용**: 
  - `notify_job_variant_state_change()` 함수 생성
  - `job_variant_state_change_trigger` 트리거 생성
  - `current_step` 또는 `status` 변경 시에만 NOTIFY 발행
  - `job_variant_state_changed` 채널로 이벤트 발행

#### 1.2 트리거 적용
- ✅ Docker 컨테이너 시작 시 자동 실행
- ✅ 데이터베이스 초기화 시 자동 적용

---

### Phase 2: Python LISTEN/NOTIFY 리스너 구현 ✅ 완료

#### 2.1 의존성 추가
- **파일**: `requirements.txt`
- **추가**: ✅ `asyncpg>=0.29.0` (PostgreSQL async 드라이버)

#### 2.2 리스너 서비스 모듈 생성
- **파일**: `services/job_state_listener.py` ✅ 구현 완료
- **기능**:
  - ✅ `asyncpg`로 PostgreSQL 연결
  - ✅ `LISTEN 'job_variant_state_changed'` 시작
  - ✅ `LISTEN 'job_state_changed'` 시작 (뒤처진 variants 복구용)
  - ✅ 이벤트 수신 및 파싱
  - ✅ 조건 확인 및 다음 단계 API 호출
  - ✅ 재연결 로직
  - ✅ 뒤처진 variants 자동 복구
  - ✅ 주기적 수동 복구 체크 (1분 간격)
  - ✅ 에러 처리 및 로깅

#### 2.3 파이프라인 트리거 서비스
- **파일**: `services/pipeline_trigger.py` ✅ 구현 완료
- **기능**:
  - ✅ 각 단계별 API 호출 함수
  - ✅ Variant 기반 트리거 (`trigger_next_pipeline_stage_for_variant`)
  - ✅ Job 기반 트리거 (`trigger_next_pipeline_stage`)
  - ✅ 중복 실행 방지 (variant/job 상태 재확인)
  - ✅ overlay_id 자동 조회
  - ✅ text 및 proposal_id 자동 조회
  - ✅ HTTP 요청 및 에러 처리

---

### Phase 3: FastAPI 통합 ✅ 완료

#### 3.1 Startup 이벤트에 리스너 등록
- **파일**: `main.py` ✅ 구현 완료
- **변경사항**:
  - ✅ FastAPI `lifespan` 이벤트에 리스너 시작
  - ✅ `lifespan` shutdown에 리스너 종료
  - ✅ `ENABLE_JOB_STATE_LISTENER` 환경 변수로 활성화/비활성화 제어

#### 3.2 설정 추가
- **파일**: `config.py` ✅ 구현 완료
- **추가**:
  - ✅ `ENABLE_JOB_STATE_LISTENER` (기본값: `True`)
  - ✅ `JOB_STATE_LISTENER_RECONNECT_DELAY` (기본값: `5` 초)

---

### Phase 4: 테스트 및 검증 ✅ 완료

#### 4.1 단위 테스트
- ✅ 트리거 함수 테스트
- ✅ 리스너 연결 테스트
- ✅ 이벤트 수신 테스트

#### 4.2 통합 테스트
- ✅ 전체 파이프라인 자동 실행 테스트
- ✅ 재연결 시나리오 테스트
- ✅ 중복 실행 방지 테스트
- ✅ 뒤처진 variants 복구 테스트
- ✅ 주기적 수동 복구 체크 테스트

#### 4.3 테스트 스크립트
- ✅ `test/test_listener_status.py`: 리스너 상태 확인
- ✅ `test/test_ye_img_gen_trigger.py`: YE 파트 트리거 테스트
- ✅ `scripts/background_pipeline_with_text_generation.py`: 전체 파이프라인 테스트

---

## 🔧 상세 구현 사항

### 1. PostgreSQL 트리거 함수 (현재 구현)

```sql
-- db/init/03_job_variants_state_notify_trigger.sql

-- 트리거 함수: jobs_variants 테이블 변경 시 NOTIFY 발행
CREATE OR REPLACE FUNCTION notify_job_variant_state_change()
RETURNS TRIGGER AS $$
BEGIN
    -- current_step 또는 status가 변경된 경우에만 NOTIFY 발행
    IF (OLD.current_step IS DISTINCT FROM NEW.current_step 
        OR OLD.status IS DISTINCT FROM NEW.status) THEN
        
        PERFORM pg_notify(
            'job_variant_state_changed',
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
        logger.info("PostgreSQL 연결 성공 (Job State Listener)")
        
        # LISTEN 시작 (두 채널 모두 리스닝)
        await self.conn.add_listener('job_state_changed', self._handle_notification)
        await self.conn.add_listener('job_variant_state_changed', self._handle_variant_notification)
        logger.info("LISTEN 'job_state_changed' 시작")
        logger.info("LISTEN 'job_variant_state_changed' 시작")
        
        # 연결이 끊길 때까지 대기
        try:
            while self.running:
                await asyncio.sleep(1)
        finally:
            await self.conn.remove_listener('job_state_changed', self._handle_notification)
            await self.conn.remove_listener('job_variant_state_changed', self._handle_variant_notification)
            await self.conn.close()
            self.conn = None
            logger.info("PostgreSQL 연결 종료 (Job State Listener)")
    
    def _handle_notification(self, conn, pid, channel, payload):
        """NOTIFY 이벤트 핸들러 (job_state_changed)"""
        try:
            # JSON 파싱
            data = json.loads(payload)
            job_id = data.get('job_id')
            current_step = data.get('current_step')
            status = data.get('status')
            tenant_id = data.get('tenant_id')
            
            logger.info(
                f"Job 상태 변화 감지: job_id={job_id}, "
                f"current_step={current_step}, status={status}, tenant_id={tenant_id}"
            )
            
            # 비동기로 처리 (이벤트 핸들러는 동기 함수이므로)
            task = asyncio.create_task(
                self._process_job_state_change(job_id, current_step, status, tenant_id)
            )
            self.pending_tasks.add(task)
            task.add_done_callback(self.pending_tasks.discard)
            
        except Exception as e:
            logger.error(f"이벤트 처리 오류: {e}", exc_info=True)
    
    def _handle_variant_notification(self, conn, pid, channel, payload):
        """NOTIFY 이벤트 핸들러 (job_variant_state_changed)"""
        try:
            # JSON 파싱
            data = json.loads(payload)
            job_variants_id = data.get('job_variants_id')
            job_id = data.get('job_id')
            current_step = data.get('current_step')
            status = data.get('status')
            tenant_id = data.get('tenant_id')
            img_asset_id = data.get('img_asset_id')
            
            logger.info(
                f"Job Variant 상태 변화 감지: job_variants_id={job_variants_id}, job_id={job_id}, "
                f"current_step={current_step}, status={status}, tenant_id={tenant_id}, img_asset_id={img_asset_id}"
            )
            
            # 비동기로 처리
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
            self.pending_tasks.add(task)
            task.add_done_callback(self.pending_tasks.discard)
            
        except Exception as e:
            logger.error(f"이벤트 처리 오류 (variant): {e}", exc_info=True)
    
    async def _process_job_state_change(
        self, 
        job_id: str, 
        current_step: Optional[str], 
        status: str,
        tenant_id: str
    ):
        """Job 상태 변화 처리 및 뒤처진 variants 복구"""
        # Job 상태 변화는 주로 뒤처진 variants 복구에 사용
        # 실제 파이프라인 트리거는 variant 기반으로 동작
        try:
            # 뒤처진 variants 복구 로직
            # (구현 세부사항은 services/job_state_listener.py 참고)
            pass
        except Exception as e:
            logger.error(
                f"Job 상태 처리 오류: job_id={job_id}, error={e}",
                exc_info=True
            )
    
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
        from services.pipeline_trigger import trigger_next_pipeline_stage_for_variant
        
        try:
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

# 파이프라인 단계 매핑 (10단계)
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'method': 'POST',
        'needs_overlay_id': False
    },
    ('planner', 'done'): {
        'next_step': 'overlay',
        'api_endpoint': '/api/yh/overlay',
        'method': 'POST',
        'needs_overlay_id': False,
        'needs_text_and_proposal': True
    },
    ('overlay', 'done'): {
        'next_step': 'vlm_judge',
        'api_endpoint': '/api/yh/llava/stage2/judge',
        'method': 'POST',
        'needs_overlay_id': True
    },
    ('vlm_judge', 'done'): {
        'next_step': 'ocr_eval',
        'api_endpoint': '/api/yh/ocr/evaluate',
        'method': 'POST',
        'needs_overlay_id': True
    },
    ('ocr_eval', 'done'): {
        'next_step': 'readability_eval',
        'api_endpoint': '/api/yh/readability/evaluate',
        'method': 'POST',
        'needs_overlay_id': True
    },
    ('readability_eval', 'done'): {
        'next_step': 'iou_eval',
        'api_endpoint': '/api/yh/iou/evaluate',
        'method': 'POST',
        'needs_overlay_id': True
    },
    # Job 레벨 단계
    ('iou_eval', 'done'): {
        'next_step': 'ad_copy_gen_kor',
        'api_endpoint': '/api/yh/gpt/eng-to-kor',
        'method': 'POST',
        'is_job_level': True,
        'needs_overlay_id': False
    },
    ('ad_copy_gen_kor', 'done'): {
        'next_step': 'instagram_feed_gen',
        'api_endpoint': '/api/yh/instagram/feed',
        'method': 'POST',
        'is_job_level': True,
        'needs_overlay_id': False
    },
}

async def trigger_next_pipeline_stage_for_variant(
    job_variants_id: str,
    job_id: str,
    current_step: Optional[str],
    status: str,
    tenant_id: str,
    img_asset_id: str
):
    """다음 파이프라인 단계 트리거 (job_variants_id 기반)"""
    
    # 트리거 조건 확인
    if not current_step or status != 'done':
        logger.debug(
            f"트리거 조건 불만족: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 다음 단계 정보 조회
    stage_info = PIPELINE_STAGES.get((current_step, status))
    if not stage_info:
        logger.debug(
            f"다음 단계 없음: job_variants_id={job_variants_id}, "
            f"current_step={current_step}, status={status}"
        )
        return
    
    # 중복 실행 방지: job_variant 상태 재확인
    if not await _verify_job_variant_state(job_variants_id, current_step, status, tenant_id):
        logger.info(
            f"Job Variant 상태가 변경되어 스킵: job_variants_id={job_variants_id}, "
            f"expected: current_step={current_step}, status={status}"
        )
        return
    
    # API 호출
    api_url = f"http://{HOST}:{PORT}{stage_info['api_endpoint']}"
    request_data = {
        'job_variants_id': job_variants_id,  # 필수 파라미터
        'job_id': job_id,  # 호환성을 위해 유지
        'tenant_id': tenant_id
    }
    
    # overlay_id가 필요한 경우 조회
    if stage_info.get('needs_overlay_id', False):
        overlay_id = await _get_overlay_id_from_job_variant(job_variants_id, job_id, tenant_id)
        if overlay_id:
            request_data['overlay_id'] = overlay_id
    
    # text와 proposal_id가 필요한 경우 조회
    if stage_info.get('needs_text_and_proposal', False):
        text, proposal_id = await _get_text_and_proposal_from_job_variant(job_variants_id)
        if text and proposal_id:
            request_data['text'] = text
            request_data['proposal_id'] = proposal_id
    
    logger.info(
        f"[TRIGGER] 파이프라인 단계 트리거 (variant): "
        f"job_variants_id={job_variants_id}, next_step={stage_info['next_step']}"
    )
    
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(api_url, json=request_data)
            response.raise_for_status()
            logger.info(
                f"파이프라인 단계 실행 성공 (variant): job_variants_id={job_variants_id}, "
                f"next_step={stage_info['next_step']}"
            )
    except httpx.HTTPError as e:
        logger.error(
            f"파이프라인 단계 실행 실패 (variant): job_variants_id={job_variants_id}, "
            f"next_step={stage_info['next_step']}, error={e}"
        )
        # 실패 시 variant 상태를 'failed'로 업데이트
        await _update_variant_status(job_variants_id, 'failed')
        raise

async def _verify_job_variant_state(
    job_variants_id: str,
    expected_step: str,
    expected_status: str,
    tenant_id: str
) -> bool:
    """Job Variant 상태 재확인 (중복 실행 방지)"""
    import asyncpg
    from config import DATABASE_URL
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    try:
        conn = await asyncpg.connect(asyncpg_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT jv.current_step, jv.status, j.tenant_id
                FROM jobs_variants jv
                INNER JOIN jobs j ON jv.job_id = j.job_id
                WHERE jv.job_variants_id = $1
                """,
                uuid.UUID(job_variants_id)
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
        logger.error(f"Job Variant 상태 확인 오류: {e}", exc_info=True)
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

## 📦 파일 구조 (현재 구현)

```
feedlyai-work/
├── db/
│   └── init/
│       └── 03_job_variants_state_notify_trigger.sql  ✅ 구현 완료
├── services/
│   ├── job_state_listener.py  ✅ 구현 완료 (v2.3.0)
│   └── pipeline_trigger.py  ✅ 구현 완료 (v2.1.0)
├── main.py  ✅ 구현 완료 (lifespan 이벤트)
├── config.py  ✅ 구현 완료
└── requirements.txt  ✅ 구현 완료
```

---

## 🚀 배포 및 실행

### 1. 의존성 설치
```bash
pip install asyncpg>=0.29.0
```

### 2. 트리거 적용
```bash
# Docker 컨테이너에서 실행 (이미 자동 적용됨)
# 또는 수동으로 실행하려면:
docker exec -i feedlyai-db psql -U feedlyai -d feedlyai < db/init/03_job_variants_state_notify_trigger.sql
```

### 3. 애플리케이션 재시작
```bash
docker-compose restart app-yh
```

### 4. 로그 확인
```bash
# 리스너 로그 확인
docker logs -f feedlyai-work-yh | grep -E "Job Variant|트리거|trigger|리스너"

# 실시간 모니터링
docker logs -f feedlyai-work-yh | grep -E "LISTENER|TRIGGER"
```

---

## 📊 모니터링

### 로그 키워드
- `Job Variant 상태 변화 감지`: Variant 이벤트 수신
- `Job 상태 변화 감지`: Job 이벤트 수신 (복구용)
- `[TRIGGER] 파이프라인 단계 트리거`: 다음 단계 실행 시작
- `파이프라인 단계 실행 성공`: API 호출 성공
- `파이프라인 단계 실행 실패`: API 호출 실패
- `뒤처진 variants 복구`: 자동 복구 실행
- `수동 복구 체크`: 주기적 복구 체크
- `리스너 오류 발생`: 리스너 오류
- `재연결 시도`: 재연결 시작

### 메트릭 (선택사항)
- 이벤트 수신 횟수
- 파이프라인 트리거 횟수
- API 호출 성공/실패 횟수
- 재연결 횟수

---

## 🔄 현재 상태 및 향후 계획

### ✅ 완료된 기능
1. **PostgreSQL 트리거**: `jobs_variants` 테이블 기반 NOTIFY 발행
2. **리스너 구현**: 두 채널 리스닝 (`job_state_changed`, `job_variant_state_changed`)
3. **파이프라인 트리거**: 10단계 자동화
4. **복구 메커니즘**: 뒤처진 variants 자동 복구, 주기적 수동 복구
5. **테스트**: 통합 테스트 완료

### 🔄 향후 개선 사항
1. **성능 최적화**: 대량 job 처리 시 성능 튜닝
2. **모니터링 강화**: 메트릭 수집 및 대시보드 구축
3. **에러 처리 개선**: 더 세밀한 에러 분류 및 복구 전략
4. **문서화**: 운영 가이드 및 트러블슈팅 가이드 보완

---

**최종 업데이트**: 2025-12-02  
**구현 상태**: ✅ 완료  
**버전**: 2.3.0


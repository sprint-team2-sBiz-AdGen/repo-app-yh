# 파이프라인 전체 분석 문서

## 📋 개요

이 문서는 FeedlyAI 광고 생성 파이프라인의 전체 흐름과 각 단계별 상세 정보를 정리한 문서입니다.

**작성일**: 2025-11-28  
**버전**: 1.0.0  
**작성자**: LEEYH205

---

## 🔄 파이프라인 전체 흐름

```
img_gen (done)
  ↓ [자동 실행]
vlm_analyze (LLaVA Stage 1)
  ↓ [자동 실행]
yolo_detect
  ↓ [자동 실행]
planner
  ↓ [자동 실행]
overlay
  ↓ [자동 실행]
vlm_judge (LLaVA Stage 2)
  ↓ [자동 실행]
ocr_eval (OCR 평가)
  ↓ [자동 실행]
readability_eval (가독성 평가)
  ↓ [자동 실행]
iou_eval (IoU 평가)
```

**총 8단계**로 구성된 완전 자동화 파이프라인입니다.

---

## 🏗️ 파이프라인 실행 메커니즘

### PostgreSQL LISTEN/NOTIFY 기반 이벤트 드리븐 아키텍처

1. **PostgreSQL 트리거**: `jobs` 테이블의 `current_step` 또는 `status` 변경 시 `pg_notify` 이벤트 발행
2. **Python 리스너**: `asyncpg`를 사용하여 PostgreSQL `LISTEN`으로 이벤트 수신
3. **자동 트리거**: 이벤트 수신 시 `pipeline_trigger.py`가 다음 단계 API 자동 호출

### 중복 실행 방지

- Job 상태 재확인으로 중복 실행 방지
- 여러 워커 인스턴스가 동시에 실행되어도 안전

### 비동기 태스크 관리

리스너는 NOTIFY 이벤트를 비동기 태스크로 처리하며, 다음 메커니즘으로 안정성을 보장합니다:

1. **태스크 추적**: 실행 중인 모든 태스크를 `pending_tasks`에 추적
2. **자동 제거**: 태스크 완료 시 자동으로 추적 목록에서 제거
3. **종료 시 완료 대기**: 애플리케이션 종료 시 실행 중인 태스크가 완료될 때까지 대기 (최대 30초)
4. **안전한 종료**: 타임아웃 후에도 완료되지 않은 태스크는 취소하여 안전하게 종료

**개발 환경 주의사항**:
- FastAPI WatchFiles 자동 리로드로 인해 리스너가 재시작될 수 있음
- 재시작 중 NOTIFY 이벤트가 손실될 수 있음 (개발 환경 특성)
- 프로덕션 환경에서는 자동 리로드가 없어 이 문제가 발생하지 않음

**프로덕션 환경**:
- 백그라운드로 계속 실행되므로 자동 리로드 문제 없음
- 재시작/배포 시에도 실행 중인 태스크가 완료될 때까지 대기하여 안정성 보장

---

## 📊 단계별 상세 정보

### 1단계: LLaVA Stage 1 (이미지 분석)

**이전 단계**: `img_gen (done)`

**API 엔드포인트**: `POST /api/yh/llava/stage1/validate`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string"
}
```

**Job 상태 변화**:
- 시작: `current_step='vlm_analyze'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 이미지와 텍스트의 관련성 검증
- 폰트 추천 (스타일, 크기, 색상)
- 이미지 유효성 판단

**다음 단계**: `yolo_detect`

**DB 저장**:
- `vlm_traces` 테이블에 분석 결과 저장
- `operation_type='analyze'`

---

### 2단계: YOLO (객체 감지)

**이전 단계**: `vlm_analyze (done)`

**API 엔드포인트**: `POST /api/yh/yolo/detect`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string"
}
```

**Job 상태 변화**:
- 시작: `current_step='yolo_detect'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 음식 객체 감지 (YOLO 모델)
- 금지 영역 마스크 생성
- 바운딩 박스 좌표 저장

**다음 단계**: `planner`

**DB 저장**:
- `detections` 테이블에 감지 결과 저장
- `yolo_runs` 테이블에 실행 정보 저장
- `forbidden_mask_url` 생성

---

### 3단계: Planner (위치 제안)

**이전 단계**: `yolo_detect (done)`

**API 엔드포인트**: `POST /api/yh/planner`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "asset_url": "string (Optional)",
  "detections": "array (Optional)",
  "min_overlay_width": "float (Optional, 기본값: 0.5)",
  "min_overlay_height": "float (Optional, 기본값: 0.12)",
  "max_proposals": "int (Optional, 기본값: 10)",
  "max_forbidden_iou": "float (Optional, 기본값: 0.05)"
}
```

**Job 상태 변화**:
- 시작: `current_step='planner'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 텍스트 오버레이 최적 위치 제안 (최대 10개)
- 금지 영역(음식, 사람) 회피
- 다양한 위치 옵션 제공 (상단, 중앙, 하단 등)
- 최대 크기 제안 포함

**다음 단계**: `overlay`

**DB 저장**:
- `planner_proposals` 테이블에 제안 저장
- `layout` JSONB에 모든 제안 정보 저장

---

### 4단계: Overlay (텍스트 오버레이)

**이전 단계**: `planner (done)`

**API 엔드포인트**: `POST /api/yh/overlay`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "proposal_id": "string (UUID, Optional)",
  "text": "string",
  "x_align": "string (center|left|right)",
  "y_align": "string (top|center|bottom)",
  "text_size": "int (Optional)",
  "overlay_color": "string (hex, Optional)",
  "text_color": "string (hex, Optional)",
  "margin": "string (Optional)"
}
```

**Job 상태 변화**:
- 시작: `current_step='overlay'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 이미지에 텍스트 오버레이 적용
- Planner 제안 위치 사용 또는 수동 위치 지정
- 동적 폰트 크기 조정
- 한글 폰트 지원

**다음 단계**: `vlm_judge`

**DB 저장**:
- `overlay_layouts` 테이블에 레이아웃 정보 저장
- `render_asset_url` 생성 (최종 이미지)

---

### 5단계: LLaVA Stage 2 (최종 검증)

**이전 단계**: `overlay (done)`

**API 엔드포인트**: `POST /api/yh/llava/stage2/judge`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "overlay_id": "string (UUID, Optional)",
  "render_asset_url": "string (Optional)"
}
```

**Job 상태 변화**:
- 시작: `current_step='vlm_judge'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 최종 광고 시각 결과물 판단
- Brief 준수 여부 확인
- 가림(occlusion) 검증
- 대비(contrast) 적절성 확인
- CTA 존재 여부 확인

**다음 단계**: `ocr_eval`

**DB 저장**:
- `vlm_traces` 테이블에 판단 결과 저장
- `operation_type='judge'`

---

### 6단계: OCR 평가 (정량 평가)

**이전 단계**: `vlm_judge (done)`

**API 엔드포인트**: `POST /api/yh/ocr/evaluate`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "overlay_id": "string (UUID)"  // 필수
}
```

**Job 상태 변화**:
- 시작: `current_step='ocr_eval'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 텍스트 인식률 확인 (EasyOCR)
- 원본 텍스트와 OCR 인식 텍스트 비교
- 정확도 계산 (문자 일치율, 단어 일치율)

**다음 단계**: `readability_eval`

**DB 저장**:
- `evaluations` 테이블에 평가 결과 저장
- `evaluation_type='ocr'`
- `metrics` JSONB에 상세 메트릭 저장

**특이사항**:
- `overlay_id` 자동 조회 (파이프라인 트리거에서 처리)

---

### 7단계: 가독성 평가 (정량 평가)

**이전 단계**: `ocr_eval (done)`

**API 엔드포인트**: `POST /api/yh/readability/evaluate`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "overlay_id": "string (UUID)"  // 필수
}
```

**Job 상태 변화**:
- 시작: `current_step='readability_eval'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 텍스트와 배경 색상 대비 확인
- WCAG 2.1 기준 검증 (AA, AAA)
- 가독성 점수 계산 (0.0-1.0)
- 실제 이미지에서 배경 색상 샘플링

**다음 단계**: `iou_eval`

**DB 저장**:
- `evaluations` 테이블에 평가 결과 저장
- `evaluation_type='readability'`
- `metrics` JSONB에 상세 메트릭 저장

**특이사항**:
- `overlay_id` 자동 조회 (파이프라인 트리거에서 처리)

---

### 8단계: IoU 평가 (정량 평가)

**이전 단계**: `readability_eval (done)`

**API 엔드포인트**: `POST /api/yh/iou/evaluate`

**요청 파라미터**:
```json
{
  "job_id": "string (UUID)",
  "tenant_id": "string",
  "overlay_id": "string (UUID)"  // 필수
}
```

**Job 상태 변화**:
- 시작: `current_step='iou_eval'`, `status='running'`
- 완료: `status='done'`
- 실패: `status='failed'`

**주요 기능**:
- 음식 바운딩 박스와 텍스트 영역 겹침 확인
- IoU (Intersection over Union) 계산
- 최대 IoU를 가진 detection ID 찾기
- 겹침 감지 여부 확인

**다음 단계**: 없음 (파이프라인 종료)

**DB 저장**:
- `evaluations` 테이블에 평가 결과 저장
- `evaluation_type='iou'`
- `metrics` JSONB에 상세 메트릭 저장

**특이사항**:
- `overlay_id` 자동 조회 (파이프라인 트리거에서 처리)

---

## 🔧 파이프라인 트리거 설정

### 파이프라인 단계 매핑 (`services/pipeline_trigger.py`)

```python
PIPELINE_STAGES = {
    ('img_gen', 'done'): {
        'next_step': 'vlm_analyze',
        'api_endpoint': '/api/yh/llava/stage1/validate',
        'needs_overlay_id': False
    },
    ('vlm_analyze', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'needs_overlay_id': False
    },
    ('yolo_detect', 'done'): {
        'next_step': 'planner',
        'api_endpoint': '/api/yh/planner',
        'needs_overlay_id': False
    },
    ('planner', 'done'): {
        'next_step': 'overlay',
        'api_endpoint': '/api/yh/overlay',
        'needs_overlay_id': False
    },
    ('overlay', 'done'): {
        'next_step': 'vlm_judge',
        'api_endpoint': '/api/yh/llava/stage2/judge',
        'needs_overlay_id': False
    },
    ('vlm_judge', 'done'): {
        'next_step': 'ocr_eval',
        'api_endpoint': '/api/yh/ocr/evaluate',
        'needs_overlay_id': True
    },
    ('ocr_eval', 'done'): {
        'next_step': 'readability_eval',
        'api_endpoint': '/api/yh/readability/evaluate',
        'needs_overlay_id': True
    },
    ('readability_eval', 'done'): {
        'next_step': 'iou_eval',
        'api_endpoint': '/api/yh/iou/evaluate',
        'needs_overlay_id': True
    },
}
```

### overlay_id 자동 조회

정량 평가 단계(OCR, Readability, IoU)는 `overlay_id`가 필요합니다. 파이프라인 트리거가 자동으로 조회합니다:

```sql
SELECT ol.overlay_id
FROM jobs j
INNER JOIN job_inputs ji ON j.job_id = ji.job_id
INNER JOIN planner_proposals pp ON ji.img_asset_id = pp.image_asset_id
INNER JOIN overlay_layouts ol ON pp.proposal_id = ol.proposal_id
WHERE j.job_id = $1
  AND j.tenant_id = $2
ORDER BY ol.created_at DESC
LIMIT 1
```

---

## 📈 Job 상태 관리

### Job 상태 값

- `queued`: 대기 중
- `running`: 실행 중
- `done`: 완료
- `failed`: 실패

### current_step 값

- `img_gen`: 이미지 생성 완료
- `vlm_analyze`: LLaVA Stage 1 분석
- `yolo_detect`: YOLO 객체 감지
- `planner`: 위치 제안
- `overlay`: 텍스트 오버레이
- `vlm_judge`: LLaVA Stage 2 판단
- `ocr_eval`: OCR 평가
- `readability_eval`: 가독성 평가
- `iou_eval`: IoU 평가

### 상태 전이 패턴

각 단계는 다음 패턴을 따릅니다:

1. **시작**: `current_step='{step_name}'`, `status='running'`
2. **완료**: `status='done'` (current_step은 유지)
3. **실패**: `status='failed'` (오류 처리 시)

---

## 🗄️ 데이터베이스 테이블 구조

### 주요 테이블

1. **jobs**: Job 상태 및 진행 상황
   - `job_id`, `tenant_id`, `status`, `current_step`

2. **job_inputs**: Job 입력 데이터
   - `job_id`, `img_asset_id`, `desc_eng`

3. **image_assets**: 이미지 자산 정보
   - `image_asset_id`, `image_url`, `width`, `height`

4. **vlm_traces**: LLaVA 분석 결과
   - `vlm_trace_id`, `job_id`, `operation_type`, `response`

5. **detections**: YOLO 감지 결과
   - `detection_id`, `job_id`, `label`, `box`, `score`

6. **yolo_runs**: YOLO 실행 정보
   - `yolo_run_id`, `job_id`, `forbidden_mask_url`

7. **planner_proposals**: 위치 제안
   - `proposal_id`, `image_asset_id`, `layout` (JSONB)

8. **overlay_layouts**: 오버레이 레이아웃
   - `overlay_id`, `proposal_id`, `layout` (JSONB), `render_asset_url`

9. **evaluations**: 정량 평가 결과
   - `evaluation_id`, `job_id`, `overlay_id`, `evaluation_type`, `metrics` (JSONB)

---

## 🔍 에러 처리

### 공통 에러 처리 패턴

모든 단계는 다음 패턴으로 에러를 처리합니다:

1. **HTTPException 발생 시**:
   - Job 상태를 `failed`로 업데이트
   - 예외를 상위로 전파

2. **일반 예외 발생 시**:
   - Job 상태를 `failed`로 업데이트
   - HTTPException으로 변환하여 반환

3. **상태 업데이트 실패 시**:
   - 로그 기록 후 결과는 반환 (가능한 경우)

### 리스너 및 트리거 에러 처리

1. **이벤트 처리 오류**:
   - JSON 파싱 실패, 이벤트 핸들러 오류 등은 로그에 기록하고 계속 실행
   - 개별 이벤트 오류가 전체 리스너를 중단시키지 않음

2. **파이프라인 트리거 오류**:
   - API 호출 실패 시 로그에 기록하고 다음 이벤트 처리 계속
   - Job 상태 재확인 실패 시 스킵 (다른 워커가 이미 처리했을 수 있음)

3. **애플리케이션 종료 시**:
   - 실행 중인 모든 태스크 완료 대기 (최대 30초)
   - 타임아웃 후 미완료 태스크는 취소하여 안전하게 종료
   - PostgreSQL 연결 정리 및 리스너 제거

---

## 🚀 파이프라인 시작 방법

### 방법 1: img_gen 완료 상태로 Job 생성

```python
# Job을 img_gen 완료 상태로 생성
INSERT INTO jobs (job_id, tenant_id, status, current_step)
VALUES (gen_random_uuid(), 'tenant_id', 'done', 'img_gen');
```

### 방법 2: 수동 API 호출

```bash
# LLaVA Stage 1 수동 호출
curl -X POST http://localhost:8011/api/yh/llava/stage1/validate \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job-uuid", "tenant_id": "tenant-id"}'
```

---

## 📊 파이프라인 성능

### 예상 실행 시간

- **LLaVA Stage 1**: ~10-30초
- **YOLO**: ~5-15초
- **Planner**: ~1-5초
- **Overlay**: ~2-10초
- **LLaVA Stage 2**: ~10-30초
- **OCR 평가**: ~5-20초
- **가독성 평가**: ~1-3초
- **IoU 평가**: ~1-3초

**총 예상 시간**: 약 35-120초 (약 1-2분)

### 타임아웃 설정

- 파이프라인 트리거: 600초 (10분)
- 각 API 엔드포인트: 단계별로 다름

---

## 🔐 보안 및 검증

### 공통 검증 사항

1. **Job ID 검증**: UUID 형식 확인
2. **Tenant ID 검증**: Job의 tenant_id와 요청의 tenant_id 일치 확인
3. **Job 상태 검증**: 이전 단계 완료 여부 확인
4. **데이터 존재 확인**: 필요한 데이터(이미지, 제안 등) 존재 확인

---

## 📝 로깅

### 로그 레벨

- **INFO**: 정상 실행 로그
- **WARNING**: 경고 (예: overlay_id를 찾을 수 없음)
- **ERROR**: 오류 발생
- **DEBUG**: 디버깅 정보

### 주요 로그 메시지

- `[TRIGGER] 파이프라인 단계 트리거`: 다음 단계 트리거 시작
- `Job 상태 업데이트`: Job 상태 변경
- `파이프라인 단계 실행 성공/실패`: API 호출 결과

---

## 🧪 테스트

### 테스트 스크립트

- `test/test_pipeline_full.py`: 전체 파이프라인 테스트
- `test/test_listener_team.py`: 리스너 및 트리거 테스트
- `test/test_quantitative_eval.py`: 정량 평가 테스트

### 테스트 실행

```bash
# 전체 파이프라인 테스트
docker exec feedlyai-work-yh python3 test/test_pipeline_full.py

# 특정 단계만 테스트
docker exec feedlyai-work-yh python3 test/test_pipeline_full.py --skip-llava --skip-yolo
```

---

## 🔄 파이프라인 확장

### 새로운 단계 추가 방법

1. **API 엔드포인트 구현**
   - Job 상태 업데이트 로직 포함
   - 시작: `current_step='{step_name}'`, `status='running'`
   - 완료: `status='done'`

2. **파이프라인 트리거에 추가**
   ```python
   ('{previous_step}', 'done'): {
       'next_step': '{new_step}',
       'api_endpoint': '/api/yh/{new_step}',
       'needs_overlay_id': False  # 또는 True
   }
   ```

3. **PostgreSQL 트리거 확인**
   - `jobs` 테이블 업데이트 시 자동으로 NOTIFY 발행

---

## 📚 관련 문서

- `DOCS_JOB_STATE_LISTENER.md`: Job State Listener 사용 가이드
- `IMPLEMENTATION_PLAN_LISTEN_NOTIFY.md`: LISTEN/NOTIFY 구현 계획
- `ANALYSIS_JOB_STATE_DETECTION.md`: Job 상태 감지 분석

---

## ❓ FAQ

**Q: 파이프라인이 중간에 실패하면 어떻게 되나요?**  
A: 실패한 단계에서 `status='failed'`로 업데이트되고, 파이프라인이 중단됩니다. 수동으로 재시작하거나 오류를 수정한 후 다시 시작해야 합니다.

**Q: 특정 단계만 수동으로 실행할 수 있나요?**  
A: 네, 각 API 엔드포인트를 직접 호출할 수 있습니다. 단, 이전 단계가 완료되어 있어야 합니다.

**Q: 여러 Job을 동시에 실행할 수 있나요?**  
A: 네, 각 Job은 독립적으로 실행되며, 여러 Job을 동시에 처리할 수 있습니다.

**Q: overlay_id는 어떻게 자동으로 조회되나요?**  
A: `_get_overlay_id_from_job()` 함수가 job → job_inputs → planner_proposals → overlay_layouts 경로로 최신 overlay_id를 조회합니다.

**Q: 개발 환경에서 파이프라인이 중간에 멈추는 이유는?**  
A: FastAPI WatchFiles 자동 리로드로 인해 리스너가 재시작되면서 NOTIFY 이벤트를 놓칠 수 있습니다. 프로덕션 환경에서는 자동 리로드가 없어 이 문제가 발생하지 않습니다.

**Q: 애플리케이션 재시작 시 실행 중인 작업은 어떻게 되나요?**  
A: 리스너가 종료될 때 실행 중인 모든 태스크가 완료될 때까지 최대 30초 대기합니다. 이를 통해 작업 손실을 최소화합니다.

---

## 📞 문의

문제가 발생하거나 질문이 있으면 팀 채널에 문의하세요.

---

**최종 업데이트**: 2025-11-28  
**문서 버전**: 1.1.0

## 🔄 변경 이력

### v1.1.0 (2025-11-28)
- 비동기 태스크 관리 개선 사항 추가
- 개발 환경 vs 프로덕션 환경 차이점 명시
- 리스너 및 트리거 에러 처리 섹션 추가
- FAQ에 개발 환경 관련 질문 추가

### v1.0.0 (2025-11-28)
- 초기 문서 작성
- 전체 파이프라인 흐름 및 단계별 상세 정보

## 🔄 변경 이력

### v1.1.0 (2025-11-28)
- 비동기 태스크 관리 개선 사항 추가
- 개발 환경 vs 프로덕션 환경 차이점 명시
- 리스너 및 트리거 에러 처리 섹션 추가
- FAQ에 개발 환경 관련 질문 추가

### v1.0.0 (2025-11-28)
- 초기 문서 작성
- 전체 파이프라인 흐름 및 단계별 상세 정보


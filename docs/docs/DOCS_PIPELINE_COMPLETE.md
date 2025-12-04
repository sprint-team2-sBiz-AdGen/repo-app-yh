# 전체 파이프라인 완전 가이드

## 📋 개요

이 문서는 FeedlyAI 광고 생성 파이프라인의 전체 흐름, 각 단계별 상세 정보, 트리거 메커니즘, 결과물 관리 등을 종합적으로 정리한 문서입니다.

**작성일**: 2025-12-01  
**버전**: 2.0.0  
**작성자**: LEEYH205  
**최종 업데이트**: 2025-12-01

---

## 🎯 파이프라인 개요

### 전체 구조

```
[전 단계: JS 파트(텍스트) + YE 파트(이미지 생성)]
  ↓ (모두 완료되어야 YH 파트 시작)
[YH 파트 파이프라인 시작]
  ↓
[Variant별 처리 단계] (일반적으로 3개 variants)
  - vlm_analyze → yolo_detect → planner → overlay → vlm_judge → ocr_eval → readability_eval → iou_eval
  ↓
[Job 레벨 처리 단계]
  - ad_copy_gen_kor (Eng→Kor 변환)
  - instagram_feed_gen (피드 생성)
  ↓
[완료]
```

### 파이프라인 단계 총 개수

- **Variant별 실행 단계**: 8개 (vlm_analyze ~ iou_eval)
- **Job 레벨 실행 단계**: 2개 (ad_copy_gen_kor, instagram_feed_gen)
- **총 단계**: 10개

---

## 1️⃣ 전 단계: JS 파트 + YE 파트 완료

### 1.1 전 단계 완료 조건

**⚠️ 중요**: YH 파트 파이프라인이 시작되려면 **JS 파트(텍스트 생성)와 YE 파트(이미지 생성)가 모두 완료**되어야 합니다.

#### JS 파트 완료 조건
- ✅ `txt_ad_copy_generations` 테이블에 다음 레코드들이 `status='done'`으로 존재:
  - `generation_stage='kor_to_eng'`: 한국어 → 영어 변환 완료
  - `generation_stage='ad_copy_eng'`: 영어 광고문구 생성 완료

#### YE 파트 완료 조건
- ✅ `jobs_variants` 테이블에 모든 variants가 `status='done'`, `current_step='img_gen'` 상태
- ✅ 각 variant에 대해 `img_asset_id`가 설정되어 있음 (이미지 생성 완료)

#### YH 파트 시작 조건
- ✅ **JS 파트 완료** + **YE 파트 완료** 모두 만족 시
- ✅ `jobs_variants` 상태가 `img_gen (done)`으로 변경되면 자동으로 `vlm_analyze` 단계 트리거

---

## 2️⃣ YH 파트 파이프라인 단계

### 2.1 Variant별 실행 단계 (8단계)

각 variant는 독립적으로 다음 단계들을 순차적으로 실행합니다.

#### 단계 1: vlm_analyze (LLaVA Stage 1)
- **API**: `/api/yh/llava/stage1/validate`
- **목적**: 이미지와 광고문구의 적합성 검증
- **입력**: 
  - `job_variants_id` (필수)
  - `job_id` (필수)
  - `tenant_id` (필수)
  - `asset_url` (Optional, `jobs_variants.img_asset_id`에서 조회)
  - `ad_copy_text` (Optional, `txt_ad_copy_generations.ad_copy_eng`에서 조회)
- **출력**: 
  - `vlm_traces` 테이블에 분석 결과 저장
  - `jobs_variants.status='done'`, `jobs_variants.current_step='vlm_analyze'` 업데이트
- **트리거**: `img_gen (done)` → 자동 실행

#### 단계 2: yolo_detect
- **API**: `/api/yh/yolo/detect`
- **목적**: 음식 객체 감지 (바운딩 박스)
- **입력**: `job_variants_id`, `job_id`, `tenant_id`
- **출력**: 
  - `detections` 테이블에 바운딩 박스 저장
  - `yolo_runs` 테이블에 실행 결과 저장
  - `jobs_variants.status='done'`, `jobs_variants.current_step='yolo_detect'` 업데이트
- **트리거**: `vlm_analyze (done)` → 자동 실행

#### 단계 3: planner
- **API**: `/api/yh/planner`
- **목적**: 텍스트 오버레이 위치 제안
- **입력**: `job_variants_id`, `job_id`, `tenant_id`
- **출력**: 
  - `planner_proposals` 테이블에 위치 제안 저장
  - `jobs_variants.status='done'`, `jobs_variants.current_step='planner'` 업데이트
- **트리거**: `yolo_detect (done)` → 자동 실행

#### 단계 4: overlay
- **API**: `/api/yh/overlay`
- **목적**: 텍스트를 이미지에 오버레이
- **입력**: 
  - `job_variants_id`, `job_id`, `tenant_id` (필수)
  - `text` (필수, `txt_ad_copy_generations.ad_copy_eng`에서 조회)
  - `proposal_id` (Optional, `planner_proposals`에서 최신 제안 조회)
  - `x_align`, `y_align` (Optional, 기본값: 'center', 'top')
- **출력**: 
  - `overlay_layouts` 테이블에 오버레이 레이아웃 저장
  - `image_assets` 테이블에 최종 오버레이 이미지 저장 (`image_type='overlaid'`)
  - `jobs_variants.overlaid_img_asset_id` 업데이트
  - `jobs_variants.status='done'`, `jobs_variants.current_step='overlay'` 업데이트
- **트리거**: `planner (done)` → 자동 실행
- **특징**: `needs_text_and_proposal=True`로 설정되어 있어 텍스트와 proposal_id가 자동으로 조회됨

#### 단계 5: vlm_judge (LLaVA Stage 2)
- **API**: `/api/yh/llava/stage2/judge`
- **목적**: 최종 광고 시각 결과물 판단
- **입력**: 
  - `job_variants_id`, `job_id`, `tenant_id` (필수)
  - `overlay_id` (Optional, `overlay_layouts`에서 조회)
  - `render_asset_url` (Optional, `jobs_variants.overlaid_img_asset_id`에서 조회)
- **출력**: 
  - `vlm_traces` 테이블에 판단 결과 저장
  - `jobs_variants.status='done'`, `jobs_variants.current_step='vlm_judge'` 업데이트
- **트리거**: `overlay (done)` → 자동 실행
- **특징**: `needs_overlay_id=True`로 설정되어 있어 overlay_id가 자동으로 조회됨

#### 단계 6: ocr_eval
- **API**: `/api/yh/ocr/evaluate`
- **목적**: OCR 정확도 평가
- **입력**: 
  - `job_variants_id`, `job_id`, `tenant_id` (필수)
  - `overlay_id` (필수, `overlay_layouts`에서 조회)
- **출력**: 
  - `evaluations` 테이블에 OCR 평가 결과 저장 (`evaluation_type='ocr'`)
  - `jobs_variants.status='done'`, `jobs_variants.current_step='ocr_eval'` 업데이트
- **트리거**: `vlm_judge (done)` → 자동 실행
- **특징**: `needs_overlay_id=True`로 설정되어 있어 overlay_id가 자동으로 조회됨

#### 단계 7: readability_eval
- **API**: `/api/yh/readability/evaluate`
- **목적**: 텍스트 가독성 평가
- **입력**: 
  - `job_variants_id`, `job_id`, `tenant_id` (필수)
  - `overlay_id` (필수, `overlay_layouts`에서 조회)
- **출력**: 
  - `evaluations` 테이블에 가독성 평가 결과 저장 (`evaluation_type='readability'`)
  - `jobs_variants.status='done'`, `jobs_variants.current_step='readability_eval'` 업데이트
- **트리거**: `ocr_eval (done)` → 자동 실행
- **특징**: `needs_overlay_id=True`로 설정되어 있어 overlay_id가 자동으로 조회됨

#### 단계 8: iou_eval
- **API**: `/api/yh/iou/evaluate`
- **목적**: 텍스트 영역과 음식 바운딩 박스 겹침 확인 (IoU 계산)
- **입력**: 
  - `job_variants_id`, `job_id`, `tenant_id` (필수)
  - `overlay_id` (필수, `overlay_layouts`에서 조회)
- **출력**: 
  - `evaluations` 테이블에 IoU 평가 결과 저장 (`evaluation_type='iou'`)
  - `jobs_variants.status='done'`, `jobs_variants.current_step='iou_eval'` 업데이트
- **트리거**: `readability_eval (done)` → 자동 실행
- **특징**: 
  - `needs_overlay_id=True`로 설정되어 있어 overlay_id가 자동으로 조회됨
  - 모든 variants가 `iou_eval (done)` 완료 시 Job 레벨 단계로 진행

### 2.2 Job 레벨 실행 단계 (2단계)

**⚠️ 중요**: 이 단계들은 **Job 레벨**에서 실행되며, **variant별이 아닌 Job당 1개씩** 생성됩니다.

#### 단계 9: ad_copy_gen_kor (Eng→Kor 변환)
- **API**: `/api/yh/gpt/eng-to-kor`
- **목적**: 영어 광고문구를 한글로 변환
- **입력**: 
  - `job_id` (필수)
  - `tenant_id` (필수)
- **데이터 조회**:
  - `txt_ad_copy_generations` 테이블에서 `generation_stage='ad_copy_eng'` 또는 `generation_stage='refined_ad_copy'`의 `ad_copy_eng` 또는 `refined_ad_copy_eng` 조회
- **출력**: 
  - `llm_traces` 테이블에 GPT API 호출 Trace 저장
  - `txt_ad_copy_generations` 테이블에 한글 광고문구 저장 (`generation_stage='eng_to_kor'`, `ad_copy_kor` 필드)
  - `jobs.status='done'`, `jobs.current_step='ad_copy_gen_kor'` 업데이트
- **트리거**: 모든 variants가 `iou_eval (done)` 완료 시 → 자동 실행
- **특징**: 
  - `is_job_level=True`로 설정되어 있어 Job 레벨 트리거에서만 실행됨
  - `job_variants_id` 불필요

#### 단계 10: instagram_feed_gen (피드 생성)
- **API**: `/api/yh/instagram/feed`
- **목적**: 인스타그램 피드글 생성
- **입력**: 
  - `job_id` (필수)
  - `tenant_id` (필수)
- **데이터 조회**:
  - `txt_ad_copy_generations` 테이블에서 `ad_copy_kor` 조회
  - `txt_ad_copy_generations` 테이블에서 `refined_ad_copy_eng` 조회
  - `job_inputs` 테이블에서 `tone_style`, `product_description` 조회
  - `stores` 테이블에서 스토어 정보 조회 (`jobs.store_id` 사용)
- **출력**: 
  - `llm_traces` 테이블에 GPT API 호출 Trace 저장
  - `instagram_feeds` 테이블에 피드글 저장 (피드글, 해시태그 포함)
  - `jobs.status='done'`, `jobs.current_step='instagram_feed_gen'` 업데이트
- **트리거**: `ad_copy_gen_kor (done)` → 자동 실행
- **특징**: 
  - `is_job_level=True`로 설정되어 있어 Job 레벨 트리거에서만 실행됨
  - `job_variants_id` 불필요
  - Job당 1개의 피드글만 생성됨

---

## 3️⃣ 트리거 메커니즘

### 3.1 PostgreSQL LISTEN/NOTIFY 기반 이벤트 드리븐 아키텍처

#### 3.1.1 트리거 발행
- **PostgreSQL 트리거**: `jobs` 및 `jobs_variants` 테이블의 상태 변경 시 `pg_notify` 이벤트 발행
  - `job_state_changed`: Job 상태 변경 시
  - `job_variant_state_changed`: Variant 상태 변경 시
- **트리거 파일**: `db/init/03_job_variants_state_notify_trigger.sql`

#### 3.1.2 이벤트 수신
- **Python 리스너**: `services/job_state_listener.py`
  - `asyncpg`를 사용하여 PostgreSQL `LISTEN`으로 이벤트 수신
  - 비동기 태스크로 처리하여 성능 최적화
- **트리거 함수**: `services/pipeline_trigger.py`
  - `trigger_next_pipeline_stage()`: Job 레벨 단계 트리거
  - `trigger_next_pipeline_stage_for_variant()`: Variant 레벨 단계 트리거

#### 3.1.3 자동 트리거 로직
1. Variant 상태 변경 감지 (`job_variant_state_changed`)
2. `_process_job_variant_state_change()` 호출
3. `trigger_next_pipeline_stage_for_variant()` 실행
4. `PIPELINE_STAGES`에서 다음 단계 정보 조회
5. 다음 단계 API 자동 호출

### 3.2 Job 레벨 vs Variant 레벨 구분

#### Variant 레벨 단계 (`is_job_level=False` 또는 없음)
- 각 variant별로 독립적으로 실행
- `job_variants_id` 필수 파라미터
- 예: vlm_analyze, yolo_detect, planner, overlay, vlm_judge, ocr_eval, readability_eval, iou_eval

#### Job 레벨 단계 (`is_job_level=True`)
- Job당 1번만 실행
- `job_id`만 필요 (job_variants_id 불필요)
- 예: ad_copy_gen_kor, instagram_feed_gen

**자세한 내용**: `DOCS_JOB_VARIANT_LEVEL_EXPLANATION.md` 참고

### 3.3 중복 실행 방지

- Job/Variant 상태 재확인으로 중복 실행 방지
- 여러 워커 인스턴스가 동시에 실행되어도 안전
- 상태가 이미 변경된 경우 스킵

---

## 4️⃣ 결과물 관리

### 4.1 이미지 결과물

#### 원본 이미지
- **테이블**: `image_assets`
- **컬럼**: `image_type='generated'`
- **경로**: `image_url` (예: `/assets/yh/tenants/{tenant_id}/...`)
- **절대 경로**: `/opt/feedlyai/assets/` + `image_url`에서 `/assets/` 제거

#### 최종 오버레이 이미지
- **테이블**: `image_assets`
- **컬럼**: `image_type='overlaid'`
- **참조**: `jobs_variants.overlaid_img_asset_id`
- **경로**: `image_url` (예: `/assets/yh/tenants/{tenant_id}/final/...`)
- **절대 경로**: `/opt/feedlyai/assets/` + `image_url`에서 `/assets/` 제거
- **Fallback**: `overlay_layouts.layout->'render'->>'url'` (구버전 호환)

### 4.2 텍스트 결과물

#### 광고 카피 문구
- **테이블**: `txt_ad_copy_generations`
- **단계별 필드**:
  - `generation_stage='kor_to_eng'`: `ad_copy_eng` (영어 변환)
  - `generation_stage='ad_copy_eng'`: `ad_copy_eng` (영어 광고문구)
  - `generation_stage='refined_ad_copy'`: `refined_ad_copy_eng` (조정된 영어 광고문구, 선택적)
  - `generation_stage='eng_to_kor'`: `ad_copy_kor` (한글 광고문구)

#### 인스타그램 피드
- **테이블**: `instagram_feeds`
- **필드**:
  - `ad_copy_kor`: 한글 광고문구
  - `instagram_ad_copy`: 생성된 피드글
  - `hashtags`: 생성된 해시태그
  - `llm_trace_id`: GPT API 호출 Trace 참조

### 4.3 평가 결과물

#### VLM Traces
- **테이블**: `vlm_traces`
- **용도**: LLaVA Stage 1, Stage 2 분석 결과 저장

#### Evaluations
- **테이블**: `evaluations`
- **타입별 필드**:
  - `evaluation_type='ocr'`: OCR 평가 점수
  - `evaluation_type='readability'`: 가독성 평가 점수
  - `evaluation_type='iou'`: IoU 평가 점수 및 겹침 감지 여부

### 4.4 결과물 조회 방법

#### 테스트 스크립트 사용
```bash
python test/test_pipeline_with_text_generation.py --wait
```

#### 상세 결과물 출력 함수
- **함수**: `print_detailed_results(db, job_id)`
- **출력 내용**:
  - Job 정보
  - 원본 이미지 절대 경로
  - Variants별 최종 오버레이 이미지 절대 경로
  - 평가 점수 (OCR, Readability, IoU)
  - 광고 카피 문구 (kor_to_eng, ad_copy_eng, eng_to_kor)
  - 인스타그램 피드 (피드글, 해시태그)

---

## 5️⃣ 에러 처리 및 재시도

### 5.1 Variant 레벨 재시도

- **최대 재시도 횟수**: `MAX_VARIANT_RETRY_COUNT = 3`
- **재시도 조건**: 
  - Variant가 특정 단계에서 `failed` 상태
  - `retry_count < MAX_VARIANT_RETRY_COUNT`
- **재시도 로직**: `services/job_state_listener.py`의 `_recover_stuck_variants()` 함수

### 5.2 Job 레벨 재시도

- **최대 재시도 횟수**: `MAX_JOB_RETRY_COUNT = 3`
- **재시도 조건**: 
  - 모든 variants가 같은 단계에서 `failed` 상태
  - `retry_count < MAX_JOB_RETRY_COUNT`
- **재시도 로직**: `services/job_state_listener.py`의 `_process_job_state_change()` 함수

### 5.3 수동 복구

- **주기적 복구**: 5분마다 멈춘 variant 감지 및 재시도
- **복구 로직**: `services/job_state_listener.py`의 `_periodic_recovery_check()` 함수

---

## 6️⃣ 데이터베이스 스키마

### 6.1 주요 테이블

#### jobs
- `job_id`: UUID (PK)
- `tenant_id`: String
- `store_id`: UUID (FK → stores)
- `status`: String ('queued', 'running', 'done', 'failed')
- `current_step`: String
- `retry_count`: Integer (기본값: 0)

#### jobs_variants
- `job_variants_id`: UUID (PK)
- `job_id`: UUID (FK → jobs)
- `img_asset_id`: UUID (FK → image_assets)
- `overlaid_img_asset_id`: UUID (FK → image_assets, 최종 오버레이 이미지)
- `creation_order`: Integer
- `status`: String ('queued', 'running', 'done', 'failed')
- `current_step`: String
- `retry_count`: Integer (기본값: 0)

#### txt_ad_copy_generations
- `ad_copy_gen_id`: UUID (PK)
- `job_id`: UUID (FK → jobs)
- `llm_trace_id`: UUID (FK → llm_traces, Optional)
- `generation_stage`: String ('kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor')
- `ad_copy_kor`: Text (한글 광고문구)
- `ad_copy_eng`: Text (영어 광고문구)
- `refined_ad_copy_eng`: Text (조정된 영어 광고문구, Optional)
- `status`: String ('queued', 'running', 'done', 'failed')

#### instagram_feeds
- `instagram_feed_id`: UUID (PK)
- `job_id`: UUID (FK → jobs)
- `llm_trace_id`: UUID (FK → llm_traces, Optional)
- `ad_copy_kor`: Text (한글 광고문구)
- `instagram_ad_copy`: Text (생성된 피드글)
- `hashtags`: Text (해시태그)

#### image_assets
- `image_asset_id`: UUID (PK)
- `image_type`: String ('generated', 'overlaid')
- `image_url`: String (예: `/assets/yh/tenants/...`)
- `width`, `height`: Integer

#### evaluations
- `evaluation_id`: UUID (PK)
- `job_id`: UUID (FK → jobs)
- `overlay_id`: UUID (FK → overlay_layouts)
- `evaluation_type`: String ('ocr', 'readability', 'iou')
- `metrics`: JSONB (평가 결과)

### 6.2 인덱스

- `idx_jobs_variants_status`: `jobs_variants(status)`
- `idx_jobs_variants_current_step`: `jobs_variants(current_step)`
- `idx_jobs_variants_job_id_status`: `jobs_variants(job_id, status)`
- `idx_txt_ad_copy_generations_job_id`: `txt_ad_copy_generations(job_id)`
- `idx_instagram_feeds_job_id`: `instagram_feeds(job_id)`

---

## 7️⃣ 테스트

### 7.1 테스트 스크립트

#### 파일: `test/test_pipeline_with_text_generation.py`

#### 사용법
```bash
# 기본 실행 (Job 생성만)
python test/test_pipeline_with_text_generation.py

# 파이프라인 완료까지 대기
python test/test_pipeline_with_text_generation.py --wait

# 최대 대기 시간 지정 (분)
python test/test_pipeline_with_text_generation.py --wait --max-wait 30
```

#### 주요 함수
- `create_test_job_with_js_data()`: 테스트 Job 생성 및 JS 파트 데이터 준비
- `verify_pre_stage_completion()`: 전 단계 완료 조건 검증
- `trigger_pipeline_start()`: 파이프라인 시작 트리거
- `monitor_pipeline_progress()`: 파이프라인 진행 상황 모니터링
- `print_detailed_results()`: 상세 결과물 출력

### 7.2 예상 소요 시간

- **LLaVA 모델 로딩**: 약 1-2분 (GPU)
- **Variant별 처리**: 약 5-7분 (3개 variants)
- **Job 레벨 처리**: 약 10-20초
- **총 소요 시간**: 약 7-10분

---

## 8️⃣ 트러블슈팅

### 8.1 파이프라인이 진행되지 않는 경우

#### 확인 사항
1. **전 단계 완료 조건 확인**
   - JS 파트: `txt_ad_copy_generations`에 `kor_to_eng`, `ad_copy_eng` 레코드 존재
   - YE 파트: 모든 variants가 `img_gen (done)` 상태
2. **리스너 실행 확인**
   - `services/job_state_listener.py`가 실행 중인지 확인
   - Docker 로그에서 `[LISTENER]` 메시지 확인
3. **트리거 발행 확인**
   - PostgreSQL 트리거가 정상 작동하는지 확인
   - `db/init/03_job_variants_state_notify_trigger.sql` 확인

#### 해결 방법
- 수동으로 variant 상태를 업데이트하여 트리거 발동
- 리스너 재시작
- 수동 복구 로직 실행 대기 (5분 주기)

### 8.2 422 에러 (Unprocessable Entity)

#### 원인
- Variant 레벨 단계인데 Job 레벨 트리거에서 호출됨
- `job_variants_id` 파라미터 누락

#### 해결
- `services/pipeline_trigger.py`에서 `is_job_level` 체크 로직 확인
- Variant 레벨 단계는 `trigger_next_pipeline_stage_for_variant()`에서만 실행

### 8.3 variants가 `running` 상태로 멈춘 경우

#### 원인
- API 호출 실패
- 예외 발생으로 상태 업데이트 실패

#### 해결
- 수동 복구 로직이 자동으로 감지 및 재시도 (5분 주기)
- 또는 수동으로 상태를 `done`으로 업데이트

---

## 9️⃣ 참고 문서

- `DOCS_PIPELINE_COMPLETE_FLOW.md`: 파이프라인 흐름 상세 설명
- `DOCS_JOB_VARIANT_LEVEL_EXPLANATION.md`: Job 레벨 vs Variant 레벨 설명
- `DOCS_YH_PART_IMPLEMENTATION.md`: YH 파트 구현 가이드
- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `scripts/DOCS_PIPELINE_AUTO_TRIGGER.md`: 자동 트리거 메커니즘 상세 설명

---

## 🔟 변경 이력

### v2.0.0 (2025-12-01)
- 절대 경로 표시 수정 (`/opt/feedlyai/assets/`)
- 파이프라인 완전 가이드 작성
- 결과물 관리 섹션 추가
- 트러블슈팅 섹션 추가

### v1.0.0 (2025-12-01)
- 초기 문서 작성

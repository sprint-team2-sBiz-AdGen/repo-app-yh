# 전체 파이프라인 흐름 정리 문서

## 📋 개요

이 문서는 `test_pipeline_with_text_generation.py`를 기반으로 전체 파이프라인의 흐름을 정리한 문서입니다.

**작성일**: 2025-12-01  
**버전**: 1.0.0  
**작성자**: LEEYH205

---

## 🔄 전체 파이프라인 구조

```
[전 단계: JS 파트(텍스트) + YE 파트(이미지 생성)]
  ↓ (모두 완료되어야 YH 파트 시작)
[YH 파트 파이프라인 시작]
  ↓
[YH 파트 파이프라인 진행]
  - Variants별 처리 (일반적으로 3개)
  ↓
[마무리: 텍스트 생성 및 피드 생성]
  - Job 레벨 처리 (피드글 1개)
```

---

## 1️⃣ 전 단계: JS 파트(텍스트) + YE 파트(이미지 생성) 완료

### 1.1 전 단계 완료 조건
**⚠️ 중요**: YH 파트 파이프라인이 시작되려면 **JS 파트(텍스트 생성)와 YE 파트(이미지 생성)가 모두 완료**되어야 합니다.

#### 1.1.1 JS 파트 완료 조건
- ✅ `txt_ad_copy_generations` 테이블에 다음 레코드들이 `status='done'`으로 존재:
  - `generation_stage='kor_to_eng'`: 한국어 → 영어 변환 완료
  - `generation_stage='ad_copy_eng'`: 영어 광고문구 생성 완료

#### 1.1.2 YE 파트 완료 조건
- ✅ `jobs_variants` 테이블에 모든 variants가 `status='done'`, `current_step='img_gen'` 상태
- ✅ 각 variant에 대해 `img_asset_id`가 설정되어 있음 (이미지 생성 완료)

#### 1.1.3 YH 파트 시작 조건
- ✅ **JS 파트 완료** + **YE 파트 완료** 모두 만족 시
- ✅ `jobs_variants` 상태가 `img_gen (done)`으로 변경되면 자동으로 `vlm_analyze` 단계 트리거

### 1.2 데이터 생성 위치
- **함수**: `create_test_job_with_js_data()` (라인 36-261)
- **목적**: YH 파트 파이프라인 시작 전 필요한 모든 데이터 준비 (JS + YE 파트 완료 상태 시뮬레이션)

### 1.3 생성되는 데이터

#### 1.2.1 기본 테이블 데이터
```python
# 1. tenants 테이블
INSERT INTO tenants (tenant_id, display_name, ...)

# 2. image_assets 테이블
INSERT INTO image_assets (
    image_asset_id, image_type='generated', image_url, ...
)

# 3. jobs 테이블
INSERT INTO jobs (
    job_id, tenant_id, store_id,
    status='done', current_step='img_gen'  # ⚠️ img_gen 완료 상태로 시작
)

# 4. job_inputs 테이블
INSERT INTO job_inputs (
    job_id, img_asset_id, tone_style_id, desc_kor, ...
)
```

#### 1.2.2 JS 파트 데이터 (임의 생성)
```python
# 5. txt_ad_copy_generations 테이블 - kor_to_eng
INSERT INTO txt_ad_copy_generations (
    ad_copy_gen_id, job_id,
    generation_stage='kor_to_eng',
    ad_copy_eng='Delicious Korean Army Stew...',  # 영어 변환 결과
    status='done'
)

# 6. txt_ad_copy_generations 테이블 - ad_copy_eng
INSERT INTO txt_ad_copy_generations (
    ad_copy_gen_id, job_id,
    generation_stage='ad_copy_eng',
    ad_copy_eng='Experience the perfect harmony...',  # 영어 광고문구
    status='done'
)
```

#### 1.3.3 YE 파트: 이미지 생성 완료 (Variants)
```python
# 7. jobs_variants 테이블 (이미지 처리용)
# ⚠️ 여러 개의 variants 생성 가능 (일반적으로 3개)
INSERT INTO jobs_variants (
    job_variants_id, job_id, img_asset_id, creation_order,
    status='done', current_step='img_gen'  # ⚠️ img_gen 완료 상태로 시작
)
# 예: variants_count=3이면 3개의 variants 생성
```

**Variants 개수**:
- 일반적으로 **3개**의 variants 생성 (테스트에서는 `--variants` 파라미터로 조절 가능)
- 각 variant는 독립적으로 이미지 처리 파이프라인 진행

### 1.4 전 단계 완료 상태 요약
- ✅ **JS 파트**: `txt_ad_copy_generations`에 `kor_to_eng`, `ad_copy_eng` 레코드 존재 (`status='done'`)
- ✅ **YE 파트**: `jobs_variants.status = 'done'`, `jobs_variants.current_step = 'img_gen'` (모든 variants)
- ✅ **Job 상태**: `jobs.status = 'done'`, `jobs.current_step = 'img_gen'`
- ✅ **YH 파트 시작 준비 완료**: 위 조건들이 모두 만족되면 YH 파트 파이프라인 시작 가능

---

## 2️⃣ 트리거 발동: YH 파트 파이프라인 시작

### 2.1 트리거 함수
- **함수**: `trigger_pipeline_start()` (라인 495-532)
- **목적**: PostgreSQL 트리거를 발동하여 자동 파이프라인 시작

### 2.2 트리거 메커니즘

#### 2.2.1 상태 업데이트
```python
# 각 variant에 대해:
# 1. running 상태로 변경
UPDATE jobs_variants 
SET status = 'running', current_step = 'img_gen', updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = :variant_id

# 2. done 상태로 변경 (트리거 발동)
UPDATE jobs_variants 
SET status = 'done', current_step = 'img_gen', updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = :variant_id
```

#### 2.2.2 PostgreSQL 트리거 자동 감지
- **트리거 파일**: `db/init/03_job_variants_state_notify_trigger.sql`
- **트리거 함수**: `notify_job_variant_state_change()`
- **동작**: `jobs_variants` 테이블의 `current_step` 또는 `status` 변경 시 자동으로 `pg_notify()` 실행
- **NOTIFY 채널**: `'job_variant_state_changed'`
- **NOTIFY 페이로드**: JSON 형태로 `job_variants_id`, `job_id`, `current_step`, `status`, `img_asset_id`, `tenant_id` 포함

#### 2.2.3 Python 리스너 수신
- **리스너**: `services/job_state_listener.py`
- **동작**: PostgreSQL `LISTEN`으로 `job_variant_state_changed` 이벤트 수신
- **처리**: 이벤트 수신 시 `_process_job_variant_state_change()` 함수 호출

#### 2.2.4 다음 단계 자동 트리거
- **트리거 서비스**: `services/pipeline_trigger.py`
- **조건 확인**: `current_step='img_gen'`, `status='done'`인 경우
- **다음 단계**: `vlm_analyze`
- **API 호출**: `POST /api/yh/llava/stage1/validate`

---

## 3️⃣ YH 파트 파이프라인 진행

### 3.1 파이프라인 단계 순서

```
img_gen (done) [전 단계에서 완료]
  ↓ [자동 트리거]
vlm_analyze (LLaVA Stage 1) [variant별 실행]
  ↓ [자동 트리거]
yolo_detect [variant별 실행]
  ↓ [자동 트리거]
planner [variant별 실행]
  ↓ [자동 트리거]
overlay [variant별 실행]
  ↓ [자동 트리거]
vlm_judge (LLaVA Stage 2) [variant별 실행]
  ↓ [자동 트리거]
ocr_eval [variant별 실행]
  ↓ [자동 트리거]
readability_eval [variant별 실행]
  ↓ [자동 트리거]
iou_eval [variant별 실행]
  ↓ [모든 variants 완료 시 자동 트리거]
ad_copy_gen_kor (Eng→Kor 변환) [Job 레벨 실행]
  ↓ [자동 트리거]
instagram_feed_gen (피드 생성) [Job 레벨 실행]
  ↓
완료
```

### 3.2 각 단계별 상세 정보

#### 3.2.1 Variant별 실행 단계 (vlm_analyze ~ iou_eval)

**트리거 조건** (`services/pipeline_trigger.py`):
```python
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
    # ... (중간 단계들)
    ('readability_eval', 'done'): {
        'next_step': 'iou_eval',
        'api_endpoint': '/api/yh/iou/evaluate',
        'method': 'POST',
        'needs_overlay_id': True
    },
}
```

**실행 방식**:
1. 각 variant가 독립적으로 실행
2. `job_state_listener.py`가 각 variant의 상태 변화를 감지
3. `current_step='이전단계'`, `status='done'`인 variant에 대해 다음 단계 API 호출
4. API 호출 시 `job_variants_id`를 파라미터로 전달

**상태 업데이트**:
- 각 API 엔드포인트에서:
  1. `jobs_variants.status = 'running'`, `jobs_variants.current_step = '현재단계'` 업데이트
  2. 작업 수행
  3. `jobs_variants.status = 'done'` 업데이트
  4. PostgreSQL 트리거가 자동으로 NOTIFY 발행
  5. 리스너가 다음 단계 트리거

#### 3.2.2 Job 레벨 실행 단계 (ad_copy_gen_kor, instagram_feed_gen)

**⚠️ 중요**: 이 단계들은 **Job 레벨**에서 실행되며, **variant별이 아닌 Job당 1개씩** 생성됩니다.

**트리거 조건**:
```python
PIPELINE_STAGES = {
    ('iou_eval', 'done'): {  # ⚠️ 모든 variants가 iou_eval 완료되어야 함
        'next_step': 'ad_copy_gen_kor',
        'api_endpoint': '/api/yh/gpt/eng-to-kor',
        'method': 'POST',
        'is_job_level': True,  # Job 레벨 단계 (variant별 실행 아님)
        'needs_overlay_id': False
    },
    ('ad_copy_gen_kor', 'done'): {
        'next_step': 'instagram_feed_gen',
        'api_endpoint': '/api/yh/instagram/feed',
        'method': 'POST',
        'is_job_level': True,  # Job 레벨 단계 (variant별 실행 아님)
        'needs_overlay_id': False
    },
}
```

**실행 조건**:
- **ad_copy_gen_kor**: 모든 variants가 `iou_eval (done)` 완료
- **instagram_feed_gen**: `ad_copy_gen_kor (done)` 완료

**실행 방식**:
1. `job_state_listener.py`가 `jobs` 테이블 상태 변화 감지
2. `jobs.current_step='iou_eval'`, `jobs.status='done'`인 경우 `ad_copy_gen_kor` 트리거
3. API 호출 시 `job_id`를 파라미터로 전달 (variant별 실행 아님)

**결과물 개수**:
- **Variants**: 여러 개 (일반적으로 3개) - 각 variant별로 독립적인 이미지 처리 결과
- **피드글**: **1개** - Job당 1개의 인스타그램 피드 생성 (`instagram_feeds` 테이블에 1개 레코드)

**상태 업데이트**:
- 각 API 엔드포인트에서:
  1. `jobs.status = 'running'`, `jobs.current_step = '현재단계'` 업데이트
  2. 작업 수행
  3. `jobs.status = 'done'` 업데이트
  4. PostgreSQL 트리거가 자동으로 NOTIFY 발행
  5. 리스너가 다음 단계 트리거

### 3.3 데이터 흐름

#### 3.3.1 vlm_analyze 단계
- **입력**: `txt_ad_copy_generations.ad_copy_eng` (generation_stage='ad_copy_eng')
- **출력**: `vlm_traces` 테이블에 분석 결과 저장
- **선택적**: 검증 결과에 따라 `refined_ad_copy` 실행 가능

#### 3.3.2 overlay 단계
- **입력**: `txt_ad_copy_generations.ad_copy_eng` 또는 `refined_ad_copy_eng`
- **출력**: `overlay_layouts` 테이블에 오버레이 결과 저장
- **최종 이미지**: `image_assets` 테이블에 `image_type='overlaid'`로 저장, `jobs_variants.overlaid_img_asset_id` 업데이트

#### 3.3.3 ad_copy_gen_kor 단계
- **입력**: `txt_ad_copy_generations.refined_ad_copy_eng` (generation_stage='refined_ad_copy' 또는 'ad_copy_eng')
- **출력**: 
  - `llm_traces` 테이블에 GPT API 호출 기록 저장
  - `txt_ad_copy_generations` 테이블에 `ad_copy_kor` 저장 (generation_stage='eng_to_kor')

#### 3.3.4 instagram_feed_gen 단계
- **입력**:
  - `txt_ad_copy_generations.ad_copy_kor` (generation_stage='eng_to_kor')
  - `txt_ad_copy_generations.refined_ad_copy_eng`
  - `job_inputs.tone_style`, `job_inputs.product_description`
  - `stores` 테이블 (jobs.store_id로 조회)
- **출력**:
  - `llm_traces` 테이블에 GPT API 호출 기록 저장
  - `instagram_feeds` 테이블에 피드 글, 해시태그 저장

---

## 4️⃣ 마무리: 파이프라인 완료

### 4.1 완료 조건
- **최종 단계**: `instagram_feed_gen`
- **완료 상태**: `jobs.status = 'done'`, `jobs.current_step = 'instagram_feed_gen'`

### 4.2 완료 확인 메커니즘

#### 4.2.1 모니터링 함수
- **함수**: `monitor_pipeline_progress()` (라인 396-492)
- **동작**: 30초 간격으로 상태 확인, 완료 시 최종 상태 출력

#### 4.2.2 완료 감지
```python
# 완료 조건 확인
if status == 'done' and current_step == 'instagram_feed_gen':
    print("\n✅ 파이프라인 완료!")
    print_table_status(db, job_id, "최종 상태")
    break
```

### 4.3 최종 결과물

#### 4.3.1 Variants별 결과
- **최종 이미지**: `jobs_variants.overlaid_img_asset_id` → `image_assets` 테이블
- **오버레이 레이아웃**: `overlay_layouts` 테이블
- **평가 결과**: `evaluations` 테이블 (vlm_judge, ocr_eval, readability_eval, iou_eval)

#### 4.3.2 Job 레벨 결과
- **텍스트 생성 결과**: `txt_ad_copy_generations` 테이블
  - `kor_to_eng`: 한국어 → 영어 변환
  - `ad_copy_eng`: 영어 광고문구
  - `refined_ad_copy`: 조정된 영어 광고문구 (선택적)
  - `eng_to_kor`: 영어 → 한국어 변환
- **인스타그램 피드**: `instagram_feeds` 테이블
  - ⚠️ **Job당 1개만 생성** (variants 개수와 무관)
  - `instagram_ad_copy`: 생성된 피드 글
  - `hashtags`: 생성된 해시태그
  - `llm_trace_id`: GPT API 호출 기록 참조
  - `job_id`: 해당 Job과 연결

### 4.4 최종 상태 출력
```python
print_table_status(db, job_id, "최종 상태")
# 출력 내용:
# - jobs 테이블 상태
# - jobs_variants 테이블 상태 (모든 variants)
# - txt_ad_copy_generations 테이블 상태
# - instagram_feeds 테이블 상태
```

---

## 🔧 핵심 메커니즘 요약

### 1. PostgreSQL LISTEN/NOTIFY 기반 이벤트 드리븐 아키텍처
- **트리거**: `jobs_variants` 테이블 변경 시 자동으로 NOTIFY 발행
- **리스너**: Python에서 `LISTEN`으로 이벤트 수신
- **트리거 서비스**: 이벤트 수신 시 다음 단계 API 자동 호출

### 2. 자동 파이프라인 진행
- **Variant별 단계**: 각 variant가 독립적으로 진행
- **Job 레벨 단계**: 모든 variants 완료 후 Job 레벨에서 실행
- **상태 기반 트리거**: `current_step`과 `status` 조합으로 다음 단계 결정

### 3. 데이터 일관성
- **공유 데이터**: `job_id`로 모든 데이터 연결
- **중간 결과 저장**: 각 단계별 결과를 DB에 저장하여 추적 가능
- **Trace 관리**: 모든 LLM API 호출을 `llm_traces` 테이블에 기록

---

## 📝 핵심 요약

### 전 단계 완료 조건
- ✅ **JS 파트(텍스트)**: `txt_ad_copy_generations`에 `kor_to_eng`, `ad_copy_eng` 완료
- ✅ **YE 파트(이미지)**: 모든 `jobs_variants`가 `img_gen (done)` 완료
- ✅ **YH 파트 시작**: 위 두 조건이 모두 만족되어야 자동으로 `vlm_analyze` 트리거

### 결과물 개수
- **Variants**: 일반적으로 **3개** (각 variant별로 독립적인 이미지 처리 결과)
- **피드글**: **1개** (Job당 1개의 인스타그램 피드 생성)

### 파이프라인 진행 방식
- **Variant별 단계** (vlm_analyze ~ iou_eval): 각 variant가 독립적으로 진행
- **Job 레벨 단계** (ad_copy_gen_kor, instagram_feed_gen): 모든 variants 완료 후 Job당 1개씩 생성

---

## 📝 참고 사항

### LLaVA 모델 로딩 시간
- 첫 번째 `vlm_analyze` 호출 시 GPU에 모델 로딩 시간이 소요됨
- 모니터링 시 이 시간을 고려하여 대기 시간 설정 필요

### 트리거 발동 타이밍
- `trigger_pipeline_start()` 함수에서 상태를 `running` → `done`으로 변경하여 트리거 발동
- 실제로는 이미 `done` 상태이지만, 상태 변경을 통해 트리거를 강제로 발동

### 에러 처리
- 각 단계에서 실패 시 `status='failed'`로 업데이트
- `retry_count`를 증가시키고 최대 재시도 횟수 내에서 자동 재시도

---

## 🔗 관련 파일

- **테스트 스크립트**: `test/test_pipeline_with_text_generation.py`
- **트리거 서비스**: `services/pipeline_trigger.py`
- **리스너 서비스**: `services/job_state_listener.py`
- **PostgreSQL 트리거**: `db/init/03_job_variants_state_notify_trigger.sql`
- **API 엔드포인트**: `routers/` 디렉토리 내 각 단계별 라우터


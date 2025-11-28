# Job Variants 기반 파이프라인 구현 문서

## 🎯 핵심 결정 사항 (최종)

### ✅ 최종 결정: 옵션 C (하이브리드) - **구현 완료**

#### 1. Job 상태 관리
- **ye 파트 → yh 파트 시작**: `jobs.current_step = 'vlm_analyze'`, `jobs.status = 'running'` 설정
- **yh 파트 진행 중**: `jobs_variants` 테이블만 업데이트
- **매 단계 완료 시**: 모든 variants가 같은 단계에서 `done`이면 `jobs.current_step = 해당 단계`로 자동 업데이트
- **최종 완료**: 모든 variants가 `iou_eval` 단계에서 `done`이면 `jobs.status = 'done'`, `jobs.current_step = 'iou_eval'` 자동 업데이트

#### 2. 트리거 전략
- **`jobs_variants` 테이블 트리거 사용**
- `job_variant_state_changed` 채널로 NOTIFY 발행
- 매 단계마다 모든 variants 완료 여부 확인하여 `jobs` 테이블 업데이트

#### 3. 하위 호환성
- **`job_variants_id`는 필수 파라미터**
- 모든 API 엔드포인트에서 `job_variants_id` 필수로 검증

#### 4. 실행 방식
- **병렬 실행**: 같은 `job_id`의 여러 variant를 병렬로 처리
- Thread-safe 모델 로딩 구현 (Double-checked locking 패턴)

---

## 📋 구현 완료 사항

### ✅ 완료된 작업
1. **스키마 변경**: `jobs_variants` 테이블에 `status`, `current_step`, `updated_at` 컬럼 추가
2. **트리거 구현**: `jobs_variants` 테이블 트리거 생성 (매 단계마다 `jobs` 테이블 업데이트)
3. **API 엔드포인트 수정**: 모든 8개 엔드포인트에 `job_variants_id` 필수 파라미터 추가
4. **파이프라인 트리거**: `job_variants_id` 기반 파이프라인 트리거 구현
5. **리스너**: `job_variant_state_changed` 채널 리스너 추가
6. **Thread-safe 모델 로딩**: LLaVA 모델 로딩 시 동시 접근 방지 (threading.Lock 사용)

---

## 🗄️ 데이터베이스 구조

### 현재 테이블 구조

#### `jobs` 테이블
```sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY,
    tenant_id VARCHAR(255),
    status TEXT,  -- queued, running, done, failed
    current_step TEXT,  -- 'vlm_analyze', 'vlm_planner', 'vlm_judge', etc.
    ...
);
```

#### `jobs_variants` 테이블 (구현 완료)
```sql
CREATE TABLE jobs_variants (
    job_variants_id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(job_id),
    img_asset_id UUID REFERENCES image_assets(image_asset_id),
    creation_order INTEGER NOT NULL,
    selected BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'queued',  -- queued, running, done, failed
    current_step TEXT DEFAULT 'vlm_analyze',  -- 파이프라인 단계
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스
CREATE INDEX idx_jobs_variants_status ON jobs_variants(status);
CREATE INDEX idx_jobs_variants_current_step ON jobs_variants(current_step);
CREATE INDEX idx_jobs_variants_job_id_status ON jobs_variants(job_id, status);
```

**구현 완료**:
- ✅ `status`, `current_step`, `updated_at` 컬럼 추가
- ✅ 각 variant의 파이프라인 진행 상황 추적 가능

---

## 🔄 파이프라인 흐름 (현재 vs 변경 후)

### 현재 흐름
```
Job ID: job-123
  └─ [파이프라인 1회 실행]
     └─ vlm_analyze → yolo_detect → planner → overlay → vlm_judge → ...
```

### 변경 후 흐름 (목표)
```
Job ID: job-123
  ├─ Variant 1 (job_variants_id: variant-1)
  │  └─ [파이프라인 1회 실행]
  │     └─ vlm_analyze → yolo_detect → planner → overlay → vlm_judge → ...
  │
  ├─ Variant 2 (job_variants_id: variant-2)
  │  └─ [파이프라인 1회 실행]
  │     └─ vlm_analyze → yolo_detect → planner → overlay → vlm_judge → ...
  │
  └─ Variant 3 (job_variants_id: variant-3)
     └─ [파이프라인 1회 실행]
        └─ vlm_analyze → yolo_detect → planner → overlay → vlm_judge → ...
```

---

## 🎯 구현 완료된 해결 방안

### ✅ 선택된 방안: `jobs_variants` 테이블에 상태 컬럼 추가

**구현 완료 사항**:
1. ✅ 스키마 변경: `status`, `current_step`, `updated_at` 컬럼 추가
2. ✅ 트리거 구현: `jobs_variants` 테이블 트리거 생성
3. ✅ 파이프라인 트리거 로직 변경: `job_variants_id` 기준으로 변경
4. ✅ 모든 API 엔드포인트 수정: `job_variants_id` 필수 파라미터 추가

**구현 결과**:
- ✅ 각 variant별로 독립적인 상태 관리
- ✅ variant별로 독립적인 파이프라인 진행 추적
- ✅ 기존 `jobs` 테이블 구조 유지 (다른 파트와 호환성)
- ✅ 병렬 실행 지원 (thread-safe 모델 로딩)

---

## 🔧 구현 완료 사항

### ✅ 1단계: 스키마 변경 (완료)

**파일**: `db/init/01_schema.sql`

```sql
-- jobs_variants 테이블에 상태 컬럼 추가
ALTER TABLE jobs_variants 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'queued',
ADD COLUMN IF NOT EXISTS current_step TEXT DEFAULT 'vlm_analyze',
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_jobs_variants_status ON jobs_variants(status);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_current_step ON jobs_variants(current_step);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_job_id_status ON jobs_variants(job_id, status);
```

### ✅ 2단계: 트리거 구현 (완료)

**파일**: `db/init/03_job_variants_state_notify_trigger.sql`

#### 트리거 1: NOTIFY 발행
- `job_variant_state_changed` 채널로 상태 변화 알림

#### 트리거 2: jobs 테이블 자동 업데이트
- **매 단계마다**: 모든 variants가 같은 단계에서 `done`이면 `jobs.current_step = 해당 단계`로 업데이트
- **최종 완료**: 모든 variants가 `iou_eval` 단계에서 `done`이면 `jobs.status = 'done'`, `jobs.current_step = 'iou_eval'`로 업데이트
- **img_gen 단계 제외**: 파이프라인 시작 전 단계이므로 `jobs` 테이블 업데이트 안 함

### ✅ 3단계: 파이프라인 트리거 로직 변경 (완료)

**파일**: `services/pipeline_trigger.py`

- ✅ `trigger_next_pipeline_stage_for_variant()` 함수 추가
- ✅ `job_variants_id` 기반으로 파이프라인 실행
- ✅ `_get_overlay_id_from_job_variant()`, `_get_text_and_proposal_from_job_variant()` 함수 추가

### ✅ 4단계: API 엔드포인트 변경 (완료)

**파일**: `models.py`, `routers/*.py`

**변경된 엔드포인트 (8개)**:
1. ✅ `llava_stage1.py` - `LLaVaStage1In`에 `job_variants_id` 필수 추가
2. ✅ `yolo.py` - `DetectIn`에 `job_variants_id` 필수 추가
3. ✅ `planner.py` - `PlannerIn`에 `job_variants_id` 필수 추가
4. ✅ `overlay.py` - `OverlayIn`에 `job_variants_id` 필수 추가
5. ✅ `llava_stage2.py` - `JudgeIn`에 `job_variants_id` 필수 추가
6. ✅ `ocr_eval.py` - `OCREvalIn`에 `job_variants_id` 필수 추가
7. ✅ `readability_eval.py` - `ReadabilityEvalIn`에 `job_variants_id` 필수 추가
8. ✅ `iou_eval.py` - `IoUEvalIn`에 `job_variants_id` 필수 추가

**변경 사항**:
- ✅ 모든 Input 모델에 `job_variants_id: str` 필수 필드 추가
- ✅ 이미지 조회: `job_inputs` → `jobs_variants.img_asset_id`
- ✅ 상태 업데이트: `jobs` → `jobs_variants`

### ✅ 5단계: Job 상태 업데이트 로직 변경 (완료)

**변경 사항**:
- ✅ 모든 엔드포인트에서 `jobs_variants` 테이블만 업데이트
- ✅ 각 단계 완료 시 `jobs_variants.status = 'done'`, `jobs_variants.current_step = 해당 단계`
- ✅ 트리거가 자동으로 `jobs` 테이블 업데이트 (매 단계마다)

---

## 📊 파이프라인 단계별 변경 사항

### 각 단계별 필요한 변경

| 단계 | 현재 | 변경 후 |
|------|------|---------|
| **vlm_analyze** | `job_id` 기준 | `job_variants_id` 기준, `jobs_variants.img_asset_id` 사용 |
| **yolo_detect** | `job_id` 기준 | `job_variants_id` 기준, `jobs_variants.img_asset_id` 사용 |
| **planner** | `job_id` 기준 | `job_variants_id` 기준, `jobs_variants.img_asset_id` 사용 |
| **overlay** | `job_id` 기준 | `job_variants_id` 기준, `jobs_variants.img_asset_id` 사용 |
| **vlm_judge** | `job_id` 기준 | `job_variants_id` 기준, `jobs_variants.img_asset_id` 사용 |
| **ocr_eval** | `job_id` 기준 | `job_variants_id` 기준 |
| **readability_eval** | `job_id` 기준 | `job_variants_id` 기준 |
| **iou_eval** | `job_id` 기준 | `job_variants_id` 기준 |

---

## 🔄 트리거 발동 시나리오

### 시나리오 1: img_gen 완료 후 (ye 파트)

```sql
-- ye 파트에서 img_gen 완료 후 jobs_variants 생성
INSERT INTO jobs_variants (job_variants_id, job_id, img_asset_id, creation_order, status, current_step)
VALUES 
    (gen_random_uuid(), 'job-123', 'img-1', 1, 'queued', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-2', 2, 'queued', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-3', 3, 'queued', 'img_gen');

-- 각 variant의 상태를 'done'으로 변경하여 트리거 발동
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'img_gen',
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'job-123' AND status = 'queued';
```

**결과**: 3개의 NOTIFY 이벤트가 발행되어, 각 variant마다 파이프라인이 시작됨

### 시나리오 2: 각 단계 완료 후

```sql
-- variant-1의 vlm_analyze 완료
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'vlm_analyze',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'variant-1';
```

**결과**: variant-1에 대해 yolo_detect가 자동 실행됨

---

## ✅ 구현 완료 체크리스트

### Phase 1: 스키마 및 트리거 변경 ✅
- [x] `jobs_variants` 테이블에 `status`, `current_step`, `updated_at` 컬럼 추가
- [x] 인덱스 추가
- [x] `jobs_variants` 테이블용 트리거 함수 생성
- [x] 트리거 생성 및 테스트
- [x] 매 단계마다 `jobs` 테이블 업데이트 로직 구현

### Phase 2: 데이터베이스 모델 변경 ✅
- [x] `JobVariant` 모델에 새 컬럼 추가
- [x] SQLAlchemy 모델 업데이트

### Phase 3: 리스너 변경 ✅
- [x] `job_variant_state_changed` 채널 리스너 추가
- [x] `_process_job_variant_state_change()` 함수 구현

### Phase 4: 파이프라인 트리거 변경 ✅
- [x] `trigger_next_pipeline_stage_for_variant()` 함수 구현
- [x] `job_variants_id` 기반 파이프라인 실행
- [x] 이미지 조회 로직 변경 (`job_inputs` → `jobs_variants.img_asset_id`)
- [x] 병렬 실행 지원 (각 variant는 독립적으로 실행)

### Phase 5: API 엔드포인트 변경 ✅
- [x] 모든 8개 API 엔드포인트에 `job_variants_id` 필수 파라미터 추가
- [x] 이미지 조회 로직 변경
- [x] Job 상태 업데이트 로직 변경 (`jobs` → `jobs_variants`)

### Phase 6: Thread-safe 모델 로딩 ✅
- [x] LLaVA 모델 로딩 시 `threading.Lock` 사용
- [x] Double-checked locking 패턴 구현

### Phase 7: 테스트 ✅
- [x] 테스트 스크립트 작성 (`test/test_job_variants_pipeline.py`)
- [x] Argument parser로 유동적 테스트 지원
- [x] 테이블 상태 모니터링 기능 추가

---

## ⚠️ 주의사항

### 1. 하위 호환성 (옵션 B 채택)
- **`job_variants_id`는 필수 파라미터**
- 기존 `job_id`만 사용하는 로직은 제거
- 모든 API 엔드포인트에서 `job_variants_id` 필수로 검증

### 2. 데이터 마이그레이션
- 기존 데이터가 있는 경우 마이그레이션 스크립트 필요
- 기존 `jobs` 테이블의 `current_step`, `status`를 `jobs_variants`로 이전

### 3. 다른 파트와의 호환성
- `jobs` 테이블은 그대로 유지 (js, ye 파트에서 사용)
- `jobs_variants`는 yh 파트 전용으로 사용

### 4. 트리거 중복
- `jobs` 테이블 트리거와 `jobs_variants` 테이블 트리거가 모두 필요할 수 있음
- 리스너가 두 채널 모두 수신하도록 설정

---

## 📝 예상 변경 파일 목록

### 스키마
- `db/init/01_schema.sql` (또는 마이그레이션 파일)

### Python 코드
- `database.py` - `JobVariant` 모델 추가/수정
- `services/job_state_listener.py` - variant 이벤트 처리 추가
- `services/pipeline_trigger.py` - `job_variants_id` 지원 추가
- `routers/llava_stage1.py` - `job_variants_id` 파라미터 추가
- `routers/yolo.py` - `job_variants_id` 파라미터 추가
- `routers/planner.py` - `job_variants_id` 파라미터 추가
- `routers/overlay.py` - `job_variants_id` 파라미터 추가
- `routers/llava_stage2.py` - `job_variants_id` 파라미터 추가
- `routers/ocr_eval.py` - `job_variants_id` 파라미터 추가
- `routers/readability_eval.py` - `job_variants_id` 파라미터 추가
- `routers/iou_eval.py` - `job_variants_id` 파라미터 추가
- `models.py` - 모든 Input 모델에 `job_variants_id` 추가

### 테스트
- `test/test_pipeline_full.py` - variant 테스트 추가
- `test/test_pipeline_auto_trigger.py` - variant 테스트 추가
- `test/test_background_trigger.py` - variant 테스트 추가

### 문서
- `DOCS_PIPELINE_COMPLETE.md` - variant 기반 파이프라인 설명 추가
- `DOCS_JOB_STATE_LISTENER.md` - variant 트리거 설명 추가

---

## 🎯 구현 우선순위

### High Priority
1. 스키마 변경 (마이그레이션)
2. 트리거 생성 및 테스트
3. 파이프라인 트리거 로직 변경
4. 핵심 API 엔드포인트 변경 (vlm_analyze, yolo_detect, planner, overlay)

### Medium Priority
5. 평가 API 엔드포인트 변경 (ocr_eval, readability_eval, iou_eval)
6. 리스너 변경
7. 테스트 업데이트

### Low Priority
8. 문서 업데이트
9. 모니터링 스크립트 업데이트

---

## 🔗 Jobs 테이블과 Jobs_Variants 테이블의 상태 연동

### 현재 이해

**Jobs 테이블의 역할**:
- 전체 워크플로우의 상태를 추적
- 각 파트(js, ye, yh)의 단계를 포함
- js: `user_img_input`, `user_txt_input`, `gpt_llm_translation`, `gpt_llm_generation`, `ab_vote`
- ye: `gen_vlm_analyze`, `img_gen`
- yh: `vlm_analyze`, `vlm_planner`, `vlm_judge`, `ocr_eval`, `iou_eval`, `feed_gen`

**Jobs_Variants 테이블의 역할**:
- yh 파트에서 각 variant별로 독립적인 파이프라인 진행 상황 추적
- 각 variant는 독립적인 이미지(`img_asset_id`)를 가짐

### 상태 연동 전략 옵션

> **✅ 최종 결정: 옵션 C (하이브리드)**  
> 아래 옵션 A, B는 참고용이며, 최종적으로 옵션 C로 결정되었습니다.

#### 옵션 A: Jobs 테이블은 집계 상태 (참고용)

**원칙**:
- `jobs.current_step`, `jobs.status`는 해당 `job_id`의 모든 `job_variants`의 상태를 집계한 값
- 모든 variants가 완료되면 `jobs.status = 'done'`
- 하나라도 실행 중이면 `jobs.status = 'running'`

**구현 방법**:
```sql
-- jobs_variants 상태 변경 시 jobs 테이블 자동 업데이트
CREATE OR REPLACE FUNCTION update_job_status_from_variants()
RETURNS TRIGGER AS $$
DECLARE
    all_done BOOLEAN;
    any_running BOOLEAN;
    any_failed BOOLEAN;
BEGIN
    -- 해당 job_id의 모든 variants 상태 확인
    SELECT 
        COUNT(*) FILTER (WHERE status = 'done') = COUNT(*),
        COUNT(*) FILTER (WHERE status = 'running') > 0,
        COUNT(*) FILTER (WHERE status = 'failed') > 0
    INTO all_done, any_running, any_failed
    FROM jobs_variants
    WHERE job_id = NEW.job_id;
    
    -- jobs 테이블 상태 업데이트
    IF all_done THEN
        UPDATE jobs 
        SET status = 'done',
            current_step = 'iou_eval',  -- yh 파트의 마지막 단계
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = NEW.job_id;
    ELSIF any_failed THEN
        UPDATE jobs 
        SET status = 'failed',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = NEW.job_id;
    ELSIF any_running THEN
        UPDATE jobs 
        SET status = 'running',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = NEW.job_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
CREATE TRIGGER update_job_status_from_variants_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    EXECUTE FUNCTION update_job_status_from_variants();
```

**장점**:
- ✅ `jobs` 테이블에서 전체 진행 상황을 한눈에 확인 가능
- ✅ 다른 파트(js, ye)와의 통합 용이
- ✅ 상위 레벨에서 job 완료 여부 확인 가능

**단점**:
- ❌ 집계 로직 복잡도 증가
- ❌ 트리거가 두 테이블 모두 업데이트 (순환 참조 주의)

---

#### 옵션 B: Jobs 테이블은 별개 상태 (참고용)

**원칙**:
- `jobs.current_step`, `jobs.status`는 다른 파트(js, ye)에서 관리
- yh 파트는 `jobs_variants` 테이블만 사용
- 두 테이블은 독립적으로 관리

**구현 방법**:
- `jobs_variants` 테이블만 트리거 사용
- `jobs` 테이블은 js, ye 파트에서만 업데이트
- yh 파트는 `jobs_variants` 테이블만 참조

**장점**:
- ✅ 단순하고 명확한 책임 분리
- ✅ 순환 참조 문제 없음
- ✅ 각 파트가 독립적으로 작동

**단점**:
- ❌ 전체 job 진행 상황 확인이 어려움
- ❌ 다른 파트와의 통합 시 추가 로직 필요

---

#### ✅ 옵션 C: 하이브리드 (Jobs는 매 단계 업데이트) - **최종 결정 및 구현 완료**

**원칙**:
- `jobs.current_step`은 현재 진행 중인 파트의 단계를 나타냄
- yh 파트 시작: `jobs.current_step = 'vlm_analyze'` (ye 파트에서 설정)
- yh 파트 진행 중: **매 단계마다** 모든 variants가 같은 단계에서 `done`이면 `jobs.current_step = 해당 단계`로 업데이트
- yh 파트 완료: 모든 variants가 `iou_eval` 단계에서 `done`이면 `jobs.current_step = 'iou_eval'`, `jobs.status = 'done'`

**구현 방법**:
- ye 파트에서 `img_gen` 완료 시 `jobs.current_step = 'vlm_analyze'` 설정
- yh 파트는 `jobs_variants`만 업데이트
- 모든 variants 완료 시 `jobs` 테이블 업데이트

**장점**:
- ✅ 각 파트의 책임이 명확
- ✅ 전체 워크플로우 추적 가능
- ✅ 순환 참조 최소화

---

## ✅ 최종 결정: 옵션 C (하이브리드)

### 결정 이유
1. **명확한 책임 분리**: 각 파트가 자신의 영역만 관리
2. **통합 가능**: `jobs` 테이블에서 전체 진행 상황 확인 가능
3. **순환 참조 방지**: yh 파트는 `jobs_variants`만 업데이트, 최종 완료 시에만 `jobs` 업데이트
4. **단순성**: 집계 로직 없이 최종 완료 시에만 `jobs` 업데이트

### 구현 세부사항

#### 1. ye 파트에서 yh 파트 시작
```sql
-- ye 파트에서 img_gen 완료 후
-- jobs_variants 생성 및 jobs 테이블 업데이트
INSERT INTO jobs_variants (job_variants_id, job_id, img_asset_id, creation_order, status, current_step)
VALUES 
    (gen_random_uuid(), 'job-123', 'img-1', 1, 'queued', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-2', 2, 'queued', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-3', 3, 'queued', 'img_gen');

-- jobs 테이블 업데이트 (ye 파트에서)
UPDATE jobs 
SET current_step = 'vlm_analyze',  -- yh 파트 시작 단계
    status = 'running',
    updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'job-123';
```

#### 2. yh 파트 진행 중
```sql
-- 각 variant별로 독립적으로 진행
-- jobs_variants 테이블만 업데이트
UPDATE jobs_variants 
SET status = 'running',
    current_step = 'vlm_analyze',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'variant-1';

-- jobs 테이블은 업데이트하지 않음 (ye 파트에서 설정한 값 유지)
```

#### 3. yh 파트 진행 중 (매 단계마다 jobs 테이블 업데이트)
```sql
-- 트리거 함수: 매 단계마다 모든 variants 완료 여부 확인
CREATE OR REPLACE FUNCTION check_all_variants_done()
RETURNS TRIGGER AS $$
DECLARE
    total_count INTEGER;
    done_count INTEGER;
    current_step_done_count INTEGER;
    all_same_step_done BOOLEAN;
    job_status TEXT;
    job_current_step TEXT;
BEGIN
    -- 해당 job_id의 모든 variants 개수 및 상태 확인
    SELECT 
        COUNT(*),
        COUNT(*) FILTER (WHERE status = 'done'),
        COUNT(*) FILTER (WHERE status = 'done' AND current_step = NEW.current_step)
    INTO total_count, done_count, current_step_done_count
    FROM jobs_variants
    WHERE job_id = NEW.job_id;
    
    -- img_gen 단계는 제외
    IF NEW.current_step = 'img_gen' THEN
        RETURN NEW;
    END IF;
    
    -- 모든 variants가 같은 단계에서 done인지 확인
    all_same_step_done := (current_step_done_count = total_count);
    
    -- 모든 variants가 같은 단계에서 done인 경우
    IF all_same_step_done THEN
        job_status := 'done';
        job_current_step := NEW.current_step;  -- 현재 단계로 업데이트
    -- 진행 중인 경우
    ELSIF done_count > 0 OR failed_count > 0 THEN
        job_status := 'running';
        IF current_step_done_count > 0 THEN
            job_current_step := NEW.current_step;
        ELSE
            -- 이전 단계 유지
            SELECT current_step INTO job_current_step FROM jobs WHERE job_id = NEW.job_id;
        END IF;
    END IF;
    
    -- jobs 테이블 업데이트
    UPDATE jobs 
    SET status = job_status,
        current_step = job_current_step,
        updated_at = CURRENT_TIMESTAMP
    WHERE job_id = NEW.job_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_all_variants_done_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    WHEN (NEW.status = 'done' OR NEW.status = 'failed')
    EXECUTE FUNCTION check_all_variants_done();
```

**동작 방식**:
- 모든 variants가 `vlm_analyze` 단계에서 `done` → `jobs.current_step = 'vlm_analyze'`, `jobs.status = 'done'`
- 모든 variants가 `yolo_detect` 단계에서 `done` → `jobs.current_step = 'yolo_detect'`, `jobs.status = 'done'`
- 모든 variants가 `iou_eval` 단계에서 `done` → `jobs.current_step = 'iou_eval'`, `jobs.status = 'done'` (최종 완료)

---

## ✅ 결정 사항 요약

### 1. Job 상태 관리 (✅ 결정됨)
- **옵션 C (하이브리드) 채택**
- `jobs` 테이블: ye 파트에서 yh 파트 시작 시 `current_step = 'vlm_analyze'` 설정
- `jobs_variants` 테이블: yh 파트 진행 중에는 이 테이블만 업데이트
- 모든 variants 완료 시: 트리거로 `jobs.status = 'done'`, `jobs.current_step = 'iou_eval'` 자동 업데이트

### 2. 트리거 전략 (✅ 결정됨)
- **`jobs_variants` 테이블만 트리거 사용**
- `jobs_variants` 상태 변경 시 NOTIFY 발행
- 리스너가 `job_variant_state_changed` 채널 수신
- 모든 variants 완료 시 트리거 함수로 `jobs` 테이블 자동 업데이트

### 3. 하위 호환성 (✅ 결정됨)
- **옵션 B 채택**: `job_variants_id` **필수**로 변경
- 모든 API 엔드포인트에서 `job_variants_id` 필수 파라미터로 처리
- 기존 `job_id`만 사용하는 로직은 제거

### 4. 병렬 실행 (✅ 결정됨)
- **옵션 A 채택**: 3개 variant를 **병렬로 실행**
- 각 variant는 독립적이므로 병렬 실행 가능
- **주의**: GCP VM 성능 테스트 필요 (리소스 부족 시 순차 실행으로 변경 고려)

---

## 🚀 병렬 실행 구현 세부사항

### ✅ 구현 완료: Thread-safe 모델 로딩

**파일**: `services/llava_service.py`

```python
import threading

_model_lock = threading.Lock()  # 모델 로딩 동기화를 위한 락

def get_llava_model():
    """LLaVa 모델 및 프로세서 로드 (싱글톤 패턴, thread-safe)"""
    global _processor, _model
    
    # Double-checked locking 패턴으로 thread-safe하게 모델 로딩
    if _model is None or _processor is None:
        with _model_lock:
            # 다시 확인 (다른 스레드가 이미 로딩했을 수 있음)
            if _model is None or _processor is None:
                # 모델 로딩 코드...
```

**동작 방식**:
- 여러 variants가 동시에 모델을 요청해도 한 번만 로드됨
- 첫 번째 요청이 모델을 로드하는 동안 다른 요청은 대기
- 모델 로딩 완료 후 모든 요청이 같은 모델 인스턴스 사용

### 병렬 실행 동작

1. **각 variant는 독립적으로 실행**:
   - 각 variant는 별도의 API 요청으로 처리
   - FastAPI가 비동기로 여러 요청을 동시에 처리

2. **모델 로딩 충돌 방지**:
   - Thread-safe 모델 로딩으로 동시 접근 시 한 번만 로드
   - 나머지는 로딩 완료를 대기

3. **에러 처리**:
   - 하나의 variant 실패 시 다른 variant는 계속 실행
   - 각 variant는 독립적으로 에러 처리

---

## 📝 구현 완료 파일 목록

### 스키마 및 트리거
- ✅ `db/init/01_schema.sql` - `jobs_variants` 테이블 스키마 변경
- ✅ `db/init/03_job_variants_state_notify_trigger.sql` - 트리거 함수 및 트리거 생성

### Python 코드
- ✅ `database.py` - `JobVariant` 모델 추가/수정
- ✅ `models.py` - 모든 Input 모델에 `job_variants_id` 필수 필드 추가
- ✅ `services/job_state_listener.py` - variant 이벤트 처리 추가
- ✅ `services/pipeline_trigger.py` - `job_variants_id` 기반 파이프라인 트리거 구현
- ✅ `services/llava_service.py` - Thread-safe 모델 로딩 구현
- ✅ `routers/llava_stage1.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/yolo.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/planner.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/overlay.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/llava_stage2.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/ocr_eval.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/readability_eval.py` - `job_variants_id` 파라미터 추가
- ✅ `routers/iou_eval.py` - `job_variants_id` 파라미터 추가

### 테스트
- ✅ `test/test_job_variants_pipeline.py` - Job Variants 기반 파이프라인 테스트 스크립트

---

## 🔄 트리거 동작 시나리오 (최종)

### 시나리오 1: img_gen 완료 후 (ye 파트)
```sql
-- ye 파트에서 jobs_variants 생성
INSERT INTO jobs_variants (job_variants_id, job_id, img_asset_id, creation_order, status, current_step)
VALUES 
    (gen_random_uuid(), 'job-123', 'img-1', 1, 'done', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-2', 2, 'done', 'img_gen'),
    (gen_random_uuid(), 'job-123', 'img-3', 3, 'done', 'img_gen');
```

**결과**: 
- `img_gen` 단계는 제외되므로 `jobs` 테이블 업데이트 안 함
- 3개의 NOTIFY 이벤트가 발행되어, 각 variant마다 파이프라인이 시작됨

### 시나리오 2: 각 단계 완료 후
```sql
-- variant-1의 vlm_analyze 완료
UPDATE jobs_variants 
SET status = 'done', 
    current_step = 'vlm_analyze',
    updated_at = CURRENT_TIMESTAMP
WHERE job_variants_id = 'variant-1';
```

**결과**: 
- variant-1에 대해 yolo_detect가 자동 실행됨
- 모든 variants가 `vlm_analyze`에서 `done`이면 `jobs.current_step = 'vlm_analyze'`로 업데이트

### 시나리오 3: 모든 variants가 같은 단계에서 완료
```sql
-- 모든 variants가 yolo_detect 단계에서 done
-- (각 variant가 독립적으로 업데이트됨)
```

**결과**: 
- 트리거가 모든 variants가 `yolo_detect`에서 `done`인 것을 감지
- `jobs.current_step = 'yolo_detect'`, `jobs.status = 'done'`으로 업데이트

---

**작성일**: 2025-11-28  
**최종 업데이트**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 2.0.0 (구현 완료, 매 단계 jobs 테이블 업데이트, thread-safe 모델 로딩)


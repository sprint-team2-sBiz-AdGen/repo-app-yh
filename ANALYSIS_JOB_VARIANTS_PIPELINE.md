# Job Variants 기반 파이프라인 변경 분석

## 🎯 핵심 결정 사항

### ✅ 최종 결정: 옵션 C (하이브리드)
- **Job 상태 관리**: `jobs` 테이블은 ye 파트에서 yh 파트 시작 시 업데이트, yh 파트 진행 중에는 `jobs_variants`만 업데이트, 모든 variants 완료 시 `jobs` 자동 업데이트
    - ye 파트 → yh 파트 시작: jobs.current_step = 'vlm_analyze' 설정
    - yh 파트 진행 중: jobs_variants 테이블만 업데이트
    - 모든 variants 완료: 트리거로 jobs.status = 'done', jobs.current_step = 'iou_eval' 자동 업데이트
- **트리거 전략**: `jobs_variants` 테이블만 트리거 사용
- **하위 호환성**: `job_variants_id`는 **필수** (옵션 B)
- **실행 방식**: **병렬 실행** (옵션 A) - GCP VM 성능 테스트 필요

---

## 📋 현재 상황

### 현재 구조
- **Job ID 기준**: 하나의 `job_id`에 대해 파이프라인이 한 번 실행됨
- **Job Variants**: 하나의 `job_id`에 대해 `jobs_variants` 테이블에 3개의 variant가 생성됨
- **문제**: 각 variant마다 파이프라인을 실행해야 하는데, 현재는 job_id 기준으로만 실행됨

### 요구사항
- **Job ID 하나당**: 3개의 variant가 생성됨
- **각 Variant마다**: 파이프라인을 독립적으로 실행해야 함
- **결과**: Job ID 하나당 파이프라인이 3번 실행되어야 함

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

#### `jobs_variants` 테이블 (현재)
```sql
CREATE TABLE jobs_variants (
    job_variants_id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(job_id),
    img_asset_id UUID REFERENCES image_assets(image_asset_id),
    creation_order INTEGER NOT NULL,
    selected BOOLEAN DEFAULT FALSE,
    ...
);
```

**현재 문제점**:
- `jobs_variants` 테이블에 `current_step`, `status` 컬럼이 없음
- 각 variant의 파이프라인 진행 상황을 추적할 수 없음

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

## 🎯 해결 방안 분석

### 옵션 1: `jobs_variants` 테이블에 상태 컬럼 추가 (권장)

#### 변경 사항

**1. 스키마 변경**
```sql
ALTER TABLE jobs_variants 
ADD COLUMN status TEXT DEFAULT 'queued',  -- queued, running, done, failed
ADD COLUMN current_step TEXT,  -- 'vlm_analyze', 'yolo_detect', 'planner', etc.
ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
```

**2. 트리거 변경**
- `jobs` 테이블 트리거 → `jobs_variants` 테이블 트리거로 변경
- 또는 두 테이블 모두에 트리거 생성

**3. 파이프라인 트리거 로직 변경**
- `job_id` 기준 → `job_variants_id` 기준으로 변경
- 각 variant별로 독립적인 파이프라인 실행

**장점**:
- ✅ 각 variant별로 독립적인 상태 관리
- ✅ variant별로 독립적인 파이프라인 진행 추적
- ✅ 기존 `jobs` 테이블 구조 유지 (다른 파트와 호환성)
- ✅ variant별로 선택적으로 실행 가능

**단점**:
- ❌ 스키마 변경 필요
- ❌ 트리거 변경 필요
- ❌ 모든 API 엔드포인트 수정 필요 (`job_id` → `job_variants_id`)

---

### 옵션 2: `job_variants_id`를 파라미터로 추가 (하이브리드)

#### 변경 사항

**1. 스키마 변경 없음**
- `jobs_variants` 테이블에 상태 컬럼 추가하지 않음
- `jobs` 테이블의 `current_step`, `status`를 variant별로 관리

**2. 파이프라인 트리거 로직 변경**
- `job_id` + `job_variants_id` 조합으로 파이프라인 실행
- 각 variant별로 순차적으로 또는 병렬로 실행

**3. API 엔드포인트 변경**
- 모든 API에 `job_variants_id` 파라미터 추가 (Optional)
- `job_variants_id`가 있으면 해당 variant의 이미지 사용
- 없으면 기존처럼 `job_inputs`의 이미지 사용

**장점**:
- ✅ 스키마 변경 최소화
- ✅ 기존 로직과 호환성 유지 가능

**단점**:
- ❌ `jobs` 테이블의 `current_step`, `status`를 variant별로 관리하기 어려움
- ❌ 어떤 variant가 현재 실행 중인지 추적 어려움
- ❌ 복잡한 상태 관리 로직 필요

---

### 옵션 3: Variant별로 별도의 Job 생성

#### 변경 사항

**1. 스키마 변경 없음**
- 기존 테이블 구조 유지

**2. 로직 변경**
- `jobs_variants`가 생성될 때 각 variant마다 별도의 `job_id` 생성
- 각 `job_id`는 독립적인 파이프라인 실행

**장점**:
- ✅ 기존 파이프라인 로직 그대로 사용 가능
- ✅ 스키마 변경 없음

**단점**:
- ❌ `job_id` 관리 복잡 (원본 job과 variant job 구분 필요)
- ❌ 데이터 중복 가능성
- ❌ 다른 파트(js, ye)와의 호환성 문제

---

## 💡 권장 방안: 옵션 1 (jobs_variants에 상태 컬럼 추가)

### 이유
1. **명확한 상태 관리**: 각 variant별로 독립적인 상태 추적 가능
2. **확장성**: 향후 variant별 선택적 실행, 우선순위 설정 등 가능
3. **호환성**: 기존 `jobs` 테이블 구조 유지 (다른 파트와 호환)
4. **트리거 활용**: PostgreSQL 트리거를 variant 기준으로 활용 가능

---

## 🔧 구현 계획

### 1단계: 스키마 변경

```sql
-- jobs_variants 테이블에 상태 컬럼 추가
ALTER TABLE jobs_variants 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'queued',
ADD COLUMN IF NOT EXISTS current_step TEXT,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_jobs_variants_status ON jobs_variants(status);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_current_step ON jobs_variants(current_step);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_job_id_status ON jobs_variants(job_id, status);
```

### 2단계: 트리거 변경

#### 옵션 A: jobs_variants 테이블에 트리거 추가 (권장)
```sql
-- jobs_variants 테이블용 트리거 함수
CREATE OR REPLACE FUNCTION notify_job_variant_state_change()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.current_step IS DISTINCT FROM NEW.current_step 
       OR OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify('job_variant_state_changed', 
            json_build_object(
                'job_variants_id', NEW.job_variants_id,
                'job_id', NEW.job_id,
                'current_step', NEW.current_step,
                'status', NEW.status,
                'img_asset_id', NEW.img_asset_id
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
CREATE TRIGGER job_variant_state_change_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    WHEN (OLD.current_step IS DISTINCT FROM NEW.current_step 
       OR OLD.status IS DISTINCT FROM NEW.status)
    EXECUTE FUNCTION notify_job_variant_state_change();
```

#### 옵션 B: jobs 테이블 트리거 유지 + jobs_variants 트리거 추가
- 두 테이블 모두에 트리거 생성
- 리스너가 두 채널 모두 수신

### 3단계: 파이프라인 트리거 로직 변경

#### 변경 전
```python
# job_id 기준으로 파이프라인 실행
trigger_next_pipeline_stage(job_id, current_step, status, tenant_id)
```

#### 변경 후
```python
# job_variants_id 기준으로 파이프라인 실행
trigger_next_pipeline_stage(
    job_variants_id=job_variants_id,
    job_id=job_id,  # 참조용
    current_step=current_step,
    status=status,
    tenant_id=tenant_id
)
```

### 4단계: API 엔드포인트 변경

모든 API 엔드포인트에 `job_variants_id` 파라미터 추가:

```python
class LLaVaStage1In(BaseModel):
    job_id: str  # 유지 (참조용)
    job_variants_id: str  # 추가 (필수)
    tenant_id: str
    # ...
```

**이미지 조회 로직 변경**:
```python
# 변경 전: job_inputs에서 이미지 조회
job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
img_asset_id = job_input.img_asset_id

# 변경 후: jobs_variants에서 이미지 조회
job_variant = db.query(JobVariant).filter(
    JobVariant.job_variants_id == job_variants_id
).first()
img_asset_id = job_variant.img_asset_id
```

### 5단계: Job 상태 업데이트 로직 변경

#### 변경 전
```python
# jobs 테이블 업데이트
db.execute(text("""
    UPDATE jobs 
    SET status = 'running', 
        current_step = 'vlm_analyze'
    WHERE job_id = :job_id
"""), {"job_id": job_id})
```

#### 변경 후
```python
# jobs_variants 테이블 업데이트
db.execute(text("""
    UPDATE jobs_variants 
    SET status = 'running', 
        current_step = 'vlm_analyze',
        updated_at = CURRENT_TIMESTAMP
    WHERE job_variants_id = :job_variants_id
"""), {"job_variants_id": job_variants_id})
```

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

## 🛠️ 구현 단계별 체크리스트

### Phase 1: 스키마 및 트리거 변경
- [ ] `jobs_variants` 테이블에 `status`, `current_step`, `updated_at` 컬럼 추가
- [ ] 인덱스 추가
- [ ] `jobs_variants` 테이블용 트리거 함수 생성
- [ ] 트리거 생성 및 테스트

### Phase 2: 데이터베이스 모델 변경
- [ ] `JobVariant` 모델에 새 컬럼 추가
- [ ] SQLAlchemy 모델 업데이트

### Phase 3: 리스너 변경
- [ ] `job_variant_state_changed` 채널 리스너 추가
- [ ] 또는 기존 리스너에 variant 이벤트 처리 추가

### Phase 4: 파이프라인 트리거 변경
- [ ] `trigger_next_pipeline_stage` 함수에 `job_variants_id` 파라미터 추가 (필수)
- [ ] `PIPELINE_STAGES` 로직은 유지 (단계 매핑은 동일)
- [ ] 이미지 조회 로직 변경 (`job_inputs` → `jobs_variants.img_asset_id`)
- [ ] **병렬 실행 구현**: 같은 `job_id`의 여러 variant를 병렬로 처리
  - 리스너에서 `job_id`별로 그룹화하여 `asyncio.gather()`로 병렬 실행
  - 각 variant는 독립적인 태스크로 실행

### Phase 5: API 엔드포인트 변경
- [ ] 모든 API 엔드포인트에 `job_variants_id` 파라미터 추가
- [ ] 이미지 조회 로직 변경
- [ ] Job 상태 업데이트 로직 변경 (`jobs` → `jobs_variants`)

### Phase 6: 테스트
- [ ] 단위 테스트 업데이트
- [ ] 통합 테스트 업데이트
- [ ] 전체 파이프라인 테스트

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

#### ✅ 옵션 C: 하이브리드 (Jobs는 최종 단계만) - **최종 결정**

**원칙**:
- `jobs.current_step`은 현재 진행 중인 파트의 단계를 나타냄
- yh 파트 시작: `jobs.current_step = 'vlm_analyze'` (ye 파트에서 설정)
- yh 파트 진행 중: `jobs.current_step`은 유지, `jobs_variants`만 업데이트
- yh 파트 완료: 모든 variants 완료 시 `jobs.current_step = 'iou_eval'`, `jobs.status = 'done'`

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

#### 3. yh 파트 완료 시
```sql
-- 모든 variants 완료 확인 후 jobs 테이블 업데이트
-- (트리거 또는 애플리케이션 로직에서 처리)

-- 트리거 함수
CREATE OR REPLACE FUNCTION check_all_variants_done()
RETURNS TRIGGER AS $$
DECLARE
    total_count INTEGER;
    done_count INTEGER;
BEGIN
    -- 해당 job_id의 모든 variants 개수 확인
    SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'done')
    INTO total_count, done_count
    FROM jobs_variants
    WHERE job_id = NEW.job_id;
    
    -- 모든 variants가 완료되면 jobs 테이블 업데이트
    IF total_count > 0 AND done_count = total_count THEN
        UPDATE jobs 
        SET status = 'done',
            current_step = 'iou_eval',  -- yh 파트의 마지막 단계
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = NEW.job_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_all_variants_done_trigger
    AFTER UPDATE ON jobs_variants
    FOR EACH ROW
    WHEN (NEW.status = 'done')
    EXECUTE FUNCTION check_all_variants_done();
```

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

### 리스너에서 병렬 처리 로직

```python
# services/job_state_listener.py

async def _process_job_variant_state_change(self, payload: dict):
    """job_variants 상태 변경 처리 (병렬 실행 지원)"""
    job_variants_id = payload.get('job_variants_id')
    job_id = payload.get('job_id')
    current_step = payload.get('current_step')
    status = payload.get('status')
    
    # 같은 job_id의 다른 variant들도 함께 처리할지 확인
    if status == 'done' and current_step in ['img_gen', 'vlm_analyze', 'yolo_detect', ...]:
        # 같은 job_id의 모든 queued/running variant들을 찾아서 병렬 실행
        variants = await self._get_pending_variants(job_id)
        
        # 병렬 실행
        tasks = [
            self._trigger_variant_pipeline(variant_id)
            for variant_id in variants
        ]
        
        # asyncio.gather로 병렬 실행 (최대 3개)
        await asyncio.gather(*tasks, return_exceptions=True)
```

### 성능 고려사항

1. **리소스 모니터링**: 
   - CPU 사용률, 메모리 사용률, GPU 사용률 모니터링
   - 리소스 부족 시 순차 실행으로 전환

2. **병렬 수 제한**:
   - 초기: 3개 variant 모두 병렬 실행
   - 리소스 부족 시: 2개씩 또는 순차 실행

3. **에러 처리**:
   - 하나의 variant 실패 시 다른 variant는 계속 실행
   - 각 variant는 독립적으로 에러 처리

---

**작성일**: 2025-11-28  
**작성자**: LEEYH205  
**버전**: 1.1.0 (옵션 C 결정, 병렬 실행 추가)


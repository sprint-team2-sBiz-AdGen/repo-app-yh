# Instagram Feed 파이프라인 통합 분석

## 📋 개요

사용자 요구사항: **간단 설명 → 광고문구 생성 → 광고 피드글 생성**을 기존 Job 파이프라인에 통합

**실제 파이프라인 흐름 (다이어그램 기반):**
1. **초기 단계**: 한국어 설명 (30자) → GPT Kor→Eng → GPT 광고문구 생성 (영어)
2. **검증 단계**: LLaVA Stage 1에서 생성 이미지와 광고문구 검증 → (선택적) Refined Ad Copy
3. **이미지 처리**: YOLO → Planner → Overlay → 평가 단계들
4. **최종 단계**: GPT Eng→Kor (한글 광고문구) → 인스타그램 피드글 생성

**작성일**: 2025-12-01  
**버전**: 3.0.0 (파트 분리, Trace 관리, txt_ad_copy_generations 테이블 추가)  
**작성자**: LEEYH205

**파트 분리:**
- **JS 파트**: user input, GPT Kor→Eng, GPT 광고문구 생성
- **YH 파트**: LLaVA 검증, GPT Eng→Kor, GPT 피드글 생성

---

## 🔍 현재 구조 분석

### 1. 현재 파이프라인 단계

```
[초기 단계 - 파이프라인 시작 전]
사용자 입력 (한국어 설명 30자, Tone & Style, Store Information)
  ↓
GPT Kor → Eng (한국어 설명 → 영어 변환)  ← Job 레벨
  ↓
GPT Product Ad Copy Generation (영어 광고문구 생성)  ← Job 레벨
  ↓
[이미지 처리 파이프라인]
img_gen (done)
  ↓ [자동 실행]
vlm_analyze (LLaVA Stage 1) - 이미지와 광고문구 검증
  ↓ [자동 실행]
(선택적) Refined Ad Copy (검증 결과에 따라 광고문구 조정)  ← Job 레벨
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
  ↓
[최종 단계]
GPT Eng → Kor (영어 광고문구 → 한글 변환)  ← Job 레벨
  ↓
Instagram Feed Generation (인스타그램 피드글 생성)  ← Job 레벨
```

**총 8단계 (이미지 처리) + 4단계 (텍스트 생성) = 12단계**로 구성

### 2. 현재 데이터베이스 구조

#### `jobs` 테이블
- `job_id` (UUID, PK)
- `tenant_id` (VARCHAR)
- `status` (TEXT): queued, running, done, failed
- `current_step` (TEXT): 파이프라인 단계 추적
- `retry_count` (INTEGER): 재시도 횟수

#### `jobs_variants` 테이블
- `job_variants_id` (UUID, PK)
- `job_id` (UUID, FK → jobs)
- `img_asset_id` (UUID, FK → image_assets)
- `status` (TEXT): queued, running, done, failed
- `current_step` (TEXT): variant별 파이프라인 단계
- `retry_count` (INTEGER)
- `overlaid_img_asset_id` (UUID, FK → image_assets): 최종 오버레이 이미지

#### `job_inputs` 테이블
- `job_id` (UUID, PK, FK → jobs)
- `img_asset_id` (UUID, FK → image_assets)
- `tone_style_id` (UUID, FK → tone_styles)
- `desc_kor` (TEXT): 한국어 설명 (사용자 입력, 30자)
- `desc_eng` (TEXT): 영어 설명 (GPT Kor→Eng 결과 또는 광고문구)

#### `jobs` 테이블
- `job_id` (UUID, PK)
- `store_id` (UUID, FK → stores): 스토어 ID

#### `stores` 테이블
- `store_id` (UUID, PK)
- `user_id` (UUID, FK → users)
- `image_id` (UUID, FK → image_assets)
- `title` (VARCHAR): 스토어 제목
- `body` (TEXT): 스토어 설명 (스토어 정보로 사용)
- `store_category` (TEXT): 스토어 카테고리
- `auto_scoring_flag` (BOOLEAN)

**스토어 정보 조회 방법:**
```sql
SELECT s.title, s.body, s.store_category
FROM jobs j
INNER JOIN stores s ON j.store_id = s.store_id
WHERE j.job_id = :job_id
```
- **참고**: 스토어 정보는 `jobs.store_id`를 통해 `stores` 테이블에서 조회
- `job_inputs` 테이블에 `store_information` 컬럼 추가 불필요

#### `llm_traces` 테이블 (이미 존재, Trace 관리용)
- `llm_trace_id` (UUID, PK)
- `job_id` (UUID, FK → jobs) ✅ **Job과 연결**
- `provider` (TEXT): 'gpt', 'anthropic' 등
- `tone_style_id` (UUID, FK → tone_styles)
- `enhanced_img_id` (UUID, FK → image_assets)
- `prompt_id` (UUID)
- `operation_type` (TEXT): 'translate', 'prompt', 'ad_copy_gen', 'eng_to_kor', 'feed_gen' 등
- `request` (JSONB): GPT API 요청 데이터
- `response` (JSONB): GPT API 응답 데이터
- `latency_ms` (FLOAT): API 호출 소요 시간

#### `txt_ad_copy_generations` 테이블 (신규 제안)
- `ad_copy_gen_id` (UUID, PK)
- `job_id` (UUID, FK → jobs) ✅ **Job과 연결**
- `llm_trace_id` (UUID, FK → llm_traces): Trace 참조
- `generation_stage` (TEXT): 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
- `ad_copy_kor` (TEXT): 한국어 광고문구 (최종)
- `ad_copy_eng` (TEXT): 영어 광고문구
- `refined_ad_copy_eng` (TEXT): 조정된 영어 광고문구
- `status` (TEXT): 'queued', 'running', 'done', 'failed'
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

#### `instagram_feeds` 테이블 (이미 존재)
- `instagram_feed_id` (UUID, PK)
- `job_id` (UUID, FK → jobs) ✅ **이미 Job과 연결됨**
- `llm_trace_id` (UUID, FK → llm_traces): Trace 참조 (신규 추가)
- `overlay_id` (UUID, FK → overlay_layouts)
- `llm_model_id` (UUID, FK → llm_models)
- `tenant_id` (VARCHAR)
- `refined_ad_copy_eng` (TEXT): 조정된 광고문구 (영어)
- `ad_copy_kor` (TEXT): 한글 광고문구 (신규 추가)
- `tone_style` (TEXT): 톤 & 스타일
- `product_description` (TEXT): 제품 설명
- `store_information` (TEXT): 스토어 정보 (jobs.store_id → stores 테이블에서 조회)
- `gpt_prompt` (TEXT): GPT 프롬프트
- `instagram_ad_copy` (TEXT): 생성된 인스타그램 피드 글
- `hashtags` (TEXT): 해시태그

### 3. 현재 API 엔드포인트

#### `/api/yh/gpt/ad-copy` (Mock 구현)
- 입력: `tone_style`, `product_description`, `store_information`
- 출력: `ad_copy_text` (Mock)
- 상태: TODO (실제 GPT API 연동 미구현)

#### `/api/yh/instagram/feed` (구현 완료)
- 입력: `refined_ad_copy_eng`, `tone_style`, `product_description`, `store_information`, `gpt_prompt`
- 출력: `instagram_ad_copy`, `hashtags`
- 상태: ✅ 구현 완료, GPT API 연동 완료

---

## 💡 통합 방안 분석

### ❌ 옵션 1: 별도 Job 생성 (사용자 요구사항에 부합하지 않음)

**문제점:**
- 사용자가 명시적으로 "job을 따로 만들면 안 될 것 같고"라고 요청
- Job 간 연결 관리 복잡도 증가
- 데이터 일관성 문제

### ❌ 옵션 2: 별도 데이터베이스 생성 (불필요)

**문제점:**
- `instagram_feeds` 테이블이 이미 `job_id`를 참조하고 있음
- 현재 데이터베이스 구조로 충분히 통합 가능
- 별도 DB는 오히려 복잡도만 증가

### ✅ 옵션 3: 파이프라인 단계 확장 (권장) - **다이어그램 기반 수정**

**장점:**
1. **기존 구조 활용**: `instagram_feeds` 테이블이 이미 `job_id`를 참조
2. **자동화**: 파이프라인 트리거로 자동 실행
3. **일관성**: 모든 단계가 같은 Job으로 관리
4. **단순성**: 별도 DB나 Job 생성 불필요

**구현 방안:**

#### 3.1 파이프라인 단계 추가 (다이어그램 기반)

**초기 단계 (Job 생성 시 또는 img_gen 전):**
```
[Job 생성]
  ↓
desc_kor_translate (GPT Kor → Eng)  ← Job 레벨 (JS 파트)
  - job_inputs.desc_kor → GPT API → llm_traces 저장
  - txt_ad_copy_generations 저장 (generation_stage='kor_to_eng', ad_copy_eng=영어 설명)
  - job_inputs.desc_eng 업데이트
  ↓
ad_copy_gen_eng (GPT Product Ad Copy Generation)  ← Job 레벨 (JS 파트)
  - job_inputs.desc_eng, tone_style_id → GPT API → llm_traces 저장
  - txt_ad_copy_generations 저장/업데이트 (generation_stage='ad_copy_eng', ad_copy_eng=영어 광고문구)
```

**중간 단계 (vlm_analyze 이후, 선택적):**
```
vlm_analyze (done)  ← YH 파트
  - txt_ad_copy_generations.ad_copy_eng 조회
  - 생성된 이미지와 광고문구 검증
  - vlm_traces 저장 (operation_type='analyze')
  ↓ [검증 결과에 따라]
refined_ad_copy (Refined Ad Copy)  ← Job 레벨 (YH 파트, 선택적)
  - 검증 결과가 불만족스러우면 GPT API 호출 → llm_traces 저장
  - txt_ad_copy_generations 업데이트 (generation_stage='refined_ad_copy', refined_ad_copy_eng)
```

**최종 단계 (iou_eval 이후):**
```
iou_eval (done)
  ↓ [자동 실행]
ad_copy_gen_kor (GPT Eng → Kor)  ← Job 레벨 (YH 파트)
  - txt_ad_copy_generations.ad_copy_eng 또는 refined_ad_copy_eng 조회
  - GPT API 호출 → llm_traces 저장 (operation_type='eng_to_kor')
  - txt_ad_copy_generations 저장/업데이트 (generation_stage='eng_to_kor', ad_copy_kor=한글 광고문구)
  - instagram_feeds.ad_copy_kor 저장
  ↓ [자동 실행]
instagram_feed_gen (Instagram Feed Generation)  ← Job 레벨 (YH 파트)
  - txt_ad_copy_generations.ad_copy_kor 조회
  - job_inputs 데이터 조회 → GPT API 호출 → llm_traces 저장 (operation_type='feed_gen')
  - instagram_feeds 테이블에 저장 (llm_trace_id 포함)
```

**총 8단계 (이미지) + 4단계 (텍스트) = 12단계**로 확장

#### 3.2 Job 레벨 처리

**특징:**
- `ad_copy_gen`과 `instagram_feed_gen`은 **Job 레벨에서 한 번만 실행**
- Variant별로 실행할 필요 없음 (이미지 생성과 달리 텍스트 생성이므로)
- `jobs` 테이블의 `current_step`으로 추적
- `jobs_variants` 테이블은 업데이트하지 않음 (이미 `iou_eval, done` 상태 유지)

#### 3.3 데이터 흐름 (다이어그램 기반)

```
[Phase 1: 초기 텍스트 생성 - Job 생성 시]
1. 사용자 입력
   - 이미지: job_inputs.img_asset_id
   - 한국어 설명 (30자): job_inputs.desc_kor
   - 톤 & 스타일: job_inputs.tone_style_id → tone_styles
   - 스토어 정보: jobs.store_id → stores 테이블에서 조회

2. desc_kor_translate 실행 (Job 생성 직후 또는 img_gen 전) - JS 파트
   - job_inputs.desc_kor 조회
   - GPT API 호출: 한국어 → 영어 변환
   - llm_traces 저장 (operation_type='kor_to_eng', request/response 포함)
   - txt_ad_copy_generations 레코드 생성:
     * generation_stage='kor_to_eng'
     * ad_copy_eng=영어 설명 (변환 결과)
     * llm_trace_id=생성된 llm_trace_id 참조
     * status='done'
   - job_inputs.desc_eng 업데이트
   - job.current_step = 'desc_kor_translate', status = 'done'

3. ad_copy_gen_eng 실행 - JS 파트
   - job_inputs.desc_eng, tone_style_id 조회
   - GPT API 호출: 영어 광고문구 생성
   - llm_traces 저장 (operation_type='ad_copy_gen', request/response 포함)
   - txt_ad_copy_generations 레코드 생성/업데이트:
     * generation_stage='ad_copy_eng'
     * ad_copy_eng=영어 광고문구 (생성 결과)
     * llm_trace_id=생성된 llm_trace_id 참조
     * status='done'
   - job.current_step = 'ad_copy_gen_eng', status = 'done'

[Phase 2: 이미지 처리 파이프라인]
4. img_gen 완료
   - 파이프라인 트리거: vlm_analyze 실행

5. vlm_analyze 실행 - YH 파트
   - txt_ad_copy_generations.ad_copy_eng 조회 (generation_stage='ad_copy_eng')
   - 생성된 이미지와 광고문구 검증
   - vlm_traces 저장 (operation_type='analyze', request/response 포함)
   - 검증 결과에 따라 refined_ad_copy 실행 여부 결정

6. (선택적) refined_ad_copy 실행 - YH 파트
   - 검증 결과가 불만족스러우면 GPT API 호출: 광고문구 조정
   - llm_traces 저장 (operation_type='ad_copy_gen', refined, request/response 포함)
   - txt_ad_copy_generations 레코드 업데이트:
     * generation_stage='refined_ad_copy'
     * refined_ad_copy_eng=조정된 영어 광고문구
     * llm_trace_id=생성된 llm_trace_id 참조
     * status='done'

7. ... (기존 파이프라인: yolo_detect → planner → overlay → 평가 단계들) ...

[Phase 3: 최종 텍스트 생성 - iou_eval 이후]
8. iou_eval 완료
   - job.current_step = 'iou_eval'
   - job.status = 'done' (모든 variants 완료 시)
   - 파이프라인 트리거: ad_copy_gen_kor 실행

9. ad_copy_gen_kor 실행 - YH 파트
   - txt_ad_copy_generations 조회:
     * refined_ad_copy_eng이 있으면 → refined_ad_copy_eng 사용
     * 없으면 → ad_copy_eng 사용
   - GPT API 호출: 영어 → 한글 변환
   - llm_traces 저장 (operation_type='eng_to_kor', request/response 포함)
   - txt_ad_copy_generations 레코드 생성/업데이트:
     * generation_stage='eng_to_kor'
     * ad_copy_kor=한글 광고문구 (변환 결과)
     * llm_trace_id=생성된 llm_trace_id 참조
     * status='done'
   - instagram_feeds.ad_copy_kor 저장
   - job.current_step = 'ad_copy_gen_kor', status = 'done'

10. instagram_feed_gen 실행 - YH 파트
    - txt_ad_copy_generations.ad_copy_kor 조회 (generation_stage='eng_to_kor')
    - job_inputs에서 tone_style, product_description 조회
    - jobs.store_id를 통해 stores 테이블에서 스토어 정보 조회
    - GPT API 호출: 인스타그램 피드글 생성
    - llm_traces 저장 (operation_type='feed_gen', request/response 포함)
    - instagram_feeds 테이블에 저장:
      * instagram_ad_copy=생성된 피드글
      * hashtags=생성된 해시태그
      * llm_trace_id=생성된 llm_trace_id 참조
      * job_id 연결
    - job.current_step = 'instagram_feed_gen', status = 'done'
```

---

## 🎯 최종 권장 방안

### ✅ **옵션 3: 파이프라인 단계 확장** (권장)

#### 1. 스키마 변경

**필요한 변경사항:**

**✅ job_inputs 테이블 확장:**
- ❌ `store_information` 컬럼 추가 불필요
- ✅ 스토어 정보는 `jobs.store_id`를 통해 `stores` 테이블에서 조회

**✅ txt_ad_copy_generations 테이블 신규 생성 (권장):**

**테이블 구조:**
```sql
CREATE TABLE txt_ad_copy_generations (
    ad_copy_gen_id UUID PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    llm_trace_id UUID REFERENCES llm_traces(llm_trace_id),  -- Trace 참조
    generation_stage TEXT NOT NULL,  -- 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
    ad_copy_kor TEXT,  -- 한글 광고문구 (최종)
    ad_copy_eng TEXT,  -- 영어 광고문구
    refined_ad_copy_eng TEXT,  -- 조정된 영어 광고문구
    status TEXT DEFAULT 'queued',  -- 'queued', 'running', 'done', 'failed'
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

**주요 특징:**
1. **단계별 추적**: `generation_stage`로 각 단계별 상태 관리
   - `'kor_to_eng'`: 한국어 → 영어 변환 (JS 파트)
   - `'ad_copy_eng'`: 영어 광고문구 생성 (JS 파트)
   - `'refined_ad_copy'`: 광고문구 조정 (YH 파트, 선택적)
   - `'eng_to_kor'`: 영어 → 한글 변환 (YH 파트)

2. **Trace 관리**: `llm_trace_id`로 `llm_traces`와 연결
   - 모든 GPT API 호출은 `llm_traces`에 기록
   - `txt_ad_copy_generations.llm_trace_id`로 각 단계의 Trace 참조
   - `vlm_traces`와 동일한 패턴으로 일관성 유지

3. **데이터 저장**: 각 단계별 광고문구 저장
   - `ad_copy_eng`: 영어 광고문구 (kor_to_eng, ad_copy_eng 단계)
   - `refined_ad_copy_eng`: 조정된 영어 광고문구 (refined_ad_copy 단계)
   - `ad_copy_kor`: 한글 광고문구 (eng_to_kor 단계)

4. **파트 분리 지원**: JS 파트와 YH 파트의 결과물을 한 테이블에서 관리
   - JS 파트: `kor_to_eng`, `ad_copy_eng` 단계
   - YH 파트: `refined_ad_copy`, `eng_to_kor` 단계

5. **Job 연결**: `job_id`로 이미지 처리와 같은 Job에 연결

**✅ instagram_feeds 테이블 확장:**
- `llm_trace_id` 컬럼 추가 (UUID, FK → llm_traces) - Trace 참조
- `ad_copy_kor` 컬럼 추가 (TEXT, nullable) - 한글 광고문구 저장용

**✅ llm_traces 테이블 활용:**
- `operation_type`에 새로운 값 추가: 'ad_copy_gen', 'eng_to_kor', 'feed_gen'
- 모든 GPT API 호출을 `llm_traces`에 기록
- `vlm_traces`와 동일한 패턴으로 관리

#### 2. 파이프라인 단계 추가 (다이어그램 기반)

**`services/pipeline_trigger.py` 수정:**

```python
PIPELINE_STAGES = {
    # 초기 단계 (Job 생성 시 또는 img_gen 전)
    ('job_created', 'queued'): {  # 또는 별도 트리거
        'next_step': 'desc_kor_translate',
        'api_endpoint': '/api/yh/gpt/kor-to-eng',
        'method': 'POST',
        'is_job_level': True,
        'runs_before_img_gen': True  # img_gen 전에 실행
    },
    ('desc_kor_translate', 'done'): {
        'next_step': 'ad_copy_gen_eng',
        'api_endpoint': '/api/yh/gpt/ad-copy-eng',
        'method': 'POST',
        'is_job_level': True,
        'runs_before_img_gen': True
    },
    
    # 중간 단계 (vlm_analyze 이후, 선택적)
    ('vlm_analyze', 'done'): {
        'next_step': 'refined_ad_copy',  # 선택적 단계
        'api_endpoint': '/api/yh/gpt/refine-ad-copy',
        'method': 'POST',
        'is_job_level': True,
        'is_optional': True  # 검증 결과에 따라 스킵 가능
    },
    
    # 기존 단계들...
    ('refined_ad_copy', 'done'): {
        'next_step': 'yolo_detect',
        'api_endpoint': '/api/yh/yolo/detect',
        'method': 'POST',
        'is_job_level': False  # variant별 실행
    },
    
    # 최종 단계 (iou_eval 이후)
    ('iou_eval', 'done'): {
        'next_step': 'ad_copy_gen_kor',
        'api_endpoint': '/api/yh/gpt/eng-to-kor',
        'method': 'POST',
        'is_job_level': True
    },
    ('ad_copy_gen_kor', 'done'): {
        'next_step': 'instagram_feed_gen',
        'api_endpoint': '/api/yh/instagram/feed',
        'method': 'POST',
        'is_job_level': True
    },
}
```

#### 3. API 엔드포인트 수정 (다이어그램 기반)

**초기 단계 API:**

**`/api/js/gpt/kor-to-eng` (신규 생성, JS 파트):**
- `job_id`, `tenant_id` 파라미터 (필수)
- `job_inputs.desc_kor` 조회
- GPT API 호출: 한국어 → 영어 변환
- `llm_traces` 저장 (operation_type='kor_to_eng', request/response 포함)
- `txt_ad_copy_generations` 레코드 생성:
  * generation_stage='kor_to_eng'
  * ad_copy_eng=영어 설명 (변환 결과)
  * llm_trace_id=생성된 llm_trace_id 참조
  * status='done'
- `job_inputs.desc_eng` 업데이트
- `job.current_step = 'desc_kor_translate'`, `job.status = 'done'` 업데이트

**`/api/js/gpt/ad-copy-eng` (신규 생성, JS 파트):**
- `job_id`, `tenant_id` 파라미터 (필수)
- `job_inputs.desc_eng`, `tone_style_id` 조회
- GPT API 실제 구현: 영어 광고문구 생성
- `llm_traces` 저장 (operation_type='ad_copy_gen', request/response 포함)
- `txt_ad_copy_generations` 레코드 생성/업데이트:
  * generation_stage='ad_copy_eng'
  * ad_copy_eng=영어 광고문구 (생성 결과)
  * llm_trace_id=생성된 llm_trace_id 참조
  * status='done'
- `job.current_step = 'ad_copy_gen_eng'`, `job.status = 'done'` 업데이트

**중간 단계 API:**

**`/api/yh/gpt/refine-ad-copy` (신규 생성, YH 파트, 선택적):**
- `job_id`, `tenant_id` 파라미터 (필수)
- `txt_ad_copy_generations.ad_copy_eng` 조회 (generation_stage='ad_copy_eng')
- `vlm_traces`에서 `vlm_analyze` 검증 결과 조회
- 검증 결과가 불만족스러우면:
  * GPT API 호출: 광고문구 조정
  * `llm_traces` 저장 (operation_type='ad_copy_gen', refined, request/response 포함)
  * `txt_ad_copy_generations` 레코드 업데이트:
    - generation_stage='refined_ad_copy'
    - refined_ad_copy_eng=조정된 영어 광고문구
    - llm_trace_id=생성된 llm_trace_id 참조
    - status='done'
  * `job.current_step = 'refined_ad_copy'`, `job.status = 'done'` 업데이트
- 검증 결과가 만족스러우면 스킵

**최종 단계 API:**

**`/api/yh/gpt/eng-to-kor` (신규 생성, YH 파트):**
- `job_id`, `tenant_id` 파라미터 (필수)
- `txt_ad_copy_generations` 조회:
  * refined_ad_copy_eng이 있으면 → refined_ad_copy_eng 사용
  * 없으면 → ad_copy_eng 사용
- GPT API 호출: 영어 → 한글 변환
- `llm_traces` 저장 (operation_type='eng_to_kor', request/response 포함)
- `txt_ad_copy_generations` 레코드 생성/업데이트:
  * generation_stage='eng_to_kor'
  * ad_copy_kor=한글 광고문구 (변환 결과)
  * llm_trace_id=생성된 llm_trace_id 참조
  * status='done'
- `instagram_feeds.ad_copy_kor` 저장
- `job.current_step = 'ad_copy_gen_kor'`, `job.status = 'done'` 업데이트

**`/api/yh/instagram/feed` 수정 (YH 파트):**
- `job_id`, `tenant_id` 파라미터 필수화
- `txt_ad_copy_generations.ad_copy_kor` 조회 (generation_stage='eng_to_kor')
- `job_inputs`에서 `tone_style`, `product_description` 조회
- `jobs.store_id`를 통해 `stores` 테이블에서 스토어 정보 조회
- GPT API 호출: 인스타그램 피드글 생성
- `llm_traces` 저장 (operation_type='feed_gen', request/response 포함)
- `instagram_feeds` 테이블에 저장:
  * instagram_ad_copy=생성된 피드글
  * hashtags=생성된 해시태그
  * llm_trace_id=생성된 llm_trace_id 참조
  * job_id 연결
- `job.current_step = 'instagram_feed_gen'`, `job.status = 'done'` 업데이트

#### 4. 트리거 로직 수정

**`services/job_state_listener.py` 수정:**
- Job 레벨 단계(`is_job_level=True`)는 `jobs` 테이블 변경 시에만 트리거
- `jobs_variants` 변경 시에는 트리거하지 않음

#### 5. 광고문구 저장 위치 (다이어그램 기반, txt_ad_copy_generations 테이블 제안)

**✅ 권장 방안: `txt_ad_copy_generations` 테이블 신규 생성**

**구조:**
- `txt_ad_copy_generations`: 광고문구 생성 과정의 모든 단계 추적
  - `generation_stage`: 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
  - `ad_copy_kor`: 한글 광고문구 (최종)
  - `ad_copy_eng`: 영어 광고문구
  - `refined_ad_copy_eng`: 조정된 영어 광고문구
  - `llm_trace_id`: 각 단계별 `llm_traces` 참조

**장점:**
1. **명확한 단계 추적**: `generation_stage`로 각 단계별 상태 관리
2. **Trace 관리**: `llm_trace_id`로 `llm_traces`와 연결, `vlm_traces`와 동일한 패턴
3. **데이터 분리**: 광고문구 생성 과정을 별도 테이블로 관리
4. **파트 분리 지원**: JS 파트와 YH 파트의 결과물을 명확히 구분
5. **재사용성**: 같은 Job에서 여러 단계의 광고문구를 추적 가능

**데이터 흐름:**
```
[JS 파트]
job_inputs.desc_kor (사용자 입력)
  ↓
llm_traces (operation_type='kor_to_eng')
  ↓
txt_ad_copy_generations (generation_stage='kor_to_eng', ad_copy_eng=영어 설명)
  ↓
llm_traces (operation_type='ad_copy_gen')
  ↓
txt_ad_copy_generations (generation_stage='ad_copy_eng', ad_copy_eng=영어 광고문구)

[YH 파트]
  ↓
vlm_analyze 검증
  ↓
(선택적) txt_ad_copy_generations (generation_stage='refined_ad_copy', refined_ad_copy_eng)
  ↓
llm_traces (operation_type='eng_to_kor')
  ↓
txt_ad_copy_generations (generation_stage='eng_to_kor', ad_copy_kor=한글 광고문구)
  ↓
llm_traces (operation_type='feed_gen')
  ↓
instagram_feeds (instagram_ad_copy=최종 피드글, llm_trace_id 참조)
```

**Trace 관리:**
- 모든 GPT API 호출은 `llm_traces`에 기록
- `txt_ad_copy_generations.llm_trace_id`로 각 단계의 Trace 참조
- `vlm_traces`와 동일한 패턴으로 일관성 유지

---

## 📊 데이터 흐름도 (다이어그램 기반, Trace 관리 포함)

```
[Phase 1: 초기 텍스트 생성 - JS 파트]
[사용자 입력]
  - 이미지, 한국어 설명 (30자), Tone & Style, Store Information
  ↓
job_inputs 테이블 저장
  - desc_kor, tone_style_id
  - jobs.store_id (stores 테이블 조회용)
  ↓
[JS 파트: /api/js/gpt/kor-to-eng]
  - job_inputs.desc_kor 조회
  - GPT API: 한국어 → 영어 변환
  - llm_traces 저장 (operation_type='kor_to_eng')
  - txt_ad_copy_generations 저장 (generation_stage='kor_to_eng', ad_copy_eng=영어 설명)
  - job_inputs.desc_eng 업데이트
  ↓
[JS 파트: /api/js/gpt/ad-copy-eng]
  - job_inputs.desc_eng, tone_style_id 조회
  - GPT API: 영어 광고문구 생성
  - llm_traces 저장 (operation_type='ad_copy_gen')
  - txt_ad_copy_generations 저장/업데이트 (generation_stage='ad_copy_eng', ad_copy_eng=영어 광고문구)
  ↓
[Phase 2: 이미지 처리 파이프라인 - YH 파트]
[파이프라인 시작]
  ↓
img_gen (done)
  ↓
[YH 파트: vlm_analyze]
  - txt_ad_copy_generations.ad_copy_eng 조회
  - 생성된 이미지와 광고문구 검증
  - vlm_traces 저장 (operation_type='analyze')
  - 검증 결과 저장
  ↓
[선택적: refined_ad_copy - YH 파트]
  - 검증 결과가 불만족스러우면
  - GPT API: 광고문구 조정
  - llm_traces 저장 (operation_type='ad_copy_gen', refined)
  - txt_ad_copy_generations 업데이트 (generation_stage='refined_ad_copy', refined_ad_copy_eng)
  ↓
... (기존 파이프라인: yolo_detect → planner → overlay → 평가 단계들) ...
  ↓
iou_eval 완료
  ↓
[Phase 3: 최종 텍스트 생성 - YH 파트]
[YH 파트: /api/yh/gpt/eng-to-kor]
  - txt_ad_copy_generations.ad_copy_eng 또는 refined_ad_copy_eng 조회
  - GPT API: 영어 → 한글 변환
  - llm_traces 저장 (operation_type='eng_to_kor')
  - txt_ad_copy_generations 저장/업데이트 (generation_stage='eng_to_kor', ad_copy_kor=한글 광고문구)
  - instagram_feeds.ad_copy_kor 저장
  - job.current_step = 'ad_copy_gen_kor', status = 'done'
  ↓
[YH 파트: /api/yh/instagram/feed]
  - txt_ad_copy_generations.ad_copy_kor 조회
  - job_inputs에서 tone_style, product_description 조회
  - jobs.store_id를 통해 stores 테이블에서 스토어 정보 조회
  - GPT API: 인스타그램 피드글 생성
  - llm_traces 저장 (operation_type='feed_gen')
  - instagram_feeds 테이블에 저장 (llm_trace_id 포함, 완전한 데이터)
  - job.current_step = 'instagram_feed_gen', status = 'done'
  ↓
[완료]
```

**Trace 관리:**
- 모든 GPT API 호출은 `llm_traces`에 기록
- `txt_ad_copy_generations.llm_trace_id`로 각 단계의 Trace 참조
- `instagram_feeds.llm_trace_id`로 최종 피드글 생성 Trace 참조
- `vlm_traces`와 동일한 패턴으로 일관성 유지

---

## 🔧 구현 체크리스트

### 1. 스키마 변경
- [ ] 스토어 정보 조회 방법 확인 (`jobs.store_id` → `stores` 테이블)
- [ ] `txt_ad_copy_generations` 테이블 신규 생성
  - [ ] `ad_copy_gen_id` (UUID, PK)
  - [ ] `job_id` (UUID, FK → jobs)
  - [ ] `llm_trace_id` (UUID, FK → llm_traces)
  - [ ] `generation_stage` (TEXT): 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
  - [ ] `ad_copy_kor` (TEXT, nullable)
  - [ ] `ad_copy_eng` (TEXT, nullable)
  - [ ] `refined_ad_copy_eng` (TEXT, nullable)
  - [ ] `status` (TEXT): 'queued', 'running', 'done', 'failed'
  - [ ] 인덱스: `idx_txt_ad_copy_generations_job_id`, `idx_txt_ad_copy_generations_llm_trace_id`, `idx_txt_ad_copy_generations_generation_stage`
- [ ] `instagram_feeds` 테이블 확장
  - [ ] `llm_trace_id` 컬럼 추가 (UUID, FK → llm_traces)
  - [ ] `ad_copy_kor` 컬럼 추가 (TEXT, nullable)
  - [ ] 인덱스: `idx_instagram_feeds_llm_trace_id`
- [ ] `llm_traces` 테이블 확인
  - [ ] `operation_type`에 새 값 지원 확인: 'ad_copy_gen', 'eng_to_kor', 'feed_gen'

### 2. API 엔드포인트 수정 (다이어그램 기반, Trace 관리 포함)

**JS 파트 (별도 구현 필요):**
- [ ] `/api/js/gpt/kor-to-eng` (JS 파트)
  - [ ] `job_id`, `tenant_id` 파라미터 (필수)
  - [ ] `job_inputs.desc_kor` 조회 및 GPT API 호출
  - [ ] `llm_traces`에 기록 (operation_type='kor_to_eng')
  - [ ] `txt_ad_copy_generations` 레코드 생성 (generation_stage='kor_to_eng')
  - [ ] `job_inputs.desc_eng` 업데이트
- [ ] `/api/js/gpt/ad-copy-eng` (JS 파트)
  - [ ] `job_id`, `tenant_id` 파라미터 (필수)
  - [ ] `job_inputs`에서 데이터 조회
  - [ ] GPT API 호출
  - [ ] `llm_traces`에 기록 (operation_type='ad_copy_gen')
  - [ ] `txt_ad_copy_generations` 레코드 생성/업데이트 (generation_stage='ad_copy_eng')

**YH 파트:**
- [ ] `/api/yh/gpt/refine-ad-copy` 신규 생성 (선택적)
  - [ ] `job_id`, `tenant_id` 파라미터 (필수)
  - [ ] `vlm_analyze` 검증 결과 조회
  - [ ] 조건부 실행 로직 구현
  - [ ] GPT API 호출
  - [ ] `llm_traces`에 기록 (operation_type='ad_copy_gen', refined)
  - [ ] `txt_ad_copy_generations` 레코드 업데이트 (generation_stage='refined_ad_copy')
- [ ] `/api/yh/gpt/eng-to-kor` 신규 생성
  - [ ] `job_id`, `tenant_id` 파라미터 (필수)
  - [ ] `txt_ad_copy_generations`에서 `ad_copy_eng` 또는 `refined_ad_copy_eng` 조회
  - [ ] GPT API 호출
  - [ ] `llm_traces`에 기록 (operation_type='eng_to_kor')
  - [ ] `txt_ad_copy_generations` 레코드 생성/업데이트 (generation_stage='eng_to_kor')
  - [ ] `instagram_feeds.ad_copy_kor` 저장
  - [ ] `jobs` 테이블 업데이트
- [ ] `/api/yh/instagram/feed` 수정
  - [ ] `job_id`, `tenant_id` 파라미터 필수화
  - [ ] `txt_ad_copy_generations.ad_copy_kor` 조회
  - [ ] `job_inputs`에서 추가 데이터 조회
  - [ ] GPT API 호출
  - [ ] `llm_traces`에 기록 (operation_type='feed_gen')
  - [ ] `instagram_feeds` 테이블에 저장 (`llm_trace_id` 포함)
  - [ ] `jobs` 테이블 업데이트

### 3. 파이프라인 트리거 수정
- [ ] `services/pipeline_trigger.py`에 새 단계 추가
- [ ] Job 레벨 단계 처리 로직 추가
- [ ] `services/job_state_listener.py` 수정
  - [ ] Job 레벨 단계는 `jobs` 테이블 변경 시에만 트리거

### 4. 트리거 함수 수정
- [ ] `db/init/03_job_variants_state_notify_trigger.sql` 확인
- [ ] Job 레벨 단계는 `jobs` 테이블 트리거 사용 (기존 `02_job_state_notify_trigger.sql` 활용)

### 5. 테스트
- [ ] 전체 파이프라인 테스트
- [ ] Job 레벨 단계 자동 실행 확인
- [ ] 데이터 저장 확인

---

## ❓ 질문 및 고려사항

### 1. 광고문구 저장 위치
- **질문**: 각 단계의 광고문구를 어디에 저장할까?
- **제안**: 
  - **`txt_ad_copy_generations` 테이블 신규 생성** (권장)
  - **장점**: 
    - 광고문구 생성 과정의 모든 단계를 한 테이블에서 추적
    - `llm_trace_id`로 Trace 관리 (`vlm_traces`와 동일한 패턴)
    - `generation_stage`로 단계별 상태 관리
    - 파트 분리 지원 (JS 파트와 YH 파트 결과물 구분)
    - 재사용성 및 확장성

### 2. 스토어 정보 조회 방법
- **질문**: `store_information`을 어디서 조회할까?
- **제안**: `jobs.store_id`를 통해 `stores` 테이블에서 조회
  - `stores.title`: 스토어 제목
  - `stores.body`: 스토어 설명
  - `stores.store_category`: 스토어 카테고리
  - `job_inputs` 테이블에 `store_information` 컬럼 추가 불필요

### 3. Job 레벨 단계 트리거
- **질문**: Job 레벨 단계는 어떤 트리거를 사용할까?
- **제안**: 기존 `jobs` 테이블 트리거 활용 (`02_job_state_notify_trigger.sql`)

### 4. Variant별 처리
- **질문**: 광고문구와 피드글은 variant별로 생성할까?
- **제안**: **Job 레벨에서 한 번만 생성** (이미지와 달리 텍스트는 variant별 차이 없음)
- **예외**: `vlm_analyze`는 variant별로 실행되지만, 광고문구는 Job 레벨에서 한 번만 생성되어 모든 variant에 공통으로 사용

### 5. 초기 단계 실행 시점
- **질문**: `desc_kor_translate`와 `ad_copy_gen_eng`은 언제 실행할까?
- **제안**: 
  - **옵션 A**: Job 생성 직후 실행 (img_gen 전)
  - **옵션 B**: img_gen 완료 후 실행 (vlm_analyze 전)
  - **권장**: **옵션 A** (Job 생성 직후) - vlm_analyze에서 광고문구가 필요하므로

### 6. Trace 관리
- **질문**: GPT API 호출을 어떻게 추적할까?
- **제안**: 
  - **`llm_traces` 테이블 활용** (`vlm_traces`와 동일한 패턴)
  - 모든 GPT API 호출을 `llm_traces`에 기록
  - `operation_type`에 새 값 추가: 'ad_copy_gen', 'eng_to_kor', 'feed_gen'
  - `txt_ad_copy_generations.llm_trace_id`로 각 단계의 Trace 참조
  - `instagram_feeds.llm_trace_id`로 최종 피드글 생성 Trace 참조

### 7. 파트 분리
- **질문**: JS 파트와 YH 파트를 어떻게 구분할까?
- **제안**: 
  - **JS 파트**: `/api/js/gpt/*` 엔드포인트 (별도 구현)
  - **YH 파트**: `/api/yh/gpt/*` 엔드포인트 (기존 구조)
  - **데이터 공유**: `txt_ad_copy_generations` 테이블로 중간 결과물 공유
  - **Trace 관리**: 모든 파트의 GPT API 호출을 `llm_traces`에 기록

---

## 📝 결론

### ✅ **최종 권장 방안: 파이프라인 단계 확장 (다이어그램 기반, txt_ad_copy_generations 테이블 추가)**

1. **별도 DB 불필요**: 현재 구조로 충분
2. **별도 Job 불필요**: 같은 Job에 통합 (`job_id` 공유)
3. **자동화**: 파이프라인 트리거로 자동 실행
4. **Trace 관리**: `llm_traces` 테이블 활용 (`vlm_traces`와 동일한 패턴)
5. **명확한 데이터 흐름**: 
   - 입력 데이터 → `job_inputs` 테이블
   - 광고문구 생성 과정 → `txt_ad_copy_generations` 테이블 (신규)
   - 최종 결과물 → `instagram_feeds` 테이블
6. **파트 분리 지원**: JS 파트와 YH 파트의 결과물을 `txt_ad_copy_generations`로 공유

### 구현 우선순위

1. **Phase 1**: 스키마 변경 (`job_inputs`, `instagram_feeds` 컬럼 추가)
2. **Phase 2**: 초기 단계 API 구현 (`kor-to-eng`, `ad-copy-eng`)
3. **Phase 3**: 파이프라인 단계 추가 및 트리거 로직 수정
4. **Phase 4**: 중간 단계 API 구현 (`refine-ad-copy`, 선택적)
5. **Phase 5**: 최종 단계 API 구현 (`eng-to-kor`, `instagram-feed`)
6. **Phase 6**: 테스트 및 검증

---

## 📚 참고 문서

- `scripts/DOCS_PIPELINE_AUTO_TRIGGER.md`: 파이프라인 자동 트리거 문서
- `DOCS_INSTAGRAM_FEED.md`: 인스타그램 피드 생성 문서
- `ANALYSIS_JOB_VARIANTS_PIPELINE.md`: Job Variants 파이프라인 분석


# YH 파트 구현 가이드

## 📋 개요

이 문서는 **YH 파트**에서 구현해야 할 광고문구 및 인스타그램 피드 생성 관련 기능에 대한 가이드입니다.

**작성일**: 2025-12-01  
**버전**: 1.0.0  
**작성자**: LEEYH205

---

## 🎯 YH 파트 담당 범위

YH 파트는 다음 세 단계를 담당합니다:

1. **`vlm_analyze`**: 생성된 이미지와 광고문구 검증 (기존 구현, 수정 필요)
2. **`refined_ad_copy`**: 광고문구 조정 (선택적, 신규)
3. **`eng_to_kor`**: 영어 광고문구 → 한글 변환 (신규)
4. **`instagram_feed_gen`**: 인스타그램 피드글 생성 (기존 구현, 수정 필요)

---

## 📊 데이터베이스 구조

### 1. 관련 테이블

#### `txt_ad_copy_generations` 테이블 (JS 파트가 생성)
- `ad_copy_gen_id` (UUID, PK)
- `job_id` (UUID, FK → jobs)
- `llm_trace_id` (UUID, FK → llm_traces)
- `generation_stage` (TEXT): 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
- `ad_copy_eng` (TEXT): 영어 광고문구 (JS 파트에서 생성)
- `refined_ad_copy_eng` (TEXT): 조정된 영어 광고문구 (YH 파트에서 생성, 선택적)
- `ad_copy_kor` (TEXT): 한글 광고문구 (YH 파트에서 생성)
- `status` (TEXT)

#### `jobs` 테이블
- `job_id` (UUID, PK)
- `store_id` (UUID, FK → stores): 스토어 ID

#### `stores` 테이블
- `store_id` (UUID, PK)
- `title` (VARCHAR): 스토어 제목
- `body` (TEXT): 스토어 설명
- `store_category` (TEXT): 스토어 카테고리
- **참고**: 스토어 정보는 `jobs.store_id`를 통해 `stores` 테이블에서 조회

#### `instagram_feeds` 테이블
- `instagram_feed_id` (UUID, PK)
- `job_id` (UUID, FK → jobs)
- `llm_trace_id` (UUID, FK → llm_traces): 신규 추가
- `ad_copy_kor` (TEXT): 한글 광고문구 (신규 추가)
- `instagram_ad_copy` (TEXT): 생성된 인스타그램 피드 글
- `hashtags` (TEXT): 해시태그

#### `llm_traces` 테이블
- `llm_trace_id` (UUID, PK)
- `job_id` (UUID, FK → jobs)
- `provider` (TEXT): 'gpt'
- `operation_type` (TEXT): 'ad_copy_gen' (refined), 'eng_to_kor', 'feed_gen'
- `request` (JSONB)
- `response` (JSONB)
- `latency_ms` (FLOAT)

---

## 🔧 구현해야 할 API 엔드포인트

### 1. `/api/yh/llava/stage1/validate` (기존 수정)

**수정 사항**: `txt_ad_copy_generations` 테이블에서 광고문구 조회

**기존 코드:**
```python
# job_inputs에서 광고 텍스트 가져오기
job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
ad_copy_text = body.ad_copy_text if body.ad_copy_text else (job_input.desc_eng if job_input else None)
```

**수정 후:**
```python
# txt_ad_copy_generations에서 광고문구 조회 (우선순위)
ad_copy_gen = db.execute(
    text("""
        SELECT ad_copy_eng
        FROM txt_ad_copy_generations
        WHERE job_id = :job_id
          AND generation_stage = 'ad_copy_eng'
          AND status = 'done'
        ORDER BY created_at DESC
        LIMIT 1
    """),
    {"job_id": job_id}
).first()

if ad_copy_gen and ad_copy_gen.ad_copy_eng:
    ad_copy_text = ad_copy_gen.ad_copy_eng
elif body.ad_copy_text:
    ad_copy_text = body.ad_copy_text
else:
    # Fallback: job_inputs에서 조회
    job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
    ad_copy_text = job_input.desc_eng if job_input else None
```

---

### 2. `/api/yh/gpt/refine-ad-copy` (신규 생성, 선택적)

**목적**: `vlm_analyze` 검증 결과에 따라 광고문구 조정

**요청 (Request):**
```json
{
  "job_id": "uuid-string",
  "tenant_id": "string"
}
```

**처리 과정:**
1. `vlm_traces` 테이블에서 `vlm_analyze` 검증 결과 조회:
   ```sql
   SELECT response
   FROM vlm_traces
   WHERE job_id = :job_id
     AND operation_type = 'analyze'
   ORDER BY created_at DESC
   LIMIT 1
   ```
2. 검증 결과 분석:
   - `is_valid = False` 또는 `relevance_score < 0.7`이면 조정 필요
   - 만족스러우면 스킵
3. `txt_ad_copy_generations` 테이블에서 현재 광고문구 조회:
   ```sql
   SELECT ad_copy_eng
   FROM txt_ad_copy_generations
   WHERE job_id = :job_id
     AND generation_stage = 'ad_copy_eng'
     AND status = 'done'
   ```
4. GPT API 호출: 광고문구 조정
   - 입력: 현재 광고문구 + 검증 결과 이슈
   - 출력: 조정된 영어 광고문구
5. `llm_traces` 테이블에 기록:
   ```sql
   INSERT INTO llm_traces (
       llm_trace_id, job_id, provider, operation_type,
       request, response, latency_ms, created_at, updated_at
   ) VALUES (
       :llm_trace_id, :job_id, 'gpt', 'ad_copy_gen',
       CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
6. `txt_ad_copy_generations` 테이블에 레코드 생성/업데이트:
   ```sql
   INSERT INTO txt_ad_copy_generations (
       ad_copy_gen_id, job_id, llm_trace_id, generation_stage,
       refined_ad_copy_eng, status, created_at, updated_at
   ) VALUES (
       :ad_copy_gen_id, :job_id, :llm_trace_id, 'refined_ad_copy',
       :refined_ad_copy_eng, 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
7. `jobs` 테이블 업데이트:
   ```sql
   UPDATE jobs
   SET current_step = 'refined_ad_copy',
       status = 'done',
       updated_at = CURRENT_TIMESTAMP
   WHERE job_id = :job_id
   ```

**응답 (Response):**
```json
{
  "job_id": "uuid-string",
  "llm_trace_id": "uuid-string",
  "ad_copy_gen_id": "uuid-string",
  "refined_ad_copy_eng": "Refined English ad copy text",
  "status": "done"
}
```

---

### 3. `/api/yh/gpt/eng-to-kor` (신규 생성)

**목적**: 영어 광고문구를 한글로 변환

**요청 (Request):**
```json
{
  "job_id": "uuid-string",
  "tenant_id": "string"
}
```

**처리 과정:**
1. `txt_ad_copy_generations` 테이블에서 영어 광고문구 조회:
   ```sql
   SELECT 
       COALESCE(refined_ad_copy_eng, ad_copy_eng) AS ad_copy_eng
   FROM txt_ad_copy_generations
   WHERE job_id = :job_id
     AND (generation_stage = 'refined_ad_copy' OR generation_stage = 'ad_copy_eng')
     AND status = 'done'
   ORDER BY 
       CASE generation_stage
           WHEN 'refined_ad_copy' THEN 1
           WHEN 'ad_copy_eng' THEN 2
       END
   LIMIT 1
   ```
   - `refined_ad_copy_eng`이 있으면 우선 사용
   - 없으면 `ad_copy_eng` 사용
2. GPT API 호출: 영어 → 한글 변환
3. `llm_traces` 테이블에 기록:
   ```sql
   INSERT INTO llm_traces (
       llm_trace_id, job_id, provider, operation_type,
       request, response, latency_ms, created_at, updated_at
   ) VALUES (
       :llm_trace_id, :job_id, 'gpt', 'eng_to_kor',
       CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
4. `txt_ad_copy_generations` 테이블에 레코드 생성/업데이트:
   ```sql
   INSERT INTO txt_ad_copy_generations (
       ad_copy_gen_id, job_id, llm_trace_id, generation_stage,
       ad_copy_kor, status, created_at, updated_at
   ) VALUES (
       :ad_copy_gen_id, :job_id, :llm_trace_id, 'eng_to_kor',
       :ad_copy_kor, 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
5. `instagram_feeds.ad_copy_kor` 저장:
   ```sql
   UPDATE instagram_feeds
   SET ad_copy_kor = :ad_copy_kor,
       updated_at = CURRENT_TIMESTAMP
   WHERE job_id = :job_id
   ```
   또는 새 레코드 생성
6. `jobs` 테이블 업데이트:
   ```sql
   UPDATE jobs
   SET current_step = 'ad_copy_gen_kor',
       status = 'done',
       updated_at = CURRENT_TIMESTAMP
   WHERE job_id = :job_id
   ```

**응답 (Response):**
```json
{
  "job_id": "uuid-string",
  "llm_trace_id": "uuid-string",
  "ad_copy_gen_id": "uuid-string",
  "ad_copy_kor": "한글 광고문구",
  "status": "done"
}
```

---

### 4. `/api/yh/instagram/feed` (기존 수정)

**수정 사항**: 
- `job_id`, `tenant_id` 파라미터 필수화
- `txt_ad_copy_generations`에서 한글 광고문구 조회
- `llm_traces` 저장 추가
- `instagram_feeds.llm_trace_id` 저장 추가

**요청 (Request):**
```json
{
  "job_id": "uuid-string",
  "tenant_id": "string"
}
```

**처리 과정:**
1. `txt_ad_copy_generations` 테이블에서 한글 광고문구 조회:
   ```sql
   SELECT ad_copy_kor
   FROM txt_ad_copy_generations
   WHERE job_id = :job_id
     AND generation_stage = 'eng_to_kor'
     AND status = 'done'
   ```
2. `job_inputs` 테이블에서 추가 데이터 조회:
   - `tone_style_id` → `tone_styles` 테이블에서 톤 & 스타일 정보
   - `desc_kor`: 제품 설명
3. `jobs.store_id`를 통해 `stores` 테이블에서 스토어 정보 조회:
   ```sql
   SELECT s.title, s.body, s.store_category
   FROM jobs j
   INNER JOIN stores s ON j.store_id = s.store_id
   WHERE j.job_id = :job_id
   ```
   - `stores.title`: 스토어 제목
   - `stores.body`: 스토어 설명 (스토어 정보로 사용)
   - `stores.store_category`: 스토어 카테고리
   - **참고**: `job_inputs` 테이블에 `store_information` 컬럼 추가 불필요
3. GPT API 호출: 인스타그램 피드글 생성
4. `llm_traces` 테이블에 기록:
   ```sql
   INSERT INTO llm_traces (
       llm_trace_id, job_id, provider, operation_type,
       request, response, latency_ms, created_at, updated_at
   ) VALUES (
       :llm_trace_id, :job_id, 'gpt', 'feed_gen',
       CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
5. `instagram_feeds` 테이블에 저장:
   ```sql
   INSERT INTO instagram_feeds (
       instagram_feed_id, job_id, llm_trace_id, llm_model_id,
       tenant_id, refined_ad_copy_eng, ad_copy_kor, tone_style,
       product_description, store_information, gpt_prompt,  -- store_information은 stores 테이블에서 조회한 정보
       instagram_ad_copy, hashtags, used_temperature, used_max_tokens,
       gpt_prompt_used, gpt_response_raw, latency_ms,
       prompt_tokens, completion_tokens, total_tokens, token_usage,
       created_at, updated_at
   ) VALUES (
       :instagram_feed_id, :job_id, :llm_trace_id, :llm_model_id,
       :tenant_id, :refined_ad_copy_eng, :ad_copy_kor, :tone_style,
       :product_description, :store_information, :gpt_prompt,  -- store_information은 stores 테이블에서 조회한 정보
       :instagram_ad_copy, :hashtags, :used_temperature, :used_max_tokens,
       :gpt_prompt_used, CAST(:gpt_response_raw AS jsonb), :latency_ms,
       :prompt_tokens, :completion_tokens, :total_tokens, CAST(:token_usage AS jsonb),
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
6. `jobs` 테이블 업데이트:
   ```sql
   UPDATE jobs
   SET current_step = 'instagram_feed_gen',
       status = 'done',
       updated_at = CURRENT_TIMESTAMP
   WHERE job_id = :job_id
   ```

**응답 (Response):**
```json
{
  "instagram_feed_id": "uuid-string",
  "job_id": "uuid-string",
  "llm_trace_id": "uuid-string",
  "instagram_ad_copy": "인스타그램 피드 글",
  "hashtags": "#태그1 #태그2 #태그3",
  "status": "done"
}
```

---

## 🔄 파이프라인 트리거 수정

### `services/pipeline_trigger.py` 수정

**추가할 단계:**
```python
PIPELINE_STAGES = {
    # ... 기존 단계들 ...
    
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

---

## 📝 구현 체크리스트

### 1. 스키마 마이그레이션
- [ ] `db/init/06_add_ad_copy_generations.sql` 실행 확인
- [ ] `txt_ad_copy_generations` 테이블 생성 확인
- [ ] `instagram_feeds.llm_trace_id` 컬럼 추가 확인
- [ ] `instagram_feeds.ad_copy_kor` 컬럼 추가 확인
- [ ] 스토어 정보 조회 방법 확인 (`jobs.store_id` → `stores` 테이블)

### 2. 기존 API 수정
- [ ] `/api/yh/llava/stage1/validate` 수정
  - [ ] `txt_ad_copy_generations`에서 광고문구 조회 로직 추가
  - [ ] Fallback 로직 유지 (하위 호환성)
- [ ] `/api/yh/instagram/feed` 수정
  - [ ] `job_id`, `tenant_id` 파라미터 필수화
  - [ ] `txt_ad_copy_generations.ad_copy_kor` 조회
  - [ ] `llm_traces` 저장 추가
  - [ ] `instagram_feeds.llm_trace_id` 저장 추가

### 3. 신규 API 구현
- [ ] `/api/yh/gpt/refine-ad-copy` 구현
  - [ ] `vlm_traces`에서 검증 결과 조회
  - [ ] 조건부 실행 로직 (검증 결과에 따라 스킵)
  - [ ] GPT API 호출 및 `llm_traces` 저장
  - [ ] `txt_ad_copy_generations` 레코드 생성/업데이트
- [ ] `/api/yh/gpt/eng-to-kor` 구현
  - [ ] `txt_ad_copy_generations`에서 영어 광고문구 조회
  - [ ] GPT API 호출 및 `llm_traces` 저장
  - [ ] `txt_ad_copy_generations` 레코드 생성/업데이트
  - [ ] `instagram_feeds.ad_copy_kor` 저장

### 4. 파이프라인 트리거 수정
- [ ] `services/pipeline_trigger.py`에 새 단계 추가
- [ ] Job 레벨 단계 처리 로직 확인
- [ ] 선택적 단계(`refined_ad_copy`) 처리 로직 구현

### 5. Trace 관리
- [ ] 모든 GPT API 호출을 `llm_traces`에 기록
- [ ] `txt_ad_copy_generations.llm_trace_id` 연결
- [ ] `instagram_feeds.llm_trace_id` 연결
- [ ] `vlm_traces`와 동일한 패턴으로 일관성 유지

### 6. 테스트
- [ ] 전체 파이프라인 테스트
- [ ] JS 파트와 YH 파트 연동 테스트
- [ ] `txt_ad_copy_generations` 데이터 저장/조회 테스트
- [ ] Trace 관리 테스트

---

## 🔗 JS 파트와의 연동

### 데이터 공유
- **JS 파트가 생성한 데이터**: `txt_ad_copy_generations` 테이블에서 조회
  - `generation_stage='ad_copy_eng'`: 영어 광고문구
- **YH 파트가 생성하는 데이터**: `txt_ad_copy_generations` 테이블에 저장
  - `generation_stage='refined_ad_copy'`: 조정된 영어 광고문구 (선택적)
  - `generation_stage='eng_to_kor'`: 한글 광고문구

### 실행 시점
- **`vlm_analyze`**: `img_gen` 완료 후 실행 (기존)
- **`refined_ad_copy`**: `vlm_analyze` 완료 후, 검증 결과에 따라 선택적 실행
- **`eng_to_kor`**: `iou_eval` 완료 후 실행
- **`instagram_feed_gen`**: `eng_to_kor` 완료 후 실행

---

## 📚 참고 문서

- `ANALYSIS_INSTAGRAM_FEED_PIPELINE_INTEGRATION.md`: 전체 파이프라인 분석 문서
- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `db/init/01_schema.sql`: 데이터베이스 스키마
- `db/init/06_add_ad_copy_generations.sql`: 마이그레이션 스크립트

---

## ⚠️ 주의사항

1. **하위 호환성**: 기존 코드와의 호환성을 유지하기 위해 Fallback 로직 구현
2. **Trace 관리**: 모든 GPT API 호출은 반드시 `llm_traces`에 기록
3. **에러 처리**: 각 단계에서 실패 시 적절한 에러 처리 및 재시도 로직 구현
4. **데이터 일관성**: `txt_ad_copy_generations` 레코드 생성 시 `job_id`와 `generation_stage` 조합이 유일해야 함


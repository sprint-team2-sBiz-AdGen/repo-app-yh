# JS 파트 구현 가이드

## 📋 개요

이 문서는 **JS 파트**에서 구현해야 할 광고문구 생성 관련 기능에 대한 가이드입니다.

**작성일**: 2025-12-01  
**버전**: 1.0.0  
**작성자**: LEEYH205

---

## 🎯 JS 파트 담당 범위

JS 파트는 다음 두 단계를 담당합니다:

1. **`kor_to_eng`**: 한국어 설명 → 영어 변환
2. **`ad_copy_eng`**: 영어 광고문구 생성

---

## 📊 데이터베이스 구조

### 1. 관련 테이블

#### `job_inputs` 테이블
- `job_id` (UUID, PK): Job ID
- `desc_kor` (TEXT): 사용자 입력 - 한국어 설명 (30자 이내)
- `desc_eng` (TEXT): GPT Kor→Eng 변환 결과 또는 영어 광고문구
- `tone_style_id` (UUID, FK): 톤 & 스타일 ID

#### `jobs` 테이블
- `job_id` (UUID, PK): Job ID
- `store_id` (UUID, FK → stores): 스토어 ID

#### `stores` 테이블
- `store_id` (UUID, PK): 스토어 ID
- `user_id` (UUID, FK → users): 사용자 ID
- `image_id` (UUID, FK → image_assets): 이미지 ID
- `title` (VARCHAR): 스토어 제목
- `body` (TEXT): 스토어 설명
- `store_category` (TEXT): 스토어 카테고리
- `auto_scoring_flag` (BOOLEAN): 자동 점수 계산 플래그

**스토어 정보 조회 방법:**
```sql
SELECT s.title, s.body, s.store_category
FROM jobs j
INNER JOIN stores s ON j.store_id = s.store_id
WHERE j.job_id = :job_id
```
- **참고**: 스토어 정보는 `jobs.store_id`를 통해 `stores` 테이블에서 조회
- `job_inputs` 테이블에 `store_information` 컬럼 추가 불필요

#### `txt_ad_copy_generations` 테이블 (신규)
- `ad_copy_gen_id` (UUID, PK)
- `job_id` (UUID, FK → jobs): Job과 연결
- `llm_trace_id` (UUID, FK → llm_traces): GPT API 호출 Trace 참조
- `generation_stage` (TEXT): 생성 단계
  - `'kor_to_eng'`: 한국어 → 영어 변환
  - `'ad_copy_eng'`: 영어 광고문구 생성
- `ad_copy_eng` (TEXT): 영어 광고문구
- `status` (TEXT): 'queued', 'running', 'done', 'failed'
- `created_at`, `updated_at`

#### `llm_traces` 테이블
- `llm_trace_id` (UUID, PK)
- `job_id` (UUID, FK → jobs)
- `provider` (TEXT): 'gpt' 등
- `operation_type` (TEXT): 'kor_to_eng', 'ad_copy_gen' 등
- `request` (JSONB): GPT API 요청 데이터
- `response` (JSONB): GPT API 응답 데이터
- `latency_ms` (FLOAT): API 호출 소요 시간

---

## 🔧 구현해야 할 API 엔드포인트

### 1. `/api/js/gpt/kor-to-eng` (신규 생성)

**목적**: 한국어 설명을 영어로 변환

**요청 (Request):**
```json
{
  "job_id": "uuid-string",
  "tenant_id": "string"
}
```

**처리 과정:**
1. `job_inputs` 테이블에서 `desc_kor` 조회
2. GPT API 호출: 한국어 → 영어 변환
3. `llm_traces` 테이블에 기록:
   ```sql
   INSERT INTO llm_traces (
       llm_trace_id, job_id, provider, operation_type,
       request, response, latency_ms, created_at, updated_at
   ) VALUES (
       :llm_trace_id, :job_id, 'gpt', 'kor_to_eng',
       CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
4. `txt_ad_copy_generations` 테이블에 레코드 생성:
   ```sql
   INSERT INTO txt_ad_copy_generations (
       ad_copy_gen_id, job_id, llm_trace_id, generation_stage,
       ad_copy_eng, status, created_at, updated_at
   ) VALUES (
       :ad_copy_gen_id, :job_id, :llm_trace_id, 'kor_to_eng',
       :ad_copy_eng, 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ```
5. `job_inputs.desc_eng` 업데이트 (영어 설명으로)
6. `jobs` 테이블 업데이트:
   ```sql
   UPDATE jobs
   SET current_step = 'desc_kor_translate',
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
  "desc_eng": "English description",
  "status": "done"
}
```

---

### 2. `/api/js/gpt/ad-copy-eng` (신규 생성)

**목적**: 영어 광고문구 생성

**요청 (Request):**
```json
{
  "job_id": "uuid-string",
  "tenant_id": "string"
}
```

**처리 과정:**
1. `job_inputs` 테이블에서 다음 데이터 조회:
   - `desc_eng`: 영어 설명 (kor_to_eng 결과)
   - `tone_style_id`: 톤 & 스타일 ID
2. `tone_styles` 테이블에서 톤 & 스타일 정보 조회
3. GPT API 호출: 영어 광고문구 생성
   - 입력: `desc_eng`, `tone_style` 정보
   - 출력: 영어 광고문구
4. `llm_traces` 테이블에 기록:
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
5. `txt_ad_copy_generations` 테이블에 레코드 생성/업데이트:
   ```sql
   INSERT INTO txt_ad_copy_generations (
       ad_copy_gen_id, job_id, llm_trace_id, generation_stage,
       ad_copy_eng, status, created_at, updated_at
   ) VALUES (
       :ad_copy_gen_id, :job_id, :llm_trace_id, 'ad_copy_eng',
       :ad_copy_eng, 'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
   )
   ON CONFLICT (job_id, generation_stage) 
   DO UPDATE SET 
       ad_copy_eng = EXCLUDED.ad_copy_eng,
       llm_trace_id = EXCLUDED.llm_trace_id,
       status = 'done',
       updated_at = CURRENT_TIMESTAMP
   ```
6. `jobs` 테이블 업데이트:
   ```sql
   UPDATE jobs
   SET current_step = 'ad_copy_gen_eng',
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
  "ad_copy_eng": "English ad copy text",
  "status": "done"
}
```

---

## 📝 구현 체크리스트

### 1. 데이터베이스 연결
- [ ] `job_inputs` 테이블 조회 구현
- [ ] `txt_ad_copy_generations` 테이블 INSERT 구현
- [ ] `llm_traces` 테이블 INSERT 구현
- [ ] `jobs` 테이블 UPDATE 구현

### 2. GPT API 연동
- [ ] GPT API 클라이언트 설정
- [ ] 한국어 → 영어 변환 프롬프트 작성
- [ ] 영어 광고문구 생성 프롬프트 작성
- [ ] 에러 처리 및 재시도 로직

### 3. Trace 관리
- [ ] `llm_traces` 테이블에 요청/응답 저장
- [ ] `latency_ms` 측정 및 저장
- [ ] `operation_type` 올바르게 설정

### 4. 데이터 흐름
- [ ] `kor_to_eng` 완료 후 `ad_copy_eng` 자동 실행 여부 확인
- [ ] `txt_ad_copy_generations` 레코드 생성 확인
- [ ] `job_inputs.desc_eng` 업데이트 확인

---

## 🔗 YH 파트와의 연동

### 데이터 공유
- **JS 파트가 생성한 데이터**: `txt_ad_copy_generations` 테이블에 저장
  - `generation_stage='kor_to_eng'`: 영어 설명
  - `generation_stage='ad_copy_eng'`: 영어 광고문구
- **YH 파트가 사용하는 데이터**: `txt_ad_copy_generations.ad_copy_eng` 조회
  - `vlm_analyze` 단계에서 사용
  - `eng_to_kor` 단계에서 사용

### 실행 시점
- **`kor_to_eng`**: Job 생성 직후 또는 `img_gen` 전 실행
- **`ad_copy_eng`**: `kor_to_eng` 완료 후 실행

---

## ❓ 질문 및 문의

구현 중 문제가 발생하거나 질문이 있으면 YH 파트 담당자에게 문의하세요.


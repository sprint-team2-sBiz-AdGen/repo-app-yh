# YH 파트 구현 순서 가이드

## 📋 개요

YH 파트 구현을 단계별로 진행하기 위한 순서 가이드입니다.

**작성일**: 2025-12-01  
**버전**: 1.0.0

---

## 🎯 구현 순서

### 1단계: 데이터베이스 스키마 마이그레이션 ✅

**목적**: 필요한 테이블과 컬럼 생성

**작업 내용:**
1. `txt_ad_copy_generations` 테이블 생성
2. `instagram_feeds.llm_trace_id` 컬럼 추가
3. `instagram_feeds.ad_copy_kor` 컬럼 추가

**실행 방법:**
```bash
# PostgreSQL에 직접 연결하여 스키마 실행
# 또는 Docker 컨테이너 내에서 실행

# 방법 1: psql로 직접 실행
psql -h localhost -p 5432 -U feedlyai -d feedlyai -f /home/leeyoungho/feedlyai/db/init/01_schema.sql

# 방법 2: Docker 컨테이너 내에서 실행
docker exec -i feedlyai-postgres-yh psql -U feedlyai -d feedlyai < /home/leeyoungho/feedlyai/db/init/01_schema.sql
```

**확인 사항:**
- [ ] `txt_ad_copy_generations` 테이블 생성 확인
- [ ] `instagram_feeds.llm_trace_id` 컬럼 존재 확인
- [ ] `instagram_feeds.ad_copy_kor` 컬럼 존재 확인
- [ ] 인덱스 생성 확인

**확인 쿼리:**
```sql
-- 테이블 존재 확인
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_name = 'txt_ad_copy_generations'
);

-- 컬럼 존재 확인
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'instagram_feeds' 
  AND column_name IN ('llm_trace_id', 'ad_copy_kor');
```

---

### 2단계: Database 모델 업데이트

**목적**: SQLAlchemy 모델에 새 테이블/컬럼 추가

**작업 내용:**
1. `database.py`에 `TxtAdCopyGeneration` 모델 추가
2. `InstagramFeed` 모델에 `llm_trace_id`, `ad_copy_kor` 컬럼 추가

**파일**: `database.py`

**확인 사항:**
- [ ] `TxtAdCopyGeneration` 클래스 생성
- [ ] `InstagramFeed` 모델 업데이트
- [ ] 관계 설정 확인

---

### 3단계: 기존 API 수정 - `/api/yh/llava/stage1/validate`

**목적**: `txt_ad_copy_generations` 테이블에서 광고문구 조회하도록 수정

**파일**: `routers/llava_stage1.py`

**수정 내용:**
1. `txt_ad_copy_generations` 테이블에서 `ad_copy_eng` 조회 (우선순위)
2. Fallback 로직 유지 (하위 호환성)
3. `body.ad_copy_text` → `txt_ad_copy_generations` → `job_inputs.desc_eng` 순서로 조회

**확인 사항:**
- [ ] `txt_ad_copy_generations` 조회 로직 추가
- [ ] Fallback 로직 유지
- [ ] 기존 테스트 통과 확인

---

### 4단계: 신규 API 구현 - `/api/yh/gpt/refine-ad-copy` (선택적)

**목적**: `vlm_analyze` 검증 결과에 따라 광고문구 조정

**파일**: `routers/refined_ad_copy.py` (이미 존재하는지 확인 필요)

**구현 내용:**
1. `vlm_traces`에서 `vlm_analyze` 검증 결과 조회
2. 검증 결과 분석 (is_valid, relevance_score)
3. 조건부 실행 로직 (검증 결과에 따라 스킵)
4. GPT API 호출: 광고문구 조정
5. `llm_traces` 저장
6. `txt_ad_copy_generations` 레코드 생성/업데이트 (`generation_stage='refined_ad_copy'`)
7. `jobs` 테이블 업데이트

**확인 사항:**
- [ ] API 엔드포인트 생성
- [ ] `vlm_traces` 조회 로직
- [ ] 조건부 실행 로직
- [ ] GPT API 호출 및 `llm_traces` 저장
- [ ] `txt_ad_copy_generations` 저장

---

### 5단계: 신규 API 구현 - `/api/yh/gpt/eng-to-kor`

**목적**: 영어 광고문구를 한글로 변환

**파일**: `routers/gpt.py` 또는 새 파일 생성

**구현 내용:**
1. `txt_ad_copy_generations`에서 영어 광고문구 조회
   - `refined_ad_copy_eng` 우선, 없으면 `ad_copy_eng` 사용
2. GPT API 호출: 영어 → 한글 변환
3. `llm_traces` 저장 (`operation_type='eng_to_kor'`)
4. `txt_ad_copy_generations` 레코드 생성/업데이트 (`generation_stage='eng_to_kor'`)
5. `instagram_feeds.ad_copy_kor` 저장
6. `jobs` 테이블 업데이트

**확인 사항:**
- [ ] API 엔드포인트 생성
- [ ] `txt_ad_copy_generations` 조회 로직
- [ ] GPT API 호출 및 `llm_traces` 저장
- [ ] `txt_ad_copy_generations` 저장
- [ ] `instagram_feeds.ad_copy_kor` 저장

---

### 6단계: 기존 API 수정 - `/api/yh/instagram/feed`

**목적**: `job_id`, `tenant_id` 파라미터 필수화 및 `txt_ad_copy_generations` 연동

**파일**: `routers/instagram_feed.py`

**수정 내용:**
1. `job_id`, `tenant_id` 파라미터 필수화
2. `txt_ad_copy_generations.ad_copy_kor` 조회
3. `jobs.store_id` → `stores` 테이블에서 스토어 정보 조회
4. GPT API 호출 및 `llm_traces` 저장
5. `instagram_feeds.llm_trace_id` 저장
6. `instagram_feeds.ad_copy_kor` 저장

**확인 사항:**
- [ ] `job_id`, `tenant_id` 파라미터 필수화
- [ ] `txt_ad_copy_generations.ad_copy_kor` 조회
- [ ] `stores` 테이블 조회 로직
- [ ] `llm_traces` 저장
- [ ] `instagram_feeds.llm_trace_id` 저장

---

### 7단계: 파이프라인 트리거 수정

**목적**: 새 단계를 파이프라인에 추가

**파일**: `services/pipeline_trigger.py`

**수정 내용:**
1. `PIPELINE_STAGES`에 새 단계 추가:
   - `('vlm_analyze', 'done')` → `('refined_ad_copy', 'done')` (선택적)
   - `('iou_eval', 'done')` → `('ad_copy_gen_kor', 'done')`
   - `('ad_copy_gen_kor', 'done')` → `('instagram_feed_gen', 'done')`
2. Job 레벨 단계 처리 로직 확인
3. 선택적 단계(`refined_ad_copy`) 처리 로직 구현

**확인 사항:**
- [ ] `PIPELINE_STAGES`에 새 단계 추가
- [ ] Job 레벨 단계 처리 로직 확인
- [ ] 선택적 단계 처리 로직 구현

---

### 8단계: Models 업데이트

**목적**: Pydantic 모델에 새 필드 추가

**파일**: `models.py`

**수정 내용:**
1. `InstagramFeedIn` 모델 수정 (필요 시)
2. `InstagramFeedOut` 모델 수정 (필요 시)
3. 새 API용 모델 생성 (필요 시)

**확인 사항:**
- [ ] 모델 정의 확인
- [ ] 필수 필드 확인

---

### 9단계: 테스트

**목적**: 전체 파이프라인 및 개별 기능 테스트

**테스트 항목:**
1. **단위 테스트**
   - [ ] `txt_ad_copy_generations` 데이터 저장/조회 테스트
   - [ ] `llm_traces` 저장 테스트
   - [ ] `stores` 테이블 조회 테스트

2. **통합 테스트**
   - [ ] `/api/yh/llava/stage1/validate` 수정 확인
   - [ ] `/api/yh/gpt/refine-ad-copy` 동작 확인 (선택적)
   - [ ] `/api/yh/gpt/eng-to-kor` 동작 확인
   - [ ] `/api/yh/instagram/feed` 수정 확인

3. **파이프라인 테스트**
   - [ ] 전체 파이프라인 테스트 (JS 파트 연동 포함)
   - [ ] Trace 관리 테스트
   - [ ] 에러 처리 테스트

---

## 📝 체크리스트 요약

### 필수 작업
- [ ] 1단계: 데이터베이스 스키마 마이그레이션
- [ ] 2단계: Database 모델 업데이트
- [ ] 3단계: `/api/yh/llava/stage1/validate` 수정
- [ ] 5단계: `/api/yh/gpt/eng-to-kor` 구현
- [ ] 6단계: `/api/yh/instagram/feed` 수정
- [ ] 7단계: 파이프라인 트리거 수정
- [ ] 8단계: Models 업데이트
- [ ] 9단계: 테스트

### 선택적 작업
- [ ] 4단계: `/api/yh/gpt/refine-ad-copy` 구현 (검증 결과에 따라 선택적 실행)

---

## 🔗 참고 문서

- `DOCS_YH_PART_IMPLEMENTATION.md`: 상세 구현 가이드
- `ANALYSIS_INSTAGRAM_FEED_PIPELINE_INTEGRATION.md`: 전체 파이프라인 분석
- `db/init/01_schema.sql`: 데이터베이스 스키마

---

## ⚠️ 주의사항

1. **하위 호환성**: 기존 코드와의 호환성을 유지하기 위해 Fallback 로직 구현
2. **Trace 관리**: 모든 GPT API 호출은 반드시 `llm_traces`에 기록
3. **에러 처리**: 각 단계에서 실패 시 적절한 에러 처리 및 재시도 로직 구현
4. **데이터 일관성**: `txt_ad_copy_generations` 레코드 생성 시 `job_id`와 `generation_stage` 조합이 유일해야 함

---

## 🚀 빠른 시작

가장 빠르게 시작하려면:

1. **1단계부터 순서대로 진행**
2. **각 단계 완료 후 테스트**
3. **문제 발생 시 즉시 수정**

각 단계를 완료할 때마다 체크리스트를 업데이트하세요!


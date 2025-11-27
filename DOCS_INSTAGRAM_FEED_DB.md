# 인스타그램 피드 글 생성 - 데이터베이스 테이블 설계

## 📋 테이블 설계

### 테이블명: `instagram_feeds` 및 `llm_models`

인스타그램 피드 글 생성 결과를 저장하는 테이블입니다.  
LLM 모델 정보는 별도의 `llm_models` 테이블에서 중앙 관리됩니다.

## 🗄️ 관련 테이블

### 1. `llm_models` 테이블

LLM (GPT) 모델 정보를 중앙 관리하는 테이블입니다.

```sql
CREATE TABLE llm_models (
    llm_model_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 모델 기본 정보
    model_name VARCHAR(255) NOT NULL,  -- 모델 이름 (예: "gpt-4o-mini")
    model_version VARCHAR(255),  -- 모델 버전 (예: "2024-07-18")
    provider VARCHAR(255) NOT NULL,  -- 제공자 (예: "openai", "anthropic", "google")
    
    -- 모델 설정 (기본값)
    default_temperature FLOAT,  -- 기본 temperature 설정
    default_max_tokens INTEGER,  -- 기본 최대 토큰 수
    
    -- 비용 정보 (USD per 1M tokens)
    prompt_token_cost_per_1m FLOAT,  -- 입력 토큰당 비용 (per 1M tokens)
    completion_token_cost_per_1m FLOAT,  -- 출력 토큰당 비용 (per 1M tokens)
    
    -- 메타데이터
    description TEXT,  -- 모델 설명
    is_active VARCHAR(10) DEFAULT 'true',  -- 활성화 여부 ('true', 'false')
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**주요 컬럼 설명:**
- `llm_model_id`: 모델 고유 식별자 (UUID)
- `model_name`: 모델 이름 (예: "gpt-4o-mini")
- `provider`: 제공자 (예: "openai", "anthropic")
- `default_temperature`: 기본 temperature 설정
- `default_max_tokens`: 기본 최대 토큰 수
- `prompt_token_cost_per_1m`: 입력 토큰당 비용 (USD per 1M tokens)
- `completion_token_cost_per_1m`: 출력 토큰당 비용 (USD per 1M tokens)
- `is_active`: 활성화 여부

### 2. `instagram_feeds` 테이블

인스타그램 피드 글 생성 결과를 저장하는 테이블입니다.

## 🗄️ 컬럼 구조

### 필수 컬럼

```sql
CREATE TABLE instagram_feeds (
    -- Primary Key
    instagram_feed_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Foreign Keys
    job_id UUID REFERENCES jobs(job_id),  -- 파이프라인과 연결 시 사용
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),  -- 오버레이 결과와 연결 시 사용
    llm_model_id UUID REFERENCES llm_models(llm_model_id),  -- 사용된 LLM 모델
    
    -- Tenant 정보
    tenant_id VARCHAR(255) NOT NULL,  -- 테넌트 ID
    
    -- 입력 데이터 (요청 시 받은 정보)
    refined_ad_copy_eng TEXT NOT NULL,  -- 조정된 광고문구 (영어)
    tone_style TEXT NOT NULL,  -- 톤 & 스타일
    product_description TEXT NOT NULL,  -- 제품 설명
    store_information TEXT NOT NULL,  -- 스토어 정보
    gpt_prompt TEXT NOT NULL,  -- GPT 프롬프트
    
    -- 출력 데이터 (생성된 결과)
    instagram_ad_copy TEXT NOT NULL,  -- 생성된 인스타그램 피드 글
    hashtags TEXT NOT NULL,  -- 생성된 해시태그 (예: "#태그1 #태그2 #태그3")
    
    -- LLM 실행 메타데이터 (실제 실행 시 사용된 값)
    used_temperature FLOAT,  -- 실제 사용된 temperature (llm_models의 기본값과 다를 수 있음)
    used_max_tokens INTEGER,  -- 실제 사용된 최대 토큰 수
    gpt_prompt_used TEXT,  -- 실제 사용된 전체 프롬프트 (디버깅용)
    gpt_response_raw JSONB,  -- GPT API 원본 응답 (디버깅/재생성용)
    
    -- 성능 메트릭
    latency_ms FLOAT,  -- GPT API 호출 소요 시간 (밀리초)
    prompt_tokens INTEGER,  -- 프롬프트 토큰 수 (입력, 모니터링용)
    completion_tokens INTEGER,  -- 생성 토큰 수 (출력, 모니터링용)
    total_tokens INTEGER,  -- 총 토큰 수 (모니터링용)
    token_usage JSONB,  -- 토큰 사용량 정보 원본 (예: {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300})
    
    -- 메타데이터
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 인덱스

```sql
-- llm_models 테이블 인덱스
CREATE INDEX idx_llm_models_provider ON llm_models(provider);
CREATE INDEX idx_llm_models_model_name ON llm_models(model_name);
CREATE INDEX idx_llm_models_is_active ON llm_models(is_active);

-- instagram_feeds 테이블 인덱스
CREATE INDEX idx_instagram_feeds_job_id ON instagram_feeds(job_id);
CREATE INDEX idx_instagram_feeds_overlay_id ON instagram_feeds(overlay_id);
CREATE INDEX idx_instagram_feeds_llm_model_id ON instagram_feeds(llm_model_id);
CREATE INDEX idx_instagram_feeds_tenant_id ON instagram_feeds(tenant_id);
CREATE INDEX idx_instagram_feeds_created_at ON instagram_feeds(created_at);
CREATE INDEX idx_instagram_feeds_prompt_tokens ON instagram_feeds(prompt_tokens);
CREATE INDEX idx_instagram_feeds_completion_tokens ON instagram_feeds(completion_tokens);
CREATE INDEX idx_instagram_feeds_total_tokens ON instagram_feeds(total_tokens);
CREATE INDEX idx_instagram_feeds_created_at_tokens ON instagram_feeds(created_at, total_tokens);
```

## 📝 컬럼 상세 설명

### 1. Primary Key
- **instagram_feed_id** (UUID): 고유 식별자

### 2. Foreign Keys
- **job_id** (UUID, NULLABLE): `jobs` 테이블과 연결 (파이프라인과 통합 시)
- **overlay_id** (UUID, NULLABLE): `overlay_layouts` 테이블과 연결 (오버레이 결과와 연결 시)
- **llm_model_id** (UUID, NULLABLE): `llm_models` 테이블과 연결 (사용된 LLM 모델)

### 3. Tenant & Job 정보
- **tenant_id** (VARCHAR(255), NOT NULL): 테넌트 ID

### 4. 입력 데이터 (요청 시 받은 정보)
- **refined_ad_copy_eng** (TEXT, NOT NULL): 조정된 광고문구 (영어)
- **tone_style** (TEXT, NOT NULL): 톤 & 스타일
- **product_description** (TEXT, NOT NULL): 제품 설명
- **store_information** (TEXT, NOT NULL): 스토어 정보
- **gpt_prompt** (TEXT, NOT NULL): GPT 프롬프트

### 5. 출력 데이터 (생성된 결과)
- **instagram_ad_copy** (TEXT, NOT NULL): 생성된 인스타그램 피드 글
- **hashtags** (TEXT, NOT NULL): 생성된 해시태그 (예: "#태그1 #태그2 #태그3")

### 6. LLM 실행 메타데이터
- **llm_model_id** (UUID, NULLABLE): 사용된 LLM 모델 ID (FK → llm_models.llm_model_id)
  - 모델 정보는 `llm_models` 테이블에서 조회 가능
- **used_temperature** (FLOAT, NULLABLE): 실제 사용된 temperature (llm_models의 기본값과 다를 수 있음)
- **used_max_tokens** (INTEGER, NULLABLE): 실제 사용된 최대 토큰 수
- **gpt_prompt_used** (TEXT, NULLABLE): 실제 사용된 전체 프롬프트 (디버깅용)
- **gpt_response_raw** (JSONB, NULLABLE): GPT API 원본 응답 (디버깅/재생성용)

### 7. 성능 메트릭
- **latency_ms** (FLOAT, NULLABLE): GPT API 호출 소요 시간 (밀리초)
- **prompt_tokens** (INTEGER, NULLABLE): 프롬프트 토큰 수 (입력, 모니터링용)
- **completion_tokens** (INTEGER, NULLABLE): 생성 토큰 수 (출력, 모니터링용)
- **total_tokens** (INTEGER, NULLABLE): 총 토큰 수 (모니터링용)
- **token_usage** (JSONB, NULLABLE): 토큰 사용량 정보 원본 (상세 분석용)
  ```json
  {
    "prompt_tokens": 100,
    "completion_tokens": 200,
    "total_tokens": 300
  }
  ```

### 8. 메타데이터
- **pk** (INTEGER SERIAL, NULLABLE): 순차 ID (선택사항)
- **created_at** (TIMESTAMP WITH TIME ZONE): 생성 시간
- **updated_at** (TIMESTAMP WITH TIME ZONE): 수정 시간

## 🔄 다른 테이블과의 관계

### llm_models 테이블과의 관계
- `llm_model_id`를 통해 사용된 LLM 모델 정보를 참조
- 하나의 llm_model에 여러 개의 instagram_feed가 연결될 수 있음 (1:N)
- 모델별 비용 정보, 기본 설정 등을 중앙 관리

### jobs 테이블과의 관계
- `job_id`를 통해 파이프라인과 연결 가능
- 하나의 job에 여러 개의 instagram_feed가 연결될 수 있음 (1:N)

### overlay_layouts 테이블과의 관계
- `overlay_id`를 통해 오버레이 결과와 연결 가능
- 하나의 overlay에 하나의 instagram_feed가 연결될 수 있음 (1:1 또는 1:N)

## 📊 JSONB 필드 예시

### gpt_response_raw 예시
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "gpt-4o-mini",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"instagram_ad_copy\": \"...\", \"hashtags\": \"...\"}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 200,
    "total_tokens": 300
  }
}
```

### token_usage 예시
```json
{
  "prompt_tokens": 100,
  "completion_tokens": 200,
  "total_tokens": 300
}
```

## 🔍 주요 쿼리 예시

### 1. 특정 job의 인스타그램 피드 조회
```sql
SELECT * FROM instagram_feeds 
WHERE job_id = 'xxx-xxx-xxx' 
ORDER BY created_at DESC;
```

### 2. 특정 tenant의 최근 인스타그램 피드 조회
```sql
SELECT * FROM instagram_feeds 
WHERE tenant_id = 'test_tenant' 
ORDER BY created_at DESC 
LIMIT 10;
```

### 3. 특정 overlay와 연결된 인스타그램 피드 조회
```sql
SELECT * FROM instagram_feeds 
WHERE overlay_id = 'xxx-xxx-xxx';
```

### 4. 성능 통계 조회
```sql
SELECT 
    AVG(latency_ms) as avg_latency,
    MIN(latency_ms) as min_latency,
    MAX(latency_ms) as max_latency,
    COUNT(*) as total_count
FROM instagram_feeds
WHERE tenant_id = 'test_tenant'
AND created_at >= NOW() - INTERVAL '7 days';
```

### 5. 토큰 사용량 통계 조회
```sql
SELECT 
    AVG(prompt_tokens) as avg_prompt_tokens,
    AVG(completion_tokens) as avg_completion_tokens,
    AVG(total_tokens) as avg_total_tokens,
    SUM(total_tokens) as total_tokens_sum,
    COUNT(*) as request_count
FROM instagram_feeds
WHERE tenant_id = 'test_tenant'
AND created_at >= NOW() - INTERVAL '7 days';
```

### 6. 비용 추정 쿼리 (llm_models 테이블과 조인)
```sql
-- llm_models 테이블의 비용 정보를 사용하여 정확한 비용 계산
SELECT 
    lm.model_name,
    lm.provider,
    COUNT(if.instagram_feed_id) as request_count,
    SUM(if.prompt_tokens) as total_prompt_tokens,
    SUM(if.completion_tokens) as total_completion_tokens,
    SUM(if.total_tokens) as total_tokens,
    ROUND(SUM(if.prompt_tokens) * lm.prompt_token_cost_per_1m / 1000000, 4) as estimated_input_cost_usd,
    ROUND(SUM(if.completion_tokens) * lm.completion_token_cost_per_1m / 1000000, 4) as estimated_output_cost_usd,
    ROUND(
        (SUM(if.prompt_tokens) * lm.prompt_token_cost_per_1m + 
         SUM(if.completion_tokens) * lm.completion_token_cost_per_1m) / 1000000, 
        4
    ) as estimated_total_cost_usd
FROM instagram_feeds if
INNER JOIN llm_models lm ON if.llm_model_id = lm.llm_model_id
WHERE if.tenant_id = 'test_tenant'
AND if.created_at >= NOW() - INTERVAL '7 days'
GROUP BY lm.llm_model_id, lm.model_name, lm.provider, 
         lm.prompt_token_cost_per_1m, lm.completion_token_cost_per_1m
ORDER BY estimated_total_cost_usd DESC;
```

### 7. 토큰 사용량 추이 분석
```sql
SELECT 
    DATE(created_at) as date,
    COUNT(*) as request_count,
    AVG(prompt_tokens) as avg_prompt_tokens,
    AVG(completion_tokens) as avg_completion_tokens,
    AVG(total_tokens) as avg_total_tokens,
    SUM(total_tokens) as daily_total_tokens
FROM instagram_feeds
WHERE tenant_id = 'test_tenant'
AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### 8. LLM 모델별 사용 통계
```sql
SELECT 
    lm.model_name,
    lm.provider,
    COUNT(if.instagram_feed_id) as usage_count,
    AVG(if.latency_ms) as avg_latency_ms,
    MIN(if.latency_ms) as min_latency_ms,
    MAX(if.latency_ms) as max_latency_ms,
    SUM(if.prompt_tokens) as total_prompt_tokens,
    SUM(if.completion_tokens) as total_completion_tokens,
    SUM(if.total_tokens) as total_tokens,
    AVG(if.prompt_tokens) as avg_prompt_tokens,
    AVG(if.completion_tokens) as avg_completion_tokens,
    ROUND(
        (SUM(if.prompt_tokens) * lm.prompt_token_cost_per_1m + 
         SUM(if.completion_tokens) * lm.completion_token_cost_per_1m) / 1000000, 
        4
    ) as total_cost_usd
FROM llm_models lm
LEFT JOIN instagram_feeds if ON lm.llm_model_id = if.llm_model_id
WHERE if.created_at >= NOW() - INTERVAL '7 days'
GROUP BY lm.llm_model_id, lm.model_name, lm.provider, 
         lm.prompt_token_cost_per_1m, lm.completion_token_cost_per_1m
ORDER BY usage_count DESC;
```

### 9. LLM 모델별 일일 사용량 및 비용 추이
```sql
SELECT 
    DATE(if.created_at) as date,
    lm.model_name,
    lm.provider,
    COUNT(if.instagram_feed_id) as daily_request_count,
    SUM(if.total_tokens) as daily_total_tokens,
    ROUND(
        (SUM(if.prompt_tokens) * lm.prompt_token_cost_per_1m + 
         SUM(if.completion_tokens) * lm.completion_token_cost_per_1m) / 1000000, 
        4
    ) as daily_cost_usd
FROM instagram_feeds if
INNER JOIN llm_models lm ON if.llm_model_id = lm.llm_model_id
WHERE if.tenant_id = 'test_tenant'
AND if.created_at >= NOW() - INTERVAL '30 days'
GROUP BY DATE(if.created_at), lm.llm_model_id, lm.model_name, lm.provider,
         lm.prompt_token_cost_per_1m, lm.completion_token_cost_per_1m
ORDER BY date DESC, daily_cost_usd DESC;
```

## 🚀 구현 단계

### Phase 1: 기본 테이블 생성 ✅ 완료
1. ✅ 테이블 생성 (database.py에 InstagramFeed 모델 추가)
2. ✅ 인덱스 생성 (DB 스키마에 추가 필요)
3. ✅ 기본 CRUD 기능 구현 (routers/instagram_feed.py에 저장 로직 추가)

### Phase 2: 파이프라인 연동 (진행 중)
1. [ ] `job_id` 연결 로직 추가
2. [ ] `overlay_id` 연결 로직 추가
3. [ ] 파이프라인 통합 테스트

### Phase 3: 고급 기능
1. [ ] 히스토리 관리
2. [ ] A/B 테스트 지원
3. [ ] 배치 처리 지원

## 📝 구현 완료 사항

### 데이터베이스 모델 (database.py)
- `InstagramFeed` 모델 추가 완료
- 모든 필수 컬럼 포함

### 라우터 (routers/instagram_feed.py)
- DB 저장 로직 추가 완료
- 트랜잭션 처리 (rollback 포함)
- 에러 핸들링

### 서비스 (services/gpt_service.py)
- latency_ms 측정 추가
- token_usage 수집 추가
- gpt_response_raw 저장 추가

### 응답 모델 (models.py)
- `instagram_feed_id` 필드 추가

## 📝 참고사항

1. **llm_model_id**: LLM 모델 정보는 `llm_models` 테이블에서 중앙 관리되며, `instagram_feeds`는 외래키로 참조합니다.
2. **used_temperature, used_max_tokens**: 실제 실행 시 사용된 값으로, `llm_models`의 기본값과 다를 수 있습니다.
3. **job_id와 overlay_id는 NULLABLE**: 초기에는 독립적으로 사용 가능하며, 나중에 파이프라인과 연결 가능
4. **gpt_response_raw 저장**: 디버깅 및 재생성 시 유용
5. **latency_ms 저장**: 성능 모니터링 및 최적화에 활용
6. **token_usage 저장**: 비용 관리 및 최적화에 활용
7. **비용 계산**: `llm_models` 테이블의 `prompt_token_cost_per_1m`, `completion_token_cost_per_1m`을 사용하여 정확한 비용 계산 가능


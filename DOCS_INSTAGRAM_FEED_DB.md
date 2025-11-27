# 인스타그램 피드 글 생성 - 데이터베이스 테이블 설계

## 📋 테이블 설계

### 테이블명: `instagram_feeds`

인스타그램 피드 글 생성 결과를 저장하는 테이블입니다.

## 🗄️ 컬럼 구조

### 필수 컬럼

```sql
CREATE TABLE instagram_feeds (
    -- Primary Key
    instagram_feed_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Foreign Keys (나중에 연결)
    job_id UUID REFERENCES jobs(job_id) NULLABLE,  -- 파이프라인과 연결 시 사용
    overlay_id UUID REFERENCES overlay_layouts(overlay_id) NULLABLE,  -- 오버레이 결과와 연결 시 사용
    
    -- Tenant & Job 정보
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
    
    -- GPT 메타데이터
    gpt_model_name VARCHAR(255),  -- 사용된 GPT 모델 (예: "gpt-4o-mini")
    gpt_max_tokens INTEGER,  -- 사용된 최대 토큰 수
    gpt_temperature FLOAT,  -- 사용된 temperature 설정
    gpt_prompt_used TEXT,  -- 실제 사용된 전체 프롬프트 (디버깅용)
    gpt_response_raw JSONB,  -- GPT API 원본 응답 (디버깅/재생성용)
    
    -- 성능 메트릭
    latency_ms FLOAT,  -- GPT API 호출 소요 시간 (밀리초)
    token_usage JSONB,  -- 토큰 사용량 정보 (예: {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300})
    
    -- 메타데이터
    pk INTEGER SERIAL,  -- 순차 ID (선택사항)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 인덱스

```sql
-- job_id 인덱스 (파이프라인과 연결 시 조회 성능 향상)
CREATE INDEX idx_instagram_feeds_job_id ON instagram_feeds(job_id);

-- overlay_id 인덱스 (오버레이 결과와 연결 시 조회 성능 향상)
CREATE INDEX idx_instagram_feeds_overlay_id ON instagram_feeds(overlay_id);

-- tenant_id 인덱스 (테넌트별 조회)
CREATE INDEX idx_instagram_feeds_tenant_id ON instagram_feeds(tenant_id);

-- created_at 인덱스 (시간순 조회)
CREATE INDEX idx_instagram_feeds_created_at ON instagram_feeds(created_at);
```

## 📝 컬럼 상세 설명

### 1. Primary Key
- **instagram_feed_id** (UUID): 고유 식별자

### 2. Foreign Keys (나중에 연결)
- **job_id** (UUID, NULLABLE): `jobs` 테이블과 연결 (파이프라인과 통합 시)
- **overlay_id** (UUID, NULLABLE): `overlay_layouts` 테이블과 연결 (오버레이 결과와 연결 시)

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

### 6. GPT 메타데이터
- **gpt_model_name** (VARCHAR(255), NULLABLE): 사용된 GPT 모델 (예: "gpt-4o-mini")
- **gpt_max_tokens** (INTEGER, NULLABLE): 사용된 최대 토큰 수
- **gpt_temperature** (FLOAT, NULLABLE): 사용된 temperature 설정
- **gpt_prompt_used** (TEXT, NULLABLE): 실제 사용된 전체 프롬프트 (디버깅용)
- **gpt_response_raw** (JSONB, NULLABLE): GPT API 원본 응답 (디버깅/재생성용)

### 7. 성능 메트릭
- **latency_ms** (FLOAT, NULLABLE): GPT API 호출 소요 시간 (밀리초)
- **token_usage** (JSONB, NULLABLE): 토큰 사용량 정보
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

1. **job_id와 overlay_id는 NULLABLE**: 초기에는 독립적으로 사용 가능하며, 나중에 파이프라인과 연결 가능
2. **gpt_response_raw 저장**: 디버깅 및 재생성 시 유용
3. **latency_ms 저장**: 성능 모니터링 및 최적화에 활용
4. **token_usage 저장**: 비용 관리 및 최적화에 활용


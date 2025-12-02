# 모니터링 및 추적 발표자료

## 📋 개요

**기능명**: 완전한 모니터링 및 추적 시스템

**목적**: 모든 LLM 호출과 파이프라인 단계를 추적하여 비용, 성능, 품질을 모니터링

**핵심 가치**: 
- 완전한 호출 추적
- 비용 모니터링
- 성능 분석
- 장애 복구 지원

---

## 🎯 목적

### 문제 해결
- **비용 관리**: LLM API 호출 비용 추적 어려움
- **성능 분석**: 어떤 단계가 느린지 파악 어려움
- **장애 추적**: 문제 발생 시 원인 파악 어려움
- **품질 관리**: 생성된 콘텐츠의 품질 추적 어려움

### 해결 방안
- **LLM 추적 시스템**: 모든 LLM 호출을 `llm_traces`에 저장
- **Job 상태 관리**: 파이프라인 진행 상황을 세밀하게 추적
- **Variant별 추적**: 각 Variant의 독립적 진행 추적
- **재시도 메커니즘**: 실패 시 자동 재시도 및 복구

---

## ✨ 주요 특징

### 1. LLM 추적 시스템
- **완전한 추적**: 모든 LLM API 호출 추적
- **토큰 사용량**: prompt_tokens, completion_tokens, total_tokens
- **지연 시간**: latency_ms로 성능 측정
- **모델 정보**: 사용된 LLM 모델 추적
- **작업 유형**: operation_type으로 작업 분류

### 2. Job 및 Variant 상태 관리
- **Job 레벨 상태**: 전체 Job의 진행 상황 추적
- **Variant별 추적**: 각 Variant의 독립적 진행 추적
- **단계별 상태**: current_step으로 현재 단계 추적
- **재시도 메커니즘**: retry_count로 재시도 횟수 추적

---

## 🏗️ 아키텍처

### 추적 시스템 구조

```
[LLM API 호출]
GPT API 호출
  ↓
[토큰 사용량 추출]
response.usage에서 추출
  ↓
[LLM Trace 저장]
llm_traces 테이블에 저장
  ↓
[상태 업데이트]
jobs/jobs_variants 상태 업데이트
  ↓
[모니터링]
비용, 성능, 품질 분석
```

---

## 💻 구현 코드

### 1. LLM Traces 테이블 구조

**파일**: `db/init/01_schema.sql`

```sql
CREATE TABLE llm_traces (
    llm_trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    provider VARCHAR(255),  -- 'gpt', 'anthropic', etc.
    llm_model_id UUID REFERENCES llm_models(llm_model_id) ON DELETE SET NULL,
    tone_style_id UUID REFERENCES tone_styles(tone_style_id) ON DELETE SET NULL,
    enhanced_img_id UUID REFERENCES image_assets(image_asset_id) ON DELETE SET NULL,
    prompt_id UUID,
    operation_type VARCHAR(255),  -- 'translate', 'ad_copy_gen', 'eng_to_kor', 'feed_gen'
    request JSONB,  -- 요청 데이터
    response JSONB,  -- 응답 데이터
    latency_ms FLOAT,  -- 지연 시간 (밀리초)
    -- 토큰 사용량 정보
    prompt_tokens INTEGER,  -- 프롬프트 토큰 수
    completion_tokens INTEGER,  -- 생성 토큰 수
    total_tokens INTEGER,  -- 총 토큰 수
    token_usage JSONB,  -- 토큰 사용량 원본
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_llm_traces_job_id ON llm_traces(job_id);
CREATE INDEX idx_llm_traces_operation_type ON llm_traces(operation_type);
CREATE INDEX idx_llm_traces_llm_model_id ON llm_traces(llm_model_id);
CREATE INDEX idx_llm_traces_created_at ON llm_traces(created_at);
```

**핵심 포인트**:
- **완전한 추적**: 요청/응답 모두 JSONB로 저장
- **토큰 정보**: 세 가지 토큰 정보 + 원본 JSON
- **인덱스**: 빠른 조회를 위한 인덱스
- **외래 키**: 관련 테이블과 연결

---

### 2. LLM Trace 저장 예시

**파일**: `services/gpt_service.py`

```python
def translate_eng_to_kor(
    text: str,
    llm_model_id: Optional[str],
    job_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """영어 → 한글 변환 (LLM Trace 포함)"""
    from openai import OpenAI
    from database import SessionLocal
    from sqlalchemy import text
    import time
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # 1. 시작 시간 기록
    start_time = time.time()
    
    # 2. GPT API 호출
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a translator..."},
            {"role": "user", "content": f"Translate: {text}"}
        ],
        temperature=0.7
    )
    
    # 3. 지연 시간 계산
    latency_ms = (time.time() - start_time) * 1000
    
    # 4. 토큰 사용량 추출
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else None
    completion_tokens = usage.completion_tokens if usage else None
    total_tokens = usage.total_tokens if usage else None
    
    # 5. LLM Trace 저장
    db = SessionLocal()
    try:
        llm_trace_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO llm_traces (
                llm_trace_id, job_id, llm_model_id,
                provider, operation_type,
                request, response,
                prompt_tokens, completion_tokens, total_tokens,
                token_usage, latency_ms,
                created_at, updated_at
            ) VALUES (
                :llm_trace_id, :job_id, :llm_model_id,
                'gpt', 'eng_to_kor',
                CAST(:request AS jsonb), CAST(:response AS jsonb),
                :prompt_tokens, :completion_tokens, :total_tokens,
                CAST(:token_usage AS jsonb), :latency_ms,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "llm_trace_id": llm_trace_id,
            "job_id": uuid.UUID(job_id),
            "llm_model_id": uuid.UUID(llm_model_id) if llm_model_id else None,
            "request": json.dumps({"text": text}),
            "response": json.dumps({
                "translated_text": response.choices[0].message.content
            }),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "token_usage": json.dumps({
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }) if usage else None,
            "latency_ms": latency_ms
        })
        db.commit()
    finally:
        db.close()
    
    return {
        "translated_text": response.choices[0].message.content,
        "llm_trace_id": str(llm_trace_id)
    }
```

**핵심 포인트**:
- **시작 시간 기록**: 정확한 지연 시간 측정
- **토큰 사용량 추출**: API 응답에서 자동 추출
- **완전한 저장**: 요청/응답 모두 JSONB로 저장
- **에러 처리**: try-finally로 안전한 처리

---

### 3. Job 및 Variant 상태 관리

**파일**: `database.py`

```python
class Job(Base):
    """Jobs 데이터베이스 모델"""
    __tablename__ = "jobs"
    
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.store_id"), nullable=True)
    status = Column(String(50), nullable=False)  # 'queued', 'running', 'done', 'failed'
    current_step = Column(String(255), nullable=True)  # 'img_gen', 'vlm_analyze', ...
    retry_count = Column(Integer, default=0)  # 재시도 횟수
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class JobVariant(Base):
    """Job Variants 데이터베이스 모델"""
    __tablename__ = "jobs_variants"
    
    job_variants_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False)
    img_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"), nullable=True)
    creation_order = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)  # 'queued', 'running', 'done', 'failed'
    current_step = Column(String(255), nullable=True)  # 'img_gen', 'vlm_analyze', ...
    retry_count = Column(Integer, default=0)  # 재시도 횟수
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**핵심 포인트**:
- **상태 관리**: queued, running, done, failed 상태 추적
- **단계 추적**: current_step으로 현재 단계 추적
- **재시도 추적**: retry_count로 재시도 횟수 추적
- **타임스탬프**: created_at, updated_at으로 시간 추적

---

## 📊 모니터링 쿼리

### 1. 비용 모니터링

```sql
-- 작업 유형별 토큰 사용량 집계
SELECT 
    operation_type,
    COUNT(*) as call_count,
    SUM(prompt_tokens) as total_prompt_tokens,
    SUM(completion_tokens) as total_completion_tokens,
    SUM(total_tokens) as total_tokens,
    AVG(latency_ms) as avg_latency_ms
FROM llm_traces
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY operation_type
ORDER BY total_tokens DESC;
```

---

### 2. 성능 분석

```sql
-- 작업 유형별 평균 지연 시간
SELECT 
    operation_type,
    COUNT(*) as call_count,
    AVG(latency_ms) as avg_latency_ms,
    MIN(latency_ms) as min_latency_ms,
    MAX(latency_ms) as max_latency_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as median_latency_ms
FROM llm_traces
WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY operation_type
ORDER BY avg_latency_ms DESC;
```

---

### 3. Job 진행 상황 추적

```sql
-- Job별 진행 상황
SELECT 
    j.job_id,
    j.status,
    j.current_step,
    j.retry_count,
    COUNT(DISTINCT jv.job_variants_id) as total_variants,
    COUNT(DISTINCT CASE WHEN jv.status = 'done' THEN jv.job_variants_id END) as completed_variants,
    COUNT(DISTINCT CASE WHEN jv.status = 'failed' THEN jv.job_variants_id END) as failed_variants
FROM jobs j
LEFT JOIN jobs_variants jv ON j.job_id = jv.job_id
WHERE j.created_at >= CURRENT_DATE - INTERVAL '1 day'
GROUP BY j.job_id, j.status, j.current_step, j.retry_count
ORDER BY j.created_at DESC;
```

---

### 4. Variant별 진행 상황

```sql
-- Variant별 진행 상황
SELECT 
    jv.job_variants_id,
    jv.job_id,
    jv.status,
    jv.current_step,
    jv.retry_count,
    jv.created_at,
    jv.updated_at,
    EXTRACT(EPOCH FROM (jv.updated_at - jv.created_at)) as duration_seconds
FROM jobs_variants jv
WHERE jv.job_id = 'your-job-id'
ORDER BY jv.creation_order;
```

---

### 5. 실패 분석

```sql
-- 실패한 Job 분석
SELECT 
    j.job_id,
    j.status,
    j.current_step,
    j.retry_count,
    COUNT(DISTINCT jv.job_variants_id) as failed_variants,
    MAX(jv.updated_at) as last_updated
FROM jobs j
INNER JOIN jobs_variants jv ON j.job_id = jv.job_id
WHERE j.status = 'failed' OR jv.status = 'failed'
  AND j.created_at >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY j.job_id, j.status, j.current_step, j.retry_count
ORDER BY last_updated DESC;
```

---

## 🔧 트러블슈팅

### 문제 1: 토큰 사용량이 null

**증상**: `llm_traces` 테이블의 토큰 관련 컬럼이 null

**원인**: OpenAI API 응답에 `usage` 정보가 없음

**해결 방법**:
```python
# usage 정보 확인 및 로깅
if response.usage:
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens
else:
    logger.warning(f"OpenAI API 응답에 usage 정보가 없습니다: {response}")
    # 기본값 설정 또는 재시도
```

---

### 문제 2: Job이 멈춤

**증상**: Job이 'running' 상태에서 멈춤

**확인 방법**:
```sql
-- 멈춘 Job 확인
SELECT 
    j.job_id,
    j.status,
    j.current_step,
    j.updated_at,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - j.updated_at)) as seconds_since_update
FROM jobs j
WHERE j.status = 'running'
  AND j.updated_at < CURRENT_TIMESTAMP - INTERVAL '1 hour'
ORDER BY j.updated_at ASC;
```

**해결 방법**:
1. 수동으로 상태 업데이트
2. 자동 복구 메커니즘 확인
3. 로그 확인

---

### 문제 3: Variant가 뒤처짐

**증상**: 일부 Variants만 진행되고 나머지는 멈춤

**확인 방법**:
```sql
-- 뒤처진 Variants 확인
SELECT 
    jv.job_variants_id,
    jv.job_id,
    jv.status,
    jv.current_step,
    jv.updated_at,
    j.current_step as job_current_step
FROM jobs_variants jv
INNER JOIN jobs j ON jv.job_id = j.job_id
WHERE j.status = 'running'
  AND jv.status != 'done'
  AND jv.current_step != j.current_step
ORDER BY jv.updated_at ASC;
```

**해결 방법**:
- 자동 복구 메커니즘이 작동합니다
- Job 상태가 변경되면 자동으로 뒤처진 Variants 복구

---

## 📝 사용 예시

### 예시 1: 비용 분석

```python
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # 작업 유형별 토큰 사용량 집계
    result = db.execute(text("""
        SELECT 
            operation_type,
            COUNT(*) as call_count,
            SUM(total_tokens) as total_tokens,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_traces
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        GROUP BY operation_type
        ORDER BY total_tokens DESC
    """))
    
    for row in result:
        print(f"{row.operation_type}: {row.total_tokens} tokens, {row.avg_latency_ms:.2f}ms")
finally:
    db.close()
```

---

### 예시 2: Job 진행 상황 확인

```python
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # Job 진행 상황 확인
    result = db.execute(text("""
        SELECT 
            j.job_id,
            j.status,
            j.current_step,
            COUNT(DISTINCT jv.job_variants_id) as total_variants,
            COUNT(DISTINCT CASE WHEN jv.status = 'done' THEN jv.job_variants_id END) as completed_variants
        FROM jobs j
        LEFT JOIN jobs_variants jv ON j.job_id = jv.job_id
        WHERE j.job_id = :job_id
        GROUP BY j.job_id, j.status, j.current_step
    """), {"job_id": job_id})
    
    row = result.first()
    if row:
        print(f"Job: {row.status}, Step: {row.current_step}")
        print(f"Variants: {row.completed_variants}/{row.total_variants} completed")
finally:
    db.close()
```

---

## 🎯 주요 포인트

1. **완전한 추적**: 모든 LLM 호출과 파이프라인 단계 추적
2. **비용 모니터링**: 토큰 사용량으로 비용 관리
3. **성능 분석**: 지연 시간으로 성능 최적화
4. **장애 복구**: 상태 관리로 자동 복구 지원

---

## 📚 관련 문서

- `DOCS_JS_PART_IMPLEMENTATION.md`: LLM 추적 구현 상세
- `DOCS_JOB_STATE_LISTENER.md`: Job 상태 관리 상세

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0


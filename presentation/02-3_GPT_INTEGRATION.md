# GPT 통합 발표자료

## 📋 개요

**기능명**: GPT (Generative Pre-trained Transformer) 통합

**목적**: 텍스트 생성 및 변환을 위한 OpenAI GPT API 통합

**핵심 가치**: 
- 다양한 텍스트 생성 작업 지원 (번역, 생성, 변환)
- 완전한 LLM 호출 추적
- 토큰 사용량 모니터링 및 비용 관리
- 인스타그램 최적화 콘텐츠 생성

---

## 🎯 목적

### 영어 → 한글 변환
- **목적**: 영어 광고문구를 한글로 변환
- **활용**: 광고문구의 한국어 버전 생성
- **출력**: 한글 광고문구, LLM Trace ID

### 인스타그램 피드 생성
- **목적**: 인스타그램에 최적화된 피드 글 생성
- **활용**: SNS 마케팅 콘텐츠 자동 생성
- **출력**: 인스타그램 광고문구, 해시태그

### 광고문구 생성 (향후 확장)
- **목적**: 제품 설명과 톤&스타일을 기반으로 광고문구 생성
- **활용**: 초기 광고문구 자동 생성
- **출력**: 영어 광고문구

---

## 🔧 주요 특징

### 1. 완전한 LLM 추적
- **모든 호출 저장**: `llm_traces` 테이블에 모든 GPT 호출 저장
- **요청/응답 저장**: JSONB 형식으로 완전한 추적
- **토큰 사용량**: prompt_tokens, completion_tokens, total_tokens 추적

### 2. 토큰 모니터링
- **비용 관리**: 토큰 사용량으로 API 비용 추정
- **사용량 분석**: 작업별, 모델별 토큰 사용량 분석
- **최적화**: 토큰 사용량 최소화를 위한 프롬프트 최적화

### 3. LLM 모델 관리
- **모델 정보 저장**: `llm_models` 테이블에 모델 정보 저장
- **활성 모델 추적**: 현재 사용 중인 모델 추적
- **모델별 통계**: 모델별 성능 및 비용 분석

### 4. 에러 처리 및 재시도
- **안정적인 처리**: API 호출 실패 시 적절한 에러 처리
- **로깅**: 상세한 로그로 디버깅 용이
- **재시도 로직**: 일시적 오류 시 자동 재시도 (향후 확장)

---

## 📁 구현 위치

### 서비스 레이어
- `services/gpt_service.py`: GPT 서비스 로직 (API 호출, 프롬프트 구성)

### API 엔드포인트
- `routers/gpt.py`: GPT API 엔드포인트 (`/api/yh/gpt/eng-to-kor`)
- `routers/instagram_feed.py`: 인스타그램 피드 생성 (`/api/yh/instagram/feed`)

### 데이터베이스
- `llm_traces` 테이블: 모든 GPT 호출 추적 및 저장
- `llm_models` 테이블: LLM 모델 정보 저장
- `txt_ad_copy_generations` 테이블: 광고문구 생성 결과 저장
- `instagram_feeds` 테이블: 인스타그램 피드 저장

---

## 💻 구현 코드

### 1. GPT 클라이언트 초기화

**파일**: `services/gpt_service.py`

```python
from openai import OpenAI
from config import GPT_API_KEY, GPT_MODEL_NAME, GPT_MAX_TOKENS

# OpenAI 클라이언트 초기화
_client: Optional[OpenAI] = None

def get_gpt_client() -> OpenAI:
    """OpenAI 클라이언트 가져오기 (싱글톤 패턴)"""
    global _client
    if _client is None:
        api_key = GPT_API_KEY
        if not api_key:
            raise ValueError(
                "OPENAPI_KEY 또는 GPT_API_KEY 환경 변수가 설정되지 않았습니다. "
                ".env 파일에 OPENAPI_KEY를 설정해주세요."
            )
        _client = OpenAI(api_key=api_key)
    return _client
```

**핵심 포인트**:
- **싱글톤 패턴**: 클라이언트를 한 번만 초기화
- **에러 처리**: API 키가 없으면 명확한 에러 메시지

---

### 2. 영어 → 한글 변환

**파일**: `services/gpt_service.py`

```python
def translate_eng_to_kor(ad_copy_eng: str) -> Dict[str, Any]:
    """
    GPT를 사용하여 영어 광고문구를 한글로 변환
    
    Args:
        ad_copy_eng: 영어 광고문구
    
    Returns:
        Dict[str, Any]: {
            "ad_copy_kor": 한글 광고문구,
            "prompt_used": 사용된 프롬프트,
            "latency_ms": API 호출 소요 시간 (밀리초),
            "token_usage": 토큰 사용량 정보,
            "gpt_response_raw": GPT API 원본 응답 (JSONB 형식)
        }
    """
    try:
        client = get_gpt_client()
        
        # 프롬프트 구성
        system_prompt = """You are an expert translator specializing in translating English ad copy to Korean.
Your task is to translate English advertising copy into natural, engaging Korean that:
1. Maintains the original meaning and intent
2. Sounds natural and authentic in Korean
3. Preserves the marketing tone and style
4. Is appropriate for Korean audiences
5. Keeps the same length and impact as the original

Return only the Korean translation without any additional explanation or formatting."""
        
        user_prompt = f"""Translate the following English ad copy to Korean:

{ad_copy_eng}

Please provide only the Korean translation, maintaining the original tone and style."""

        # GPT API 호출 (latency 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=GPT_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=GPT_MAX_TOKENS,
            temperature=0.3,  # 번역은 일관성을 위해 낮은 temperature 사용
        )
        latency_ms = (time.time() - start_time) * 1000
        
        # 응답 파싱
        response_text = response.choices[0].message.content.strip()
        ad_copy_kor = response_text
        
        # 토큰 사용량 추출
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None
        
        # 토큰 사용량 로깅
        if usage:
            logger.info(
                f"Token usage - prompt: {prompt_tokens}, "
                f"completion: {completion_tokens}, total: {total_tokens}"
            )
        else:
            logger.warning("OpenAI API 응답에 usage 정보가 없습니다.")
        
        # 프롬프트 구성 (디버깅용)
        prompt_used = f"{system_prompt}\n\n{user_prompt}"
        
        # GPT 응답 원본 저장
        gpt_response_raw = {
            "model": response.model,
            "choices": [
                {
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content
                    },
                    "finish_reason": choice.finish_reason
                }
                for choice in response.choices
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            } if usage else None
        }
        
        return {
            "ad_copy_kor": ad_copy_kor,
            "prompt_used": prompt_used,
            "latency_ms": latency_ms,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            } if usage else None,
            "gpt_response_raw": gpt_response_raw
        }
    except Exception as e:
        logger.error(f"GPT API 호출 중 오류: {e}")
        raise
```

**핵심 포인트**:
- **완전한 추적**: 모든 호출을 `llm_traces`에 저장
- **토큰 모니터링**: 비용 관리 및 최적화
- **에러 처리**: API 호출 실패 시 적절한 처리

---

### 3. 영어 → 한글 변환 API 엔드포인트

**파일**: `routers/gpt.py`

```python
@router.post("/eng-to-kor", response_model=EngToKorOut)
def eng_to_kor(body: EngToKorIn, db: Session = Depends(get_db)):
    """
    영어 광고문구를 한글로 변환
    
    Args:
        body: EngToKorIn 모델
            - job_id: Job ID
            - tenant_id: Tenant ID
    
    Returns:
        EngToKorOut:
            - job_id: Job ID
            - llm_trace_id: LLM Trace ID
            - ad_copy_gen_id: Ad Copy Generation ID
            - ad_copy_kor: 한글 광고문구
            - status: 상태 ('done' 또는 'failed')
    """
    # Step 1: Job 조회 및 검증
    job = db.query(Job).filter(Job.job_id == body.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {body.job_id}")
    
    # Step 2: txt_ad_copy_generations에서 영어 광고문구 조회
    # refined_ad_copy_eng 우선, 없으면 ad_copy_eng 사용
    ad_copy_gen = db.execute(
        text("""
            SELECT 
                ad_copy_gen_id,
                COALESCE(refined_ad_copy_eng, ad_copy_eng) AS ad_copy_eng
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
              AND (
                  (generation_stage = 'refined_ad_copy' AND refined_ad_copy_eng IS NOT NULL)
                  OR (generation_stage = 'ad_copy_eng' AND ad_copy_eng IS NOT NULL)
              )
              AND status = 'done'
            ORDER BY 
                CASE generation_stage
                    WHEN 'refined_ad_copy' THEN 1
                    WHEN 'ad_copy_eng' THEN 2
                END,
                created_at DESC
            LIMIT 1
        """),
        {"job_id": body.job_id}
    ).first()
    
    if not ad_copy_gen or not ad_copy_gen.ad_copy_eng:
        raise HTTPException(
            status_code=400,
            detail=f"English ad copy not found for job_id: {body.job_id}"
        )
    
    ad_copy_eng = ad_copy_gen.ad_copy_eng
    
    # Step 3: LLM 모델 조회
    llm_model = db.query(LLMModel).filter(
        LLMModel.model_name == GPT_MODEL_NAME,
        LLMModel.is_active == 'true'
    ).first()
    
    if not llm_model:
        logger.warning(f"⚠️ LLM 모델을 찾을 수 없습니다: {GPT_MODEL_NAME}")
        llm_model_id = None
    else:
        llm_model_id = llm_model.llm_model_id
    
    # Step 4: GPT API 호출: 영어 → 한글 변환
    try:
        result = translate_eng_to_kor(ad_copy_eng=ad_copy_eng)
    except Exception as e:
        logger.error(f"GPT API 호출 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
    
    # Step 5: llm_traces에 저장
    llm_trace_id = uuid.uuid4()
    db.execute(
        text("""
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
        """),
        {
            "llm_trace_id": llm_trace_id,
            "job_id": body.job_id,
            "llm_model_id": llm_model_id,
            "request": json.dumps({"ad_copy_eng": ad_copy_eng}),
            "response": json.dumps({"ad_copy_kor": result["ad_copy_kor"]}),
            "prompt_tokens": result["token_usage"]["prompt_tokens"] if result["token_usage"] else None,
            "completion_tokens": result["token_usage"]["completion_tokens"] if result["token_usage"] else None,
            "total_tokens": result["token_usage"]["total_tokens"] if result["token_usage"] else None,
            "token_usage": json.dumps(result["token_usage"]) if result["token_usage"] else None,
            "latency_ms": result["latency_ms"]
        }
    )
    
    # Step 6: txt_ad_copy_generations 레코드 생성/업데이트
    ad_copy_gen_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO txt_ad_copy_generations (
                ad_copy_gen_id, job_id, llm_trace_id,
                generation_stage, ad_copy_kor, status,
                created_at, updated_at
            ) VALUES (
                :ad_copy_gen_id, :job_id, :llm_trace_id,
                'eng_to_kor', :ad_copy_kor, 'done',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "ad_copy_gen_id": ad_copy_gen_id,
            "job_id": body.job_id,
            "llm_trace_id": llm_trace_id,
            "ad_copy_kor": result["ad_copy_kor"]
        }
    )
    
    # Step 7: Job 상태 업데이트
    db.execute(
        text("""
            UPDATE jobs
            SET status = 'done',
                current_step = 'ad_copy_gen_kor',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = :job_id
        """),
        {"job_id": body.job_id}
    )
    
    db.commit()
    
    return EngToKorOut(
        job_id=body.job_id,
        llm_trace_id=str(llm_trace_id),
        ad_copy_gen_id=str(ad_copy_gen_id),
        ad_copy_kor=result["ad_copy_kor"],
        status="done"
    )
```

**핵심 포인트**:
- **완전한 추적**: 모든 호출을 `llm_traces`에 저장
- **토큰 모니터링**: 비용 관리 및 최적화
- **상태 관리**: Job 상태 자동 업데이트

---

### 4. 인스타그램 피드 생성

**파일**: `services/gpt_service.py`

```python
def generate_instagram_feed(
    refined_ad_copy_eng: str,
    tone_style: str,
    product_description: str,
    store_information: str,
    gpt_prompt: str
) -> Dict[str, Any]:
    """
    GPT를 사용하여 인스타그램 피드 글 생성
    
    Args:
        refined_ad_copy_eng: 조정된 광고문구 (영어)
        tone_style: 톤 & 스타일
        product_description: 제품 설명
        store_information: 스토어 정보
        gpt_prompt: GPT 프롬프트
    
    Returns:
        Dict[str, Any]: {
            "instagram_ad_copy": 인스타그램 광고문구,
            "hashtags": 해시태그 문자열,
            "prompt_used": 사용된 프롬프트,
            "latency_ms": API 호출 소요 시간 (밀리초),
            "token_usage": 토큰 사용량 정보,
            "gpt_response_raw": GPT API 원본 응답 (JSONB 형식)
        }
    """
    try:
        client = get_gpt_client()
        
        # 프롬프트 구성
        system_prompt = """You are an expert Instagram content creator specializing in creating engaging ad copy and relevant hashtags for Korean audiences. 
Your task is to create compelling Instagram feed posts in Korean that:
1. Are engaging and authentic
2. Match the brand's tone and style
3. MUST include 5-10 relevant hashtags (this is REQUIRED, not optional)
4. Are optimized for Instagram's format
5. Encourage user engagement

IMPORTANT: You MUST always include hashtags in your response. The hashtags field must never be empty.

Format your response as JSON with the following structure:
{
    "instagram_ad_copy": "The main Instagram post text in Korean (without hashtags in the main text)",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5 ..."
}

Rules for hashtags:
- MUST include 5-10 hashtags
- Each hashtag must start with # symbol
- Separate hashtags with a single space
- Use Korean hashtags relevant to the product, store, and Korean market
- Include popular Korean food/restaurant hashtags like #맛집 #맛스타그램 #먹스타그램 #푸드스타그램
- Include location-based hashtags if store information is provided
- Hashtags should be in Korean (한글)"""
        
        user_prompt = f"""Create an Instagram feed post in Korean based on the following information:

Ad Copy (English): {refined_ad_copy_eng}
Tone & Style: {tone_style}
Product Description: {product_description}
Store Information: {store_information}

Custom Prompt: {gpt_prompt}

Please create an engaging Instagram post in Korean that includes:
1. A compelling main text (without hashtags)
2. 5-10 relevant Korean hashtags

Return your response as JSON with "instagram_ad_copy" and "hashtags" fields."""

        # GPT API 호출
        start_time = time.time()
        response = client.chat.completions.create(
            model=GPT_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=GPT_MAX_TOKENS,
            temperature=0.7,  # 창의성을 위해 중간 temperature 사용
            response_format={"type": "json_object"}  # JSON 형식 강제
        )
        latency_ms = (time.time() - start_time) * 1000
        
        # 응답 파싱
        response_text = response.choices[0].message.content.strip()
        response_json = json.loads(response_text)
        
        instagram_ad_copy = response_json.get("instagram_ad_copy", "")
        hashtags = response_json.get("hashtags", "")
        
        # 해시태그 검증
        if not hashtags:
            logger.warning("⚠️ GPT 응답에 해시태그가 없습니다. 기본 해시태그 추가.")
            hashtags = "#맛집 #맛스타그램 #먹스타그램 #푸드스타그램 #음식스타그램"
        
        # 토큰 사용량 추출
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else None
        completion_tokens = usage.completion_tokens if usage else None
        total_tokens = usage.total_tokens if usage else None
        
        # 프롬프트 구성 (디버깅용)
        prompt_used = f"{system_prompt}\n\n{user_prompt}"
        
        # GPT 응답 원본 저장
        gpt_response_raw = {
            "model": response.model,
            "choices": [
                {
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content
                    },
                    "finish_reason": choice.finish_reason
                }
                for choice in response.choices
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            } if usage else None
        }
        
        return {
            "instagram_ad_copy": instagram_ad_copy,
            "hashtags": hashtags,
            "prompt_used": prompt_used,
            "latency_ms": latency_ms,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            } if usage else None,
            "gpt_response_raw": gpt_response_raw
        }
    except Exception as e:
        logger.error(f"GPT API 호출 중 오류: {e}")
        raise
```

**핵심 포인트**:
- **SNS 최적화**: 인스타그램에 맞는 형식으로 생성
- **해시태그 자동 생성**: 관련 해시태그 자동 추출
- **JSON 형식 강제**: 구조화된 응답 보장

---

### 5. 인스타그램 피드 생성 API 엔드포인트

**파일**: `routers/instagram_feed.py`

```python
@router.post("/feed", response_model=InstagramFeedOut)
def create_instagram_feed(body: InstagramFeedIn, db: Session = Depends(get_db)):
    """
    GPT를 사용하여 인스타그램 피드 글 생성 및 DB 저장
    
    Args:
        body: InstagramFeedIn 모델
            - job_id: Job ID
            - tenant_id: Tenant ID
            - gpt_prompt: GPT 프롬프트
    
    Returns:
        InstagramFeedOut:
            - instagram_feed_id: 생성된 피드 ID
            - instagram_ad_copy: 인스타그램 광고문구
            - hashtags: 해시태그
    """
    # Step 1: Job 조회 및 검증
    job = db.query(Job).filter(Job.job_id == body.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {body.job_id}")
    
    # Step 2: txt_ad_copy_generations에서 한글 광고문구 조회
    ad_copy_kor_row = db.execute(
        text("""
            SELECT ad_copy_kor
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
              AND generation_stage = 'eng_to_kor'
              AND status = 'done'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"job_id": body.job_id}
    ).first()
    
    ad_copy_kor = ad_copy_kor_row.ad_copy_kor if ad_copy_kor_row else None
    
    # Step 3: txt_ad_copy_generations에서 refined_ad_copy_eng 조회
    refined_ad_copy_row = db.execute(
        text("""
            SELECT COALESCE(refined_ad_copy_eng, ad_copy_eng) AS refined_ad_copy_eng
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
              AND (
                  (generation_stage = 'refined_ad_copy' AND refined_ad_copy_eng IS NOT NULL)
                  OR (generation_stage = 'ad_copy_eng' AND ad_copy_eng IS NOT NULL)
              )
              AND status = 'done'
            ORDER BY 
                CASE generation_stage
                    WHEN 'refined_ad_copy' THEN 1
                    WHEN 'ad_copy_eng' THEN 2
                END,
                created_at DESC
            LIMIT 1
        """),
        {"job_id": body.job_id}
    ).first()
    
    refined_ad_copy_eng = refined_ad_copy_row.refined_ad_copy_eng if refined_ad_copy_row else None
    if not refined_ad_copy_eng:
        raise HTTPException(
            status_code=400,
            detail=f"English ad copy not found for job_id: {body.job_id}"
        )
    
    # Step 4: job_inputs에서 tone_style, product_description 조회
    job_input = db.query(JobInput).filter(JobInput.job_id == body.job_id).first()
    if not job_input:
        raise HTTPException(status_code=404, detail=f"JobInput not found: {body.job_id}")
    
    product_description = job_input.desc_kor if job_input.desc_kor else ""
    tone_style = "default"  # TODO: tone_styles 테이블에서 조회
    
    # Step 5: stores 테이블에서 스토어 정보 조회
    store_information = ""  # TODO: stores 테이블에서 조회
    
    # Step 6: GPT API 호출
    try:
        result = generate_instagram_feed(
            refined_ad_copy_eng=refined_ad_copy_eng,
            tone_style=tone_style,
            product_description=product_description,
            store_information=store_information,
            gpt_prompt=body.gpt_prompt
        )
    except Exception as e:
        logger.error(f"GPT API 호출 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Feed generation failed: {str(e)}")
    
    # Step 7: LLM 모델 조회
    llm_model = db.query(LLMModel).filter(
        LLMModel.model_name == GPT_MODEL_NAME,
        LLMModel.is_active == 'true'
    ).first()
    llm_model_id = llm_model.llm_model_id if llm_model else None
    
    # Step 8: llm_traces에 저장
    llm_trace_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO llm_traces (
                llm_trace_id, job_id, llm_model_id,
                provider, operation_type,
                request, response,
                prompt_tokens, completion_tokens, total_tokens,
                token_usage, latency_ms,
                created_at, updated_at
            ) VALUES (
                :llm_trace_id, :job_id, :llm_model_id,
                'gpt', 'feed_gen',
                CAST(:request AS jsonb), CAST(:response AS jsonb),
                :prompt_tokens, :completion_tokens, :total_tokens,
                CAST(:token_usage AS jsonb), :latency_ms,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "llm_trace_id": llm_trace_id,
            "job_id": body.job_id,
            "llm_model_id": llm_model_id,
            "request": json.dumps({
                "refined_ad_copy_eng": refined_ad_copy_eng,
                "tone_style": tone_style,
                "product_description": product_description,
                "store_information": store_information,
                "gpt_prompt": body.gpt_prompt
            }),
            "response": json.dumps({
                "instagram_ad_copy": result["instagram_ad_copy"],
                "hashtags": result["hashtags"]
            }),
            "prompt_tokens": result["token_usage"]["prompt_tokens"] if result["token_usage"] else None,
            "completion_tokens": result["token_usage"]["completion_tokens"] if result["token_usage"] else None,
            "total_tokens": result["token_usage"]["total_tokens"] if result["token_usage"] else None,
            "token_usage": json.dumps(result["token_usage"]) if result["token_usage"] else None,
            "latency_ms": result["latency_ms"]
        }
    )
    
    # Step 9: instagram_feeds에 저장
    instagram_feed_id = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO instagram_feeds (
                instagram_feed_id, job_id, llm_trace_id,
                gpt_prompt, ad_copy_kor,
                instagram_ad_copy, hashtags,
                status, created_at, updated_at
            ) VALUES (
                :instagram_feed_id, :job_id, :llm_trace_id,
                :gpt_prompt, :ad_copy_kor,
                :instagram_ad_copy, :hashtags,
                'done', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "instagram_feed_id": instagram_feed_id,
            "job_id": body.job_id,
            "llm_trace_id": llm_trace_id,
            "gpt_prompt": body.gpt_prompt,
            "ad_copy_kor": ad_copy_kor,
            "instagram_ad_copy": result["instagram_ad_copy"],
            "hashtags": result["hashtags"]
        }
    )
    
    # Step 10: Job 상태 업데이트
    db.execute(
        text("""
            UPDATE jobs
            SET status = 'done',
                current_step = 'instagram_feed_gen',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = :job_id
        """),
        {"job_id": body.job_id}
    )
    
    db.commit()
    
    return InstagramFeedOut(
        instagram_feed_id=str(instagram_feed_id),
        instagram_ad_copy=result["instagram_ad_copy"],
        hashtags=result["hashtags"]
    )
```

**핵심 포인트**:
- **SNS 최적화**: 인스타그램에 맞는 형식으로 생성
- **해시태그 자동 생성**: 관련 해시태그 자동 추출
- **완전한 추적**: 모든 생성 과정 추적

---

## 🔄 파이프라인 통합

### 영어 → 한글 변환 흐름
```
[iou_eval 완료 (모든 variants)]
  ↓
[ad_copy_gen_kor 트리거]
  ↓
[GPT API 호출: 영어 → 한글 변환]
  ↓
[결과 저장 (llm_traces, txt_ad_copy_generations)]
  ↓
[Job 상태 업데이트: done]
  ↓
[instagram_feed_gen 자동 트리거]
```

### 인스타그램 피드 생성 흐름
```
[ad_copy_gen_kor 완료]
  ↓
[instagram_feed_gen 트리거]
  ↓
[GPT API 호출: 인스타그램 피드 생성]
  ↓
[결과 저장 (llm_traces, instagram_feeds)]
  ↓
[Job 상태 업데이트: done]
  ↓
[파이프라인 완료]
```

---

## 📊 성능 및 통계

### API 응답 시간
- **영어 → 한글 변환**: 약 2-5초
- **인스타그램 피드 생성**: 약 3-7초

### 토큰 사용량
- **영어 → 한글 변환**: 평균 200-400 토큰
- **인스타그램 피드 생성**: 평균 500-1000 토큰

### 비용 추정 (gpt-4o-mini 기준)
- **영어 → 한글 변환**: 약 $0.0001-0.0002 per request
- **인스타그램 피드 생성**: 약 $0.0003-0.0006 per request

---

## 🔧 트러블슈팅

### 문제 1: 토큰 사용량이 null

**증상**: `llm_traces` 테이블의 토큰 관련 컬럼이 null

**원인**: OpenAI API 응답에 `usage` 정보가 없음

**해결 방법**:
```python
# usage 정보 확인
if response.usage:
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens
else:
    logger.warning("OpenAI API 응답에 usage 정보가 없습니다")
```

---

### 문제 2: API 호출 실패

**증상**: OpenAI API 호출 실패

**해결 방법**:
1. API 키 확인
   ```bash
   echo $OPENAPI_KEY
   ```
2. 네트워크 연결 확인
3. Rate limit 확인
4. 재시도 로직 구현 (향후 확장)

---

### 문제 3: JSON 파싱 오류

**증상**: 인스타그램 피드 생성 시 JSON 파싱 오류

**원인**: GPT 응답이 JSON 형식이 아님

**해결 방법**:
1. `response_format={"type": "json_object"}` 사용
2. 파싱 실패 시 fallback 로직 구현
3. 프롬프트에 JSON 형식 명시

---

### 문제 4: 해시태그가 생성되지 않음

**증상**: `hashtags` 필드가 비어있음

**원인**: GPT가 해시태그를 생성하지 않음

**해결 방법**:
1. 프롬프트에 해시태그 필수 명시
2. 기본 해시태그 fallback 제공
3. 해시태그 검증 로직 추가

---

### 문제 5: 번역 품질이 낮음

**증상**: 번역 결과가 자연스럽지 않음

**해결 방법**:
1. 프롬프트 개선
2. `temperature` 조정 (낮은 값으로 일관성 향상)
3. Few-shot 예제 추가

---

## 🎯 주요 포인트

### 장점
- ✅ 다양한 텍스트 생성 작업 지원
- ✅ 완전한 LLM 호출 추적
- ✅ 토큰 사용량 모니터링
- ✅ 인스타그램 최적화 콘텐츠 생성

### 활용 사례
- 영어 광고문구 → 한글 변환
- 인스타그램 피드 글 자동 생성
- 해시태그 자동 생성

---

## 📚 관련 문서

- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `DOCS_YH_PART_IMPLEMENTATION.md`: YH 파트 구현 가이드
- `presentation/05_TEXT_GENERATION_TRANSLATION.md`: 텍스트 생성 및 번역 발표자료

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0




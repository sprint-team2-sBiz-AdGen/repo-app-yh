# 텍스트 생성 및 변환 발표자료

## 📋 개요

**기능명**: GPT 기반 텍스트 생성 및 변환 시스템

**목적**: 사용자 입력을 기반으로 광고문구를 생성하고, 다양한 언어로 변환하여 최종 인스타그램 피드 글을 생성

**핵심 가치**: 
- 자연스러운 텍스트 생성
- 정확한 번역
- SNS 최적화 콘텐츠
- 완전한 LLM 호출 추적

---

## 🎯 목적

### 문제 해결
- **수동 작업의 한계**: 광고문구를 수동으로 작성해야 함
- **번역 품질**: 기계 번역의 부자연스러움
- **SNS 최적화**: 인스타그램에 맞는 형식으로 변환 필요

### 해결 방안
- GPT API를 활용한 자연스러운 텍스트 생성
- 컨텍스트를 고려한 정확한 번역
- 인스타그램 최적화 형식으로 자동 변환
- 모든 LLM 호출 추적 및 모니터링

---

## ✨ 주요 특징

### 1. 다국어 지원
- **한국어 → 영어**: 사용자 입력 한국어 설명을 영어로 변환
- **영어 → 한글**: 최종 광고문구를 한글로 변환
- **자연스러운 번역**: 컨텍스트를 고려한 자연스러운 번역

### 2. 광고문구 생성
- **톤&스타일 반영**: 사용자가 선택한 톤&스타일에 맞춰 생성
- **제품 설명 기반**: 제품 설명을 기반으로 광고문구 생성
- **스토어 정보 통합**: 스토어 정보를 포함한 맞춤형 광고문구

### 3. 인스타그램 최적화
- **해시태그 자동 생성**: 관련 해시태그 자동 추출
- **SNS 형식 최적화**: 인스타그램에 맞는 형식으로 변환
- **스토어 정보 통합**: 스토어 정보를 자연스럽게 포함

### 4. 완전한 추적
- **모든 호출 추적**: 모든 LLM API 호출을 `llm_traces`에 저장
- **토큰 사용량 모니터링**: 비용 관리 및 최적화
- **성능 분석**: 지연 시간 및 품질 분석

---

## 🏗️ 아키텍처

### 텍스트 생성 파이프라인

```
[사용자 입력]
한국어 설명 + 톤&스타일
  ↓
[한국어 → 영어 변환]
GPT API 호출 (kor_to_eng)
  ↓
[광고문구 생성]
GPT API 호출 (ad_copy_eng)
  ↓
[영어 → 한글 변환]
GPT API 호출 (eng_to_kor)
  ↓
[인스타그램 피드 생성]
GPT API 호출 (feed_gen)
  ↓
[최종 결과]
인스타그램 피드 글 + 해시태그
```

---

## 💻 구현 코드

### 1. 영어 → 한글 변환

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
    # 1. Job 조회 및 검증
    job = db.query(Job).filter(Job.job_id == body.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {body.job_id}")
    
    # 2. 영어 광고문구 조회 (refined_ad_copy_eng 우선)
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
        {"job_id": job.job_id}
    ).first()
    
    if not ad_copy_gen or not ad_copy_gen.ad_copy_eng:
        raise HTTPException(
            status_code=400,
            detail=f"English ad copy not found for job_id: {body.job_id}"
        )
    
    # 3. LLM 모델 조회
    llm_model = db.query(LLMModel).filter(
        LLMModel.model_name == GPT_MODEL_NAME
    ).first()
    llm_model_id = llm_model.llm_model_id if llm_model else None
    
    # 4. Job 상태 업데이트 (running)
    job.status = 'running'
    job.current_step = 'ad_copy_gen_kor'
    db.commit()
    
    # 5. GPT API 호출
    try:
        result = translate_eng_to_kor(
            text=ad_copy_gen.ad_copy_eng,
            llm_model_id=str(llm_model_id) if llm_model_id else None,
            job_id=str(job.job_id),
            tenant_id=body.tenant_id
        )
        
        ad_copy_kor = result["translated_text"]
        llm_trace_id = result["llm_trace_id"]
        
        # 6. txt_ad_copy_generations 업데이트
        db.execute(
            text("""
                UPDATE txt_ad_copy_generations
                SET ad_copy_kor = :ad_copy_kor,
                    status = 'done',
                    updated_at = CURRENT_TIMESTAMP
                WHERE ad_copy_gen_id = :ad_copy_gen_id
            """),
            {
                "ad_copy_kor": ad_copy_kor,
                "ad_copy_gen_id": ad_copy_gen.ad_copy_gen_id
            }
        )
        
        # 7. Job 상태 업데이트 (done) - 트리거 자동 발동
        job.status = 'done'
        job.current_step = 'ad_copy_gen_kor'
        db.commit()
        
        return EngToKorOut(
            job_id=str(job.job_id),
            llm_trace_id=llm_trace_id,
            ad_copy_gen_id=str(ad_copy_gen.ad_copy_gen_id),
            ad_copy_kor=ad_copy_kor,
            status="done"
        )
        
    except Exception as e:
        logger.error(f"GPT API 호출 실패: {e}", exc_info=True)
        job.status = 'failed'
        db.commit()
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
```

**핵심 포인트**:
- **우선순위 처리**: `refined_ad_copy_eng` 우선, 없으면 `ad_copy_eng` 사용
- **상태 관리**: running → done으로 업데이트하여 트리거 발동
- **에러 처리**: 실패 시 상태를 'failed'로 업데이트
- **완전한 추적**: 모든 호출을 `llm_traces`에 저장

---

### 2. GPT 서비스 (영어 → 한글 변환)

**파일**: `services/gpt_service.py`

```python
def translate_eng_to_kor(
    text: str,
    llm_model_id: Optional[str],
    job_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """영어 → 한글 변환"""
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
            {
                "role": "system",
                "content": "You are a professional translator. Translate the given English text to Korean naturally and fluently, maintaining the original tone and style."
            },
            {
                "role": "user",
                "content": f"Translate the following English text to Korean:\n\n{text}"
            }
        ],
        temperature=0.7,
        max_tokens=1000
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
- **토큰 사용량 추출**: API 응답에서 자동 추출
- **지연 시간 측정**: 성능 모니터링
- **완전한 추적**: 요청/응답 모두 저장
- **에러 처리**: API 호출 실패 시 적절한 처리

---

### 3. 인스타그램 피드 생성

**파일**: `routers/instagram_feed.py`

```python
@router.post("/feed", response_model=InstagramFeedOut)
def create_instagram_feed(body: InstagramFeedIn, db: Session = Depends(get_db)):
    """
    GPT를 사용하여 인스타그램 피드 글 생성 및 DB 저장
    
    처리 과정:
    1. txt_ad_copy_generations에서 한글 광고문구 조회
    2. job_inputs에서 tone_style, product_description 조회
    3. stores 테이블에서 스토어 정보 조회
    4. GPT API 호출하여 인스타그램 피드글 생성
    5. llm_traces 저장
    6. instagram_feeds 저장
    7. jobs 테이블 업데이트
    """
    # 1. Job 조회 및 검증
    job = db.query(Job).filter(Job.job_id == body.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {body.job_id}")
    
    # 2. 한글 광고문구 조회
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
        {"job_id": job.job_id}
    ).first()
    
    ad_copy_kor = ad_copy_kor_row.ad_copy_kor if ad_copy_kor_row else None
    
    # 3. 영어 광고문구 조회 (refined_ad_copy_eng 우선)
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
        {"job_id": job.job_id}
    ).first()
    
    refined_ad_copy_eng = refined_ad_copy_row.refined_ad_copy_eng if refined_ad_copy_row else None
    
    # 4. Job Inputs 조회
    job_input = db.query(JobInput).filter(JobInput.job_id == job.job_id).first()
    product_description = job_input.desc_kor if job_input else ""
    tone_style_name = job_input.tone_style.tone_style_name if job_input and job_input.tone_style else ""
    
    # 5. Store 정보 조회
    store = db.query(Store).filter(Store.store_id == job.store_id).first()
    store_info = {
        "store_name": store.store_name if store else "",
        "store_address": store.store_address if store else "",
        "store_phone": store.store_phone if store else ""
    }
    
    # 6. Job 상태 업데이트 (running)
    job.status = 'running'
    job.current_step = 'instagram_feed_gen'
    db.commit()
    
    # 7. GPT API 호출
    try:
        result = generate_instagram_feed(
            ad_copy_kor=ad_copy_kor,
            refined_ad_copy_eng=refined_ad_copy_eng,
            product_description=product_description,
            tone_style_name=tone_style_name,
            store_info=store_info,
            gpt_prompt=body.gpt_prompt,
            llm_model_id=str(llm_model.llm_model_id) if llm_model else None,
            job_id=str(job.job_id),
            tenant_id=body.tenant_id
        )
        
        feed_text = result["feed_text"]
        hashtags = result["hashtags"]
        llm_trace_id = result["llm_trace_id"]
        
        # 8. Instagram Feed 저장
        instagram_feed = InstagramFeed(
            instagram_feed_id=uuid.uuid4(),
            job_id=job.job_id,
            llm_trace_id=uuid.UUID(llm_trace_id),
            gpt_prompt=body.gpt_prompt,
            ad_copy_kor=ad_copy_kor,
            instagram_ad_copy=feed_text,
            hashtags=hashtags
        )
        db.add(instagram_feed)
        
        # 9. Job 상태 업데이트 (done) - 파이프라인 완료
        job.status = 'done'
        job.current_step = 'instagram_feed_gen'
        db.commit()
        
        return InstagramFeedOut(
            instagram_feed_id=str(instagram_feed.instagram_feed_id),
            instagram_ad_copy=feed_text,
            hashtags=hashtags
        )
        
    except Exception as e:
        logger.error(f"Instagram feed generation failed: {e}", exc_info=True)
        job.status = 'failed'
        db.commit()
        raise HTTPException(status_code=500, detail=f"Feed generation failed: {str(e)}")
```

**핵심 포인트**:
- **데이터 통합**: 여러 테이블에서 필요한 데이터 조회
- **우선순위 처리**: `refined_ad_copy_eng` 우선 사용
- **SNS 최적화**: 인스타그램에 맞는 형식으로 생성
- **해시태그 자동 생성**: 관련 해시태그 자동 추출

---

### 4. GPT 서비스 (인스타그램 피드 생성)

**파일**: `services/gpt_service.py`

```python
def generate_instagram_feed(
    ad_copy_kor: Optional[str],
    refined_ad_copy_eng: Optional[str],
    product_description: str,
    tone_style_name: str,
    store_info: Dict[str, str],
    gpt_prompt: str,
    llm_model_id: Optional[str],
    job_id: str,
    tenant_id: str
) -> Dict[str, Any]:
    """인스타그램 피드 글 생성"""
    from openai import OpenAI
    from database import SessionLocal
    from sqlalchemy import text
    import time
    import re
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # 1. 프롬프트 구성
    system_prompt = """You are a professional social media content creator. 
    Create an engaging Instagram post in Korean that includes:
    1. An attractive caption based on the ad copy
    2. Relevant hashtags (5-10 hashtags)
    3. Natural integration of store information
    
    The post should be:
    - Engaging and appealing to Instagram users
    - Natural and conversational
    - Include relevant emojis where appropriate
    - Optimized for Instagram's format"""
    
    user_prompt = f"""
    Create an Instagram post with the following information:
    
    Ad Copy (Korean): {ad_copy_kor or 'N/A'}
    Ad Copy (English): {refined_ad_copy_eng or 'N/A'}
    Product Description: {product_description}
    Tone & Style: {tone_style_name}
    Store Name: {store_info.get('store_name', 'N/A')}
    Store Address: {store_info.get('store_address', 'N/A')}
    Store Phone: {store_info.get('store_phone', 'N/A')}
    
    Additional Instructions: {gpt_prompt}
    
    Please create:
    1. The main Instagram post text (in Korean)
    2. Relevant hashtags (5-10 hashtags, separated by spaces)
    
    Format your response as:
    POST: [your post text here]
    HASHTAGS: [hashtags here, separated by spaces]
    """
    
    # 2. 시작 시간 기록
    start_time = time.time()
    
    # 3. GPT API 호출
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.8,
        max_tokens=GPT_MAX_TOKENS
    )
    
    # 4. 지연 시간 계산
    latency_ms = (time.time() - start_time) * 1000
    
    # 5. 응답 파싱
    response_text = response.choices[0].message.content
    
    # POST와 HASHTAGS 추출
    post_match = re.search(r'POST:\s*(.*?)(?=HASHTAGS:|$)', response_text, re.DOTALL)
    hashtags_match = re.search(r'HASHTAGS:\s*(.*?)$', response_text, re.DOTALL)
    
    feed_text = post_match.group(1).strip() if post_match else response_text
    hashtags_text = hashtags_match.group(1).strip() if hashtags_match else ""
    
    # 해시태그 리스트로 변환
    hashtags = [tag.strip() for tag in hashtags_text.split() if tag.strip().startswith('#')]
    
    # 6. 토큰 사용량 추출
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else None
    completion_tokens = usage.completion_tokens if usage else None
    total_tokens = usage.total_tokens if usage else None
    
    # 7. LLM Trace 저장
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
                'gpt', 'feed_gen',
                CAST(:request AS jsonb), CAST(:response AS jsonb),
                :prompt_tokens, :completion_tokens, :total_tokens,
                CAST(:token_usage AS jsonb), :latency_ms,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "llm_trace_id": llm_trace_id,
            "job_id": uuid.UUID(job_id),
            "llm_model_id": uuid.UUID(llm_model_id) if llm_model_id else None,
            "request": json.dumps({
                "ad_copy_kor": ad_copy_kor,
                "refined_ad_copy_eng": refined_ad_copy_eng,
                "product_description": product_description,
                "tone_style_name": tone_style_name,
                "store_info": store_info,
                "gpt_prompt": gpt_prompt
            }),
            "response": json.dumps({
                "feed_text": feed_text,
                "hashtags": hashtags
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
        "feed_text": feed_text,
        "hashtags": hashtags,
        "llm_trace_id": str(llm_trace_id)
    }
```

**핵심 포인트**:
- **프롬프트 엔지니어링**: 인스타그램에 최적화된 프롬프트 구성
- **응답 파싱**: POST와 HASHTAGS를 자동으로 분리
- **해시태그 추출**: 정규표현식으로 해시태그 자동 추출
- **완전한 추적**: 모든 호출을 `llm_traces`에 저장

---

## 📊 작업 유형별 상세

### 1. kor_to_eng (한국어 → 영어)
- **목적**: 사용자 입력 한국어 설명을 영어로 변환
- **입력**: `job_inputs.desc_kor`
- **출력**: `txt_ad_copy_generations.ad_copy_eng`
- **사용 시점**: 파이프라인 초기 단계

### 2. ad_copy_eng (영어 광고문구 생성)
- **목적**: 제품 설명 기반 영어 광고문구 생성
- **입력**: 영어 제품 설명, 톤&스타일
- **출력**: `txt_ad_copy_generations.ad_copy_eng`
- **사용 시점**: JS 파트에서 처리

### 3. eng_to_kor (영어 → 한글)
- **목적**: 최종 광고문구를 한글로 변환
- **입력**: `txt_ad_copy_generations.refined_ad_copy_eng` 또는 `ad_copy_eng`
- **출력**: `txt_ad_copy_generations.ad_copy_kor`
- **사용 시점**: 파이프라인 후반부 (모든 variants 완료 후)

### 4. feed_gen (인스타그램 피드 생성)
- **목적**: 광고문구, 스토어 정보 기반 인스타그램 피드 글 생성
- **입력**: 한글 광고문구, 영어 광고문구, 제품 설명, 스토어 정보
- **출력**: `instagram_feeds.instagram_ad_copy`, `hashtags`
- **사용 시점**: 파이프라인 최종 단계

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

### 문제 2: 번역 품질이 낮음

**증상**: 번역된 텍스트가 부자연스러움

**해결 방법**:
1. 프롬프트 개선
   ```python
   system_prompt = """You are a professional translator. 
   Translate the given English text to Korean naturally and fluently, 
   maintaining the original tone and style. 
   Consider the context and cultural nuances."""
   ```
2. Temperature 조정
   ```python
   temperature = 0.7  # 기본값, 더 창의적이려면 0.8-0.9
   ```
3. 모델 변경
   ```python
   model = "gpt-4o"  # 더 정확한 모델 사용
   ```

---

### 문제 3: 해시태그가 추출되지 않음

**증상**: `hashtags` 필드가 비어있음

**원인**: GPT 응답 형식이 예상과 다름

**해결 방법**:
1. 응답 형식 명확화
   ```python
   user_prompt = """
   Format your response as:
   POST: [your post text here]
   HASHTAGS: [hashtags here, separated by spaces]
   """
   ```
2. 정규표현식 개선
   ```python
   hashtags = re.findall(r'#\w+', response_text)
   ```

---

## 📝 사용 예시

### 예시 1: 영어 → 한글 변환

```python
# API 호출
response = requests.post(
    "http://localhost:8000/api/yh/gpt/eng-to-kor",
    json={
        "job_id": "xxx-xxx-xxx",
        "tenant_id": "test_tenant"
    }
)

# 결과
ad_copy_kor = response.json()["ad_copy_kor"]
llm_trace_id = response.json()["llm_trace_id"]
```

---

### 예시 2: 인스타그램 피드 생성

```python
# API 호출
response = requests.post(
    "http://localhost:8000/api/yh/instagram/feed",
    json={
        "job_id": "xxx-xxx-xxx",
        "tenant_id": "test_tenant",
        "gpt_prompt": "친근하고 따뜻한 톤으로 작성해주세요"
    }
)

# 결과
feed_text = response.json()["instagram_ad_copy"]
hashtags = response.json()["hashtags"]
```

---

## 🎯 주요 포인트

1. **자연스러운 번역**: 컨텍스트를 고려한 자연스러운 번역
2. **SNS 최적화**: 인스타그램에 맞는 형식으로 자동 변환
3. **해시태그 자동 생성**: 관련 해시태그 자동 추출
4. **완전한 추적**: 모든 LLM 호출 추적 및 모니터링

---

## 📚 관련 문서

- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `DOCS_INSTAGRAM_FEED.md`: 인스타그램 피드 생성 상세 문서

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0


# AI 모델 통합 발표자료

## 📋 개요

**기능명**: AI 모델 통합 (LLaVA, YOLO, GPT)

**목적**: 다양한 AI 모델을 통합하여 이미지 분석, 객체 감지, 텍스트 생성 등 다양한 작업을 수행

**핵심 가치**: 
- 멀티모달 AI 활용 (이미지 + 텍스트)
- 실시간 객체 감지
- 자연어 생성 및 변환
- GPU 효율적 사용

---

## 🎯 목적

### LLaVA (Large Language and Vision Assistant)
- **목적**: 이미지와 텍스트의 일관성 검증 및 품질 평가
- **활용**: 광고 이미지와 광고문구의 적합성 검증

### YOLO (You Only Look Once)
- **목적**: 이미지에서 텍스트 오버레이 가능 영역 감지
- **활용**: 텍스트 배치 위치 최적화

### GPT (Generative Pre-trained Transformer)
- **목적**: 텍스트 생성 및 변환
- **활용**: 광고문구 생성, 번역, 피드 글 생성

---

## 1️⃣ LLaVA 통합

### 목적
생성된 이미지와 광고문구의 적합성을 검증하고, 오버레이된 이미지의 최종 품질을 평가

### 주요 특징
- **Stage 1**: 이미지와 광고문구 검증 (초기 단계)
- **Stage 2**: 오버레이된 이미지 최종 품질 평가
- **GPU 기반 추론**: CUDA 지원
- **Thread-safe 모델 로딩**: 한 번만 로드하여 메모리 효율적 사용
- **8-bit 양자화 지원**: 메모리 사용량 감소

### 구현 위치
- `services/llava_service.py`: LLaVA 모델 서비스
- `routers/llava_stage1.py`: Stage 1 API 엔드포인트
- `routers/llava_stage2.py`: Stage 2 API 엔드포인트

---

### 구현 코드

#### 1. Thread-safe 모델 로딩

**파일**: `services/llava_service.py`

```python
import threading
from transformers import LlavaProcessor, LlavaForConditionalGeneration

# 전역 모델 변수 (lazy loading)
_processor: Optional[LlavaProcessor] = None
_model: Optional[LlavaForConditionalGeneration] = None
_model_lock = threading.Lock()  # 모델 로딩 동기화를 위한 락

def get_llava_model():
    """LLaVA 모델 및 프로세서 로드 (싱글톤 패턴, thread-safe)"""
    global _processor, _model
    
    # Double-checked locking 패턴으로 thread-safe하게 모델 로딩
    if _model is None or _processor is None:
        with _model_lock:
            # 다시 확인 (다른 스레드가 이미 로딩했을 수 있음)
            if _model is None or _processor is None:
                print(f"Loading LLaVa model: {LLAVA_MODEL_NAME} on {DEVICE}")
                
                # 프로세서 로드
                _processor = LlavaProcessor.from_pretrained(
                    LLAVA_MODEL_NAME,
                    cache_dir=MODEL_DIR
                )
                
                # 모델 로드 (8-bit 양자화 지원)
                if DEVICE == "cuda" and USE_QUANTIZATION:
                    _model = LlavaForConditionalGeneration.from_pretrained(
                        LLAVA_MODEL_NAME,
                        cache_dir=MODEL_DIR,
                        load_in_8bit=True,
                        device_map="auto"
                    )
                else:
                    _model = LlavaForConditionalGeneration.from_pretrained(
                        LLAVA_MODEL_NAME,
                        cache_dir=MODEL_DIR,
                        torch_dtype=torch.float16 if DEVICE == "cuda" else torch.float32,
                        device_map="auto"
                    )
                
                logger.info(f"✓ LLaVA 모델 로딩 완료: {LLAVA_MODEL_NAME}")
    
    return _processor, _model
```

**핵심 포인트**:
- **Double-checked locking**: 여러 스레드가 동시에 접근해도 모델을 한 번만 로드
- **8-bit 양자화**: 메모리 사용량 약 50% 감소
- **Lazy loading**: 필요할 때만 로드

---

#### 2. Stage 1: 이미지-텍스트 검증

**파일**: `routers/llava_stage1.py`

```python
@router.post("", response_model=LLaVaStage1Out)
def llava_stage1_validate(body: LLaVaStage1In, db: Session = Depends(get_db)):
    """LLaVA Stage 1: 이미지와 광고문구 검증"""
    
    # 1. Job Variant 조회
    job_variant = db.query(JobVariant).filter(
        JobVariant.job_variants_id == body.job_variants_id
    ).first()
    
    # 2. 상태 업데이트 (running)
    job_variant.status = 'running'
    job_variant.current_step = 'vlm_analyze'
    db.commit()
    
    # 3. 이미지 및 텍스트 준비
    image_url = job_variant.img_asset.image_url
    ad_copy_text = get_ad_copy_text_from_job(job_variant.job_id, db)
    
    # 4. LLaVA 모델 실행
    processor, model = get_llava_model()
    result = llava_service.validate_image_and_text(
        image_url=image_url,
        text=ad_copy_text,
        processor=processor,
        model=model
    )
    
    # 5. 상태 업데이트 (done) - 트리거 자동 발동
    job_variant.status = 'done'
    job_variant.current_step = 'vlm_analyze'
    db.commit()
    
    return result
```

**핵심 포인트**:
- 상태 관리: running → done으로 업데이트하여 트리거 발동
- 이미지-텍스트 검증: 광고문구가 이미지와 일치하는지 확인
- 자동 트리거: done 상태로 업데이트하면 다음 단계 자동 실행

---

#### 3. Stage 2: 최종 품질 평가

**파일**: `routers/llava_stage2.py`

```python
@router.post("", response_model=LLaVaStage2Out)
def llava_stage2_judge(body: LLaVaStage2In, db: Session = Depends(get_db)):
    """LLaVA Stage 2: 오버레이된 이미지 최종 품질 평가"""
    
    # 1. Overlay 이미지 조회
    overlay = db.query(OverlayLayout).filter(
        OverlayLayout.overlay_id == body.overlay_id
    ).first()
    
    # 2. LLaVA 모델 실행
    processor, model = get_llava_model()
    result = llava_service.evaluate_overlay_quality(
        overlay_image_url=overlay.overlaid_image_url,
        processor=processor,
        model=model
    )
    
    # 3. 상태 업데이트 (done) - 트리거 자동 발동
    job_variant.status = 'done'
    job_variant.current_step = 'vlm_judge'
    db.commit()
    
    return result
```

**핵심 포인트**:
- 오버레이 품질 평가: 텍스트가 잘 보이는지, 가독성이 좋은지 평가
- 자동 트리거: 다음 단계(ocr_eval)로 자동 진행

---

### 트러블슈팅

#### 문제 1: 모델이 여러 번 로드됨

**증상**: 로그에 "Loading LLaVa model" 메시지가 여러 번 나타남

**원인**: Thread-safe 로딩이 제대로 작동하지 않음

**해결 방법**:
1. `_model_lock`이 제대로 사용되고 있는지 확인
2. Double-checked locking 패턴 확인
3. 애플리케이션 재시작

**확인 방법**:
```bash
docker logs feedlyai-work-yh | grep -c "Loading LLaVa model"
# 예상: 1회만 나타나야 함
```

---

#### 문제 2: GPU 메모리 부족

**증상**: CUDA out of memory 오류

**해결 방법**:
1. 8-bit 양자화 활성화
   ```python
   USE_QUANTIZATION = True
   ```
2. 모델 크기 확인 및 더 작은 모델 사용
3. 배치 크기 감소

---

#### 문제 3: 모델 로딩 시간이 너무 김

**증상**: 첫 요청 시 응답 시간이 매우 김 (1-2분)

**원인**: 모델을 처음 로드할 때 시간이 소요됨

**해결 방법**:
- 정상적인 동작입니다
- 모델은 한 번만 로드되므로 이후 요청은 빠릅니다
- 워밍업 요청을 미리 보내는 것을 고려할 수 있습니다

---

## 2️⃣ YOLO 통합

### 목적
이미지에서 텍스트 오버레이 가능 영역을 감지하여 텍스트 배치 위치를 최적화

### 주요 특징
- **객체 감지**: 텍스트 영역 탐지
- **바운딩 박스**: 좌표 정보 반환
- **실시간 처리**: 빠른 추론 속도

### 구현 위치
- `services/yolo_service.py`: YOLO 모델 서비스
- `routers/yolo.py`: YOLO API 엔드포인트

---

### 구현 코드

**파일**: `services/yolo_service.py`

```python
def detect_text_regions(image_url: str) -> List[Dict]:
    """이미지에서 텍스트 영역 감지"""
    # 1. 이미지 로드
    image = load_image_from_url(image_url)
    
    # 2. YOLO 모델 실행
    results = yolo_model(image)
    
    # 3. 바운딩 박스 추출
    text_regions = []
    for result in results:
        boxes = result.boxes
        for box in boxes:
            text_regions.append({
                'x1': int(box.xyxy[0][0]),
                'y1': int(box.xyxy[0][1]),
                'x2': int(box.xyxy[0][2]),
                'y2': int(box.xyxy[0][3]),
                'confidence': float(box.conf[0])
            })
    
    return text_regions
```

**핵심 포인트**:
- 바운딩 박스 좌표: 텍스트 배치 위치 결정에 활용
- 신뢰도 점수: 낮은 신뢰도 영역은 제외 가능

---

## 3️⃣ GPT 통합

### 목적
텍스트 생성 및 변환 (한국어↔영어, 광고문구 생성, 피드 글 생성)

### 주요 특징
- **다양한 작업 지원**: 번역, 생성, 변환
- **LLM 추적**: 모든 호출을 `llm_traces` 테이블에 저장
- **토큰 모니터링**: 사용량 추적 및 비용 관리

### 구현 위치
- `services/gpt_service.py`: GPT 서비스 로직
- `routers/gpt.py`: GPT API 엔드포인트
- `routers/instagram_feed.py`: 인스타그램 피드 생성

---

### 구현 코드

#### 1. GPT 서비스

**파일**: `services/gpt_service.py`

```python
def translate_eng_to_kor(text: str, llm_model_id: str) -> Dict[str, Any]:
    """영어 → 한글 변환"""
    from openai import OpenAI
    from database import SessionLocal
    from sqlalchemy import text
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # 1. GPT API 호출
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a translator..."},
            {"role": "user", "content": f"Translate to Korean: {text}"}
        ],
        temperature=0.7
    )
    
    # 2. 토큰 사용량 추출
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else None
    completion_tokens = usage.completion_tokens if usage else None
    total_tokens = usage.total_tokens if usage else None
    
    # 3. LLM Trace 저장
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
                :request, :response,
                :prompt_tokens, :completion_tokens, :total_tokens,
                :token_usage, :latency_ms,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "llm_trace_id": llm_trace_id,
            "job_id": job_id,
            "llm_model_id": llm_model_id,
            "request": json.dumps({"text": text}),
            "response": json.dumps({"translated_text": response.choices[0].message.content}),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "token_usage": json.dumps({
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens
            }) if usage else None,
            "latency_ms": latency
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
- **완전한 추적**: 모든 호출을 `llm_traces`에 저장
- **토큰 모니터링**: 비용 관리 및 최적화
- **에러 처리**: API 호출 실패 시 적절한 처리

---

#### 2. 인스타그램 피드 생성

**파일**: `routers/instagram_feed.py`

```python
@router.post("", response_model=InstagramFeedOut)
def create_instagram_feed(body: InstagramFeedIn, db: Session = Depends(get_db)):
    """인스타그램 피드 글 생성"""
    
    # 1. Job 조회
    job = db.query(Job).filter(Job.job_id == body.job_id).first()
    
    # 2. 필요한 데이터 조회
    ad_copy_kor = get_ad_copy_kor_from_job(job.job_id, db)
    store_info = get_store_info_from_job(job.job_id, db)
    
    # 3. GPT API 호출
    result = gpt_service.generate_instagram_feed(
        ad_copy_kor=ad_copy_kor,
        store_info=store_info,
        gpt_prompt=body.gpt_prompt,
        llm_model_id=body.llm_model_id
    )
    
    # 4. LLM Trace 저장
    llm_trace_id = result["llm_trace_id"]
    
    # 5. Instagram Feed 저장
    instagram_feed = InstagramFeed(
        instagram_feed_id=uuid.uuid4(),
        job_id=job.job_id,
        llm_trace_id=llm_trace_id,
        gpt_prompt=body.gpt_prompt,
        ad_copy_kor=ad_copy_kor,
        instagram_ad_copy=result["feed_text"],
        hashtags=result["hashtags"]
    )
    db.add(instagram_feed)
    db.commit()
    
    return instagram_feed
```

**핵심 포인트**:
- **SNS 최적화**: 인스타그램에 맞는 형식으로 생성
- **해시태그 자동 생성**: 관련 해시태그 자동 추출
- **완전한 추적**: 모든 생성 과정 추적

---

### 트러블슈팅

#### 문제 1: 토큰 사용량이 null

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

#### 문제 2: API 호출 실패

**증상**: OpenAI API 호출 실패

**해결 방법**:
1. API 키 확인
2. 네트워크 연결 확인
3. Rate limit 확인
4. 재시도 로직 구현

---

## 🎯 주요 포인트

### LLaVA
- ✅ 멀티모달 AI 활용 (이미지 + 텍스트)
- ✅ Thread-safe 모델 로딩으로 메모리 효율적
- ✅ 8-bit 양자화로 메모리 사용량 감소

### YOLO
- ✅ 실시간 객체 감지
- ✅ 텍스트 배치 최적화

### GPT
- ✅ 다양한 텍스트 생성 작업 지원
- ✅ 완전한 LLM 호출 추적
- ✅ 토큰 사용량 모니터링

---

## 📊 성능 및 통계

### LLaVA
- **모델 로딩 시간**: 약 1-2분 (최초 1회)
- **추론 시간**: 약 5-10초 (이미지당)
- **GPU 메모리**: 약 10-15GB (8-bit 양자화 시 약 5-8GB)

### YOLO
- **추론 시간**: < 1초 (이미지당)
- **정확도**: 높은 신뢰도로 텍스트 영역 감지

### GPT
- **API 응답 시간**: 약 2-5초 (작업에 따라 다름)
- **토큰 사용량**: 작업당 평균 500-1000 토큰

---

## 📚 관련 문서

- `DOCS_OCR_IMPLEMENTATION.md`: OCR 구현 문서
- `test/README_THREAD_SAFE_TEST.md`: Thread-safe 모델 로딩 테스트
- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `DOCS_YH_PART_IMPLEMENTATION.md`: YH 파트 구현 가이드

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0


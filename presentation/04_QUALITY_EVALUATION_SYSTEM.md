# 품질 평가 시스템 발표자료

## 📋 개요

**기능명**: 다단계 품질 평가 시스템 (OCR, 가독성, IoU)

**목적**: 오버레이된 광고 이미지의 품질을 정량적으로 평가하여 최종 품질을 보장

**핵심 가치**: 
- 객관적 품질 측정
- 다각도 평가 (OCR, 가독성, 레이아웃)
- 자동 품질 검증
- 데이터 기반 개선

---

## 🎯 목적

### 문제 해결
- **주관적 평가의 한계**: 사람이 직접 평가하면 일관성 부족
- **품질 기준 부재**: 객관적인 품질 지표 없음
- **개선 방향 불명확**: 어떤 부분을 개선해야 할지 모름

### 해결 방안
- **OCR 평가**: 텍스트 인식 정확도 측정
- **가독성 평가**: WCAG 2.1 기준 대비 비율 측정
- **IoU 평가**: 레이아웃 정확도 측정
- **통합 평가**: 세 가지 지표를 종합하여 최종 품질 판단

---

## ✨ 주요 특징

### 1. OCR 평가
- **EasyOCR 사용**: 한글, 영어 지원
- **정확도 계산**: 원본 텍스트와 인식 결과 비교
- **다양한 메트릭**: 신뢰도, 정확도, 문자/단어 일치율

### 2. 가독성 평가
- **WCAG 2.1 준수**: 웹 접근성 가이드라인 기준
- **대비 비율 계산**: 텍스트와 배경 색상 대비 측정
- **상대 휘도**: 과학적 방법으로 가독성 계산

### 3. IoU 평가
- **레이아웃 정확도**: 제안된 위치와 실제 위치의 일치도
- **바운딩 박스 IoU**: 정확한 위치 측정
- **음식 영역 회피**: 텍스트가 음식을 가리지 않았는지 확인

---

## 🏗️ 아키텍처

### 평가 파이프라인

```
[Overlay 완료]
오버레이된 이미지 생성
  ↓
[OCR 평가]
텍스트 인식 정확도 측정
  ↓
[가독성 평가]
색상 대비 및 가독성 측정
  ↓
[IoU 평가]
레이아웃 정확도 측정
  ↓
[결과 저장]
evaluations 테이블에 저장
  ↓
[다음 단계]
모든 variants 완료 시 Job 레벨 단계로 진행
```

---

## 1️⃣ OCR 평가

### 목적
오버레이된 텍스트의 OCR 인식 정확도를 측정하여 텍스트가 제대로 읽히는지 확인

### 주요 특징
- **EasyOCR 사용**: 한글, 영어 동시 지원
- **정확도 계산**: 원본 텍스트와 인식 결과 비교
- **다양한 메트릭**: 신뢰도, 정확도, 문자/단어 일치율

### 구현 위치
- `services/ocr_service.py`: OCR 서비스 로직
- `routers/ocr_eval.py`: OCR 평가 API 엔드포인트

---

### 구현 코드

**파일**: `services/ocr_service.py`

```python
def get_ocr_reader():
    """EasyOCR Reader 싱글톤"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        from config import EASYOCR_MODEL_DIR
        
        # 한글(ko)과 영어(en) 지원
        _ocr_reader = easyocr.Reader(
            ['ko', 'en'], 
            gpu=True, 
            model_storage_directory=EASYOCR_MODEL_DIR
        )
        logger.info(f"EasyOCR Reader 초기화 완료 (한글, 영어 지원)")
    
    return _ocr_reader

def extract_text_from_image(
    image: Image.Image,
    text_region: Optional[Tuple[int, int, int, int]] = None
) -> List[Dict[str, Any]]:
    """이미지에서 텍스트 추출"""
    reader = get_ocr_reader()
    
    # 텍스트 영역이 지정된 경우 해당 영역만 추출
    if text_region:
        x1, y1, x2, y2 = text_region
        cropped_image = image.crop((x1, y1, x2, y2))
    else:
        cropped_image = image
    
    # OCR 실행
    results = reader.readtext(np.array(cropped_image))
    
    # 결과 포맷팅
    extracted_texts = []
    for (bbox, text, confidence) in results:
        extracted_texts.append({
            "text": text,
            "confidence": float(confidence),
            "bbox": bbox.tolist() if hasattr(bbox, 'tolist') else bbox
        })
    
    return extracted_texts

def calculate_ocr_accuracy(
    original_text: str,
    extracted_texts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """OCR 정확도 계산"""
    import difflib
    
    # 추출된 텍스트 합치기
    recognized_text = " ".join([item["text"] for item in extracted_texts])
    
    # 문자 단위 정확도
    char_accuracy = difflib.SequenceMatcher(
        None, 
        original_text.lower(), 
        recognized_text.lower()
    ).ratio()
    
    # 단어 단위 정확도
    original_words = original_text.lower().split()
    recognized_words = recognized_text.lower().split()
    word_accuracy = difflib.SequenceMatcher(
        None, 
        original_words, 
        recognized_words
    ).ratio()
    
    # 평균 신뢰도
    avg_confidence = sum(
        item["confidence"] for item in extracted_texts
    ) / len(extracted_texts) if extracted_texts else 0.0
    
    return {
        "original_text": original_text,
        "recognized_text": recognized_text,
        "char_accuracy": float(char_accuracy),
        "word_accuracy": float(word_accuracy),
        "avg_confidence": float(avg_confidence),
        "extracted_count": len(extracted_texts)
    }
```

**핵심 포인트**:
- **EasyOCR 싱글톤**: 모델을 한 번만 로드하여 메모리 효율적
- **다국어 지원**: 한글과 영어 동시 인식
- **정확도 계산**: 문자 단위 및 단어 단위 정확도 제공
- **신뢰도 측정**: 각 텍스트의 인식 신뢰도 제공

---

### API 엔드포인트

**파일**: `routers/ocr_eval.py`

```python
@router.post("/evaluate", response_model=OCREvalOut)
def ocr_evaluate(body: OCREvalIn, db: Session = Depends(get_db)):
    """OCR 평가 실행"""
    
    # 1. Job Variant 조회
    job_variant = db.query(JobVariant).filter(
        JobVariant.job_variants_id == body.job_variants_id
    ).first()
    
    # 2. Overlay Layout 조회
    overlay = db.query(OverlayLayout).filter(
        OverlayLayout.overlay_id == body.overlay_id
    ).first()
    
    # 3. 오버레이된 이미지 로드
    image = load_image_from_url(overlay.overlaid_image_url)
    
    # 4. 텍스트 영역 좌표 계산 (proposal 기반)
    proposal = db.query(PlannerProposal).filter(
        PlannerProposal.proposal_id == overlay.proposal_id
    ).first()
    
    xywh = json.loads(proposal.xywh)
    w, h = image.size
    x1 = int(xywh[0] * w)
    y1 = int(xywh[1] * h)
    x2 = int((xywh[0] + xywh[2]) * w)
    y2 = int((xywh[1] + xywh[3]) * h)
    text_region = (x1, y1, x2, y2)
    
    # 5. OCR 텍스트 추출
    extracted_texts = ocr_service.extract_text_from_image(
        image=image,
        text_region=text_region
    )
    
    # 6. 정확도 계산
    accuracy_result = ocr_service.calculate_ocr_accuracy(
        original_text=overlay.text,
        extracted_texts=extracted_texts
    )
    
    # 7. Evaluation 저장
    evaluation = Evaluation(
        evaluation_id=uuid.uuid4(),
        job_variants_id=job_variant.job_variants_id,
        overlay_id=overlay.overlay_id,
        evaluation_type="ocr",
        score=accuracy_result["char_accuracy"],
        metrics=json.dumps(accuracy_result),
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    db.add(evaluation)
    
    # 8. 상태 업데이트 (done) - 트리거 자동 발동
    job_variant.status = 'done'
    job_variant.current_step = 'ocr_eval'
    db.commit()
    
    return OCREvalOut(
        evaluation_id=str(evaluation.evaluation_id),
        char_accuracy=accuracy_result["char_accuracy"],
        word_accuracy=accuracy_result["word_accuracy"],
        avg_confidence=accuracy_result["avg_confidence"]
    )
```

**핵심 포인트**:
- **텍스트 영역 추출**: Proposal 좌표를 기반으로 텍스트 영역만 OCR 실행
- **정확도 계산**: 원본 텍스트와 인식 결과 비교
- **결과 저장**: evaluations 테이블에 저장하여 추적

---

## 2️⃣ 가독성 평가

### 목적
텍스트와 배경 색상의 대비를 측정하여 가독성을 평가

### 주요 특징
- **WCAG 2.1 준수**: 웹 접근성 가이드라인 기준
- **대비 비율 계산**: 과학적 방법으로 대비 측정
- **상대 휘도**: RGB 값을 상대 휘도로 변환하여 계산

### 구현 위치
- `services/readability_service.py`: 가독성 서비스 로직
- `routers/readability_eval.py`: 가독성 평가 API 엔드포인트

---

### 구현 코드

**파일**: `services/readability_service.py`

```python
def calculate_relative_luminance(r: int, g: int, b: int) -> float:
    """
    상대 휘도 계산 (WCAG 2.1)
    
    Args:
        r, g, b: RGB 값 (0-255)
    
    Returns:
        상대 휘도 (0.0-1.0)
    """
    def normalize(val: float) -> float:
        """색상 값을 정규화하고 감마 보정"""
        val = val / 255.0
        if val <= 0.03928:
            return val / 12.92
        else:
            return ((val + 0.055) / 1.055) ** 2.4
    
    r_norm = normalize(float(r))
    g_norm = normalize(float(g))
    b_norm = normalize(float(b))
    
    # WCAG 2.1 공식
    return 0.2126 * r_norm + 0.7152 * g_norm + 0.0722 * b_norm

def calculate_contrast_ratio(
    color1: Tuple[int, int, int],
    color2: Tuple[int, int, int]
) -> float:
    """
    대비 비율 계산 (WCAG 2.1)
    
    Args:
        color1, color2: RGB 튜플 (0-255)
    
    Returns:
        대비 비율 (1.0-21.0)
        - 4.5 이상: AA 등급 (일반 텍스트)
        - 7.0 이상: AAA 등급 (일반 텍스트)
        - 3.0 이상: AA 등급 (큰 텍스트)
    """
    l1 = calculate_relative_luminance(*color1)
    l2 = calculate_relative_luminance(*color2)
    
    lighter = max(l1, l2)
    darker = min(l1, l2)
    
    if darker == 0:
        return 21.0  # 최대 대비
    
    return (lighter + 0.05) / (darker + 0.05)

def sample_background_color(
    image: Image.Image,
    text_region: Tuple[int, int, int, int]
) -> Tuple[int, int, int]:
    """텍스트 영역의 배경 색상 샘플링"""
    x1, y1, x2, y2 = text_region
    region = image.crop((x1, y1, x2, y2))
    
    # 영역의 평균 색상 계산
    region_array = np.array(region)
    if len(region_array.shape) == 3:
        avg_color = region_array.mean(axis=(0, 1))
        return (int(avg_color[0]), int(avg_color[1]), int(avg_color[2]))
    else:
        # 그레이스케일인 경우
        avg_value = int(region_array.mean())
        return (avg_value, avg_value, avg_value)

def evaluate_readability(
    image: Image.Image,
    text_region: Tuple[int, int, int, int],
    text_color: str
) -> Dict[str, Any]:
    """가독성 평가"""
    
    # 1. 배경 색상 샘플링
    background_rgb = sample_background_color(image, text_region)
    
    # 2. 텍스트 색상 파싱
    text_rgb = parse_hex_rgba(text_color, (255, 255, 255, 255))[:3]
    
    # 3. 대비 비율 계산
    contrast_ratio = calculate_contrast_ratio(text_rgb, background_rgb)
    
    # 4. WCAG 등급 판정
    wcag_aa_normal = contrast_ratio >= 4.5
    wcag_aaa_normal = contrast_ratio >= 7.0
    wcag_aa_large = contrast_ratio >= 3.0
    
    return {
        "contrast_ratio": float(contrast_ratio),
        "text_color": text_rgb,
        "background_color": background_rgb,
        "wcag_aa_normal": wcag_aa_normal,
        "wcag_aaa_normal": wcag_aaa_normal,
        "wcag_aa_large": wcag_aa_large,
        "readability_score": min(1.0, contrast_ratio / 7.0)  # 0-1 정규화
    }
```

**핵심 포인트**:
- **WCAG 2.1 기준**: 웹 접근성 가이드라인 준수
- **과학적 계산**: 상대 휘도 및 대비 비율 계산
- **등급 판정**: AA, AAA 등급 자동 판정
- **배경 색상 샘플링**: 텍스트 영역의 실제 배경 색상 측정

---

## 3️⃣ IoU 평가

### 목적
오버레이된 텍스트와 원본 제안 위치의 일치도를 측정하여 레이아웃 정확도를 평가

### 주요 특징
- **바운딩 박스 IoU**: 정확한 위치 측정
- **음식 영역 회피**: 텍스트가 음식을 가리지 않았는지 확인
- **레이아웃 품질**: 제안된 위치와 실제 위치의 일치도

### 구현 위치
- `services/iou_eval_service.py`: IoU 평가 서비스 로직
- `routers/iou_eval.py`: IoU 평가 API 엔드포인트

---

### 구현 코드

**파일**: `services/iou_eval_service.py`

```python
def calculate_iou_with_food(
    text_region: Tuple[float, float, float, float],  # 정규화된 좌표
    food_boxes: List[List[float]],  # xyxy 형식
    image_width: int,
    image_height: int,
    boxes_are_normalized: bool = False
) -> Dict[str, Any]:
    """
    텍스트 영역과 음식 바운딩 박스 간 IoU 계산
    
    Returns:
        {
            "iou_with_food": float,  # 최대 IoU 값
            "max_iou_detection_id": Optional[str],
            "overlap_detected": bool,
            "all_ious": List[float]
        }
    """
    if not food_boxes:
        return {
            "iou_with_food": 0.0,
            "max_iou_detection_id": None,
            "overlap_detected": False,
            "all_ious": []
        }
    
    text_x, text_y, text_width, text_height = text_region
    text_right = text_x + text_width
    text_bottom = text_y + text_height
    text_area = text_width * text_height
    
    if text_area == 0:
        return {
            "iou_with_food": 0.0,
            "overlap_detected": False,
            "all_ious": []
        }
    
    max_iou = 0.0
    all_ious = []
    
    for i, food_box in enumerate(food_boxes):
        # food_box 형식: [x1, y1, x2, y2]
        if boxes_are_normalized:
            food_x1, food_y1, food_x2, food_y2 = food_box
        else:
            # 픽셀 좌표를 정규화
            food_x1 = food_box[0] / image_width
            food_y1 = food_box[1] / image_height
            food_x2 = food_box[2] / image_width
            food_y2 = food_box[3] / image_height
        
        # 교집합 계산
        intersect_x1 = max(text_x, food_x1)
        intersect_y1 = max(text_y, food_y1)
        intersect_x2 = min(text_right, food_x2)
        intersect_y2 = min(text_bottom, food_y2)
        
        if intersect_x2 <= intersect_x1 or intersect_y2 <= intersect_y1:
            iou = 0.0
        else:
            intersect_area = (intersect_x2 - intersect_x1) * (intersect_y2 - intersect_y1)
            food_area = (food_x2 - food_x1) * (food_y2 - food_y1)
            union_area = text_area + food_area - intersect_area
            
            if union_area == 0:
                iou = 0.0
            else:
                iou = intersect_area / union_area
        
        all_ious.append(iou)
        max_iou = max(max_iou, iou)
    
    return {
        "iou_with_food": float(max_iou),
        "overlap_detected": max_iou > 0.05,  # 5% 이상 겹치면 감지
        "all_ious": all_ious
    }

def calculate_proposal_iou(
    proposal_xywh: List[float],
    actual_xywh: List[float]
) -> float:
    """제안된 위치와 실제 위치의 IoU 계산"""
    px, py, pw, ph = proposal_xywh
    ax, ay, aw, ah = actual_xywh
    
    # 교집합 계산
    intersect_x1 = max(px, ax)
    intersect_y1 = max(py, ay)
    intersect_x2 = min(px + pw, ax + aw)
    intersect_y2 = min(py + ph, ay + ah)
    
    if intersect_x2 <= intersect_x1 or intersect_y2 <= intersect_y1:
        return 0.0
    
    intersect_area = (intersect_x2 - intersect_x1) * (intersect_y2 - intersect_y1)
    proposal_area = pw * ph
    actual_area = aw * ah
    union_area = proposal_area + actual_area - intersect_area
    
    if union_area == 0:
        return 0.0
    
    return intersect_area / union_area
```

**핵심 포인트**:
- **IoU 계산**: 정확한 겹침 비율 계산
- **음식 영역 회피**: 텍스트가 음식을 가리지 않았는지 확인
- **제안 일치도**: Planner 제안과 실제 위치의 일치도 측정

---

## 📊 평가 메트릭

### OCR 평가 메트릭

| 메트릭 | 설명 | 범위 | 목표 |
|--------|------|------|------|
| `char_accuracy` | 문자 단위 정확도 | 0.0-1.0 | > 0.9 |
| `word_accuracy` | 단어 단위 정확도 | 0.0-1.0 | > 0.85 |
| `avg_confidence` | 평균 신뢰도 | 0.0-1.0 | > 0.8 |

### 가독성 평가 메트릭

| 메트릭 | 설명 | 범위 | 목표 |
|--------|------|------|------|
| `contrast_ratio` | 대비 비율 | 1.0-21.0 | > 4.5 (AA) |
| `wcag_aa_normal` | AA 등급 달성 여부 | bool | True |
| `wcag_aaa_normal` | AAA 등급 달성 여부 | bool | True (선호) |
| `readability_score` | 가독성 점수 | 0.0-1.0 | > 0.64 (4.5/7.0) |

### IoU 평가 메트릭

| 메트릭 | 설명 | 범위 | 목표 |
|--------|------|------|------|
| `iou_with_food` | 음식과의 IoU | 0.0-1.0 | < 0.05 |
| `proposal_iou` | 제안 일치도 | 0.0-1.0 | > 0.8 |
| `overlap_detected` | 겹침 감지 여부 | bool | False |

---

## 🔧 트러블슈팅

### 문제 1: OCR 정확도가 낮음

**증상**: `char_accuracy`가 0.8 이하

**원인**:
- 폰트 크기가 너무 작음
- 텍스트 색상과 배경 대비가 낮음
- 이미지 해상도가 낮음

**해결 방법**:
1. 폰트 크기 증가
   ```python
   text_size = 40  # 기본값보다 크게
   ```
2. 색상 대비 개선
   ```python
   text_color = "ffffffff"  # 흰색
   overlay_color = "000000cc"  # 진한 검은색 배경
   ```
3. 이미지 해상도 확인
   ```python
   # 원본 이미지 해상도 확인
   image.size  # (width, height)
   ```

---

### 문제 2: 가독성 점수가 낮음

**증상**: `contrast_ratio`가 4.5 미만

**원인**: 텍스트 색상과 배경 색상의 대비가 부족

**해결 방법**:
1. 색상 대비 개선
   ```python
   # 밝은 배경에는 어두운 텍스트
   text_color = "000000ff"  # 검은색
   
   # 어두운 배경에는 밝은 텍스트
   text_color = "ffffffff"  # 흰색
   ```
2. 배경 오버레이 추가
   ```python
   overlay_color = "00000080"  # 반투명 검은색 배경
   ```
3. WCAG 2.1 기준 확인
   - AA 등급: 4.5 이상
   - AAA 등급: 7.0 이상

---

### 문제 3: IoU가 높음 (음식과 겹침)

**증상**: `iou_with_food`가 0.05 이상

**원인**: Planner가 금지 영역을 제대로 고려하지 않음

**해결 방법**:
1. YOLO 감지 결과 확인
   ```python
   # YOLO 감지 결과가 정확한지 확인
   detections = yolo_service.detect(image_url)
   ```
2. Planner IoU 임계값 조정
   ```python
   max_forbidden_iou = 0.01  # 더 엄격하게
   ```
3. 수동으로 위치 조정
   ```python
   # proposal_id 없이 직접 위치 지정
   x_align = "center"
   y_align = "bottom"
   ```

---

## 📝 사용 예시

### 예시 1: 전체 평가 파이프라인

```python
# 1. OCR 평가
ocr_result = requests.post(
    "http://localhost:8000/api/yh/ocr/evaluate",
    json={
        "job_variants_id": "xxx-xxx-xxx",
        "overlay_id": "yyy-yyy-yyy"
    }
)
print(f"OCR 정확도: {ocr_result.json()['char_accuracy']}")

# 2. 가독성 평가
readability_result = requests.post(
    "http://localhost:8000/api/yh/readability/evaluate",
    json={
        "job_variants_id": "xxx-xxx-xxx",
        "overlay_id": "yyy-yyy-yyy"
    }
)
print(f"대비 비율: {readability_result.json()['contrast_ratio']}")

# 3. IoU 평가
iou_result = requests.post(
    "http://localhost:8000/api/yh/iou/evaluate",
    json={
        "job_variants_id": "xxx-xxx-xxx",
        "overlay_id": "yyy-yyy-yyy"
    }
)
print(f"음식과의 IoU: {iou_result.json()['iou_with_food']}")
```

---

## 🎯 주요 포인트

1. **다각도 평가**: OCR, 가독성, IoU 세 가지 지표로 종합 평가
2. **객관적 측정**: 과학적 방법으로 정량적 평가
3. **자동 검증**: 파이프라인에 통합되어 자동으로 평가
4. **데이터 저장**: 모든 평가 결과를 DB에 저장하여 추적

---

## 📚 관련 문서

- `DOCS_OCR_IMPLEMENTATION.md`: OCR 구현 상세 문서
- `ANALYSIS_QUANTITATIVE_EVALUATION_IMPLEMENTATION.md`: 정량적 평가 구현 분석

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0


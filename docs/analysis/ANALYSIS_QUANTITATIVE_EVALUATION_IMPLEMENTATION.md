# 정량 평가 로직 개발 방안 분석

## 📋 개요

Overlay 이후 정량 평가는 다음 3가지로 구성됩니다:
1. **OCR**: 텍스트 인식률 확인
2. **가독성**: 텍스트와 배경 색상 대비 확인
3. **IoU**: 음식 바운딩 박스와 텍스트 영역 겹침 확인

---

## 🔍 현재 상태 분석

### ✅ 준비된 것

1. **데이터베이스 스키마**
   - `evaluations` 테이블 존재 (schema version 0.8)
   - `overlay_layouts` 테이블: 텍스트 영역 좌표, 색상 정보
   - `detections` 테이블: 음식 바운딩 박스 정보
   - `image_assets` 테이블: 이미지 크기 정보

2. **기존 함수 재사용 가능**
   - `services/planner_service.py::_compute_forbidden_iou()`: IoU 계산 함수
   - `utils.py::abs_from_url()`: URL을 절대 경로로 변환

3. **데이터 구조**
   - `overlay_layouts.layout.text`: 원본 텍스트
   - `overlay_layouts.layout.text_color`: 텍스트 색상 (hex)
   - `overlay_layouts.layout.overlay_color`: 배경 색상 (hex)
   - `overlay_layouts.layout.render.url`: 최종 렌더링 이미지 URL
   - `overlay_layouts.x_ratio, y_ratio, width_ratio, height_ratio`: 텍스트 영역 좌표

### ❌ 구현 필요한 것

1. **OCR 기능**: 전혀 구현되지 않음
2. **가독성 계산**: 색상 대비 계산 로직 없음
3. **평가 API**: 각 평가를 실행하는 API 엔드포인트 없음
4. **통합 평가**: 모든 평가를 한 번에 실행하는 로직 없음

---

## 🎯 구현 계획

### Phase 1: OCR 평가 구현

#### 1.1 라이브러리 선택 및 설치

**추천: EasyOCR**
- 딥러닝 기반으로 정확도 높음
- 한글 지원 우수
- 설치 간단: `pip install easyocr`

**대안: Tesseract OCR (pytesseract)**
- 가장 널리 사용
- 한글 지원 (추가 패키지 필요)
- 설치 복잡: 시스템에 Tesseract 설치 필요

#### 1.2 OCR 서비스 함수 작성

**파일**: `services/ocr_service.py` (신규 생성)

**주요 함수**:
```python
def extract_text_from_image(
    image: Image.Image,
    text_region: Optional[Tuple[int, int, int, int]] = None
) -> Dict[str, Any]:
    """
    이미지에서 텍스트 추출
    
    Args:
        image: PIL Image 객체
        text_region: 텍스트 영역 (x, y, width, height) - None이면 전체 이미지
    
    Returns:
        {
            "recognized_text": str,
            "confidence": float,  # 평균 신뢰도
            "details": List[Dict]  # 각 텍스트 박스별 정보
        }
    """
    pass

def calculate_ocr_accuracy(
    original_text: str,
    recognized_text: str
) -> Dict[str, Any]:
    """
    OCR 인식 정확도 계산
    
    Args:
        original_text: 원본 텍스트
        recognized_text: OCR로 인식된 텍스트
    
    Returns:
        {
            "accuracy": float,  # 전체 정확도 (0.0-1.0)
            "character_match_rate": float,  # 문자 일치율
            "word_match_rate": float,  # 단어 일치율
            "edit_distance": int,  # 편집 거리
            "similarity": float  # 유사도 (0.0-1.0)
        }
    """
    pass
```

#### 1.3 OCR 라우터 작성

**파일**: `routers/ocr_eval.py` (신규 생성)

**엔드포인트**: `POST /api/yh/ocr/evaluate`

**요청 모델**:
```python
class OCREvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 텍스트와 이미지 URL 조회
```

**응답 모델**:
```python
class OCREvalOut(BaseModel):
    job_id: str
    evaluation_id: str
    overlay_id: str
    ocr_confidence: float
    ocr_accuracy: float
    character_match_rate: float
    recognized_text: str
    original_text: str
```

#### 1.4 평가 결과 저장

**저장 위치**: `evaluations` 테이블
- `evaluation_type = 'ocr'`
- `metrics` JSONB:
```json
{
  "ocr_confidence": 0.95,
  "ocr_accuracy": 0.92,
  "character_match_rate": 0.94,
  "word_match_rate": 0.90,
  "recognized_text": "...",
  "original_text": "...",
  "edit_distance": 2,
  "similarity": 0.92
}
```

---

### Phase 2: 가독성 평가 구현

#### 2.1 대비 계산 함수 작성

**파일**: `services/readability_service.py` (신규 생성)

**주요 함수**:
```python
def calculate_relative_luminance(r: int, g: int, b: int) -> float:
    """
    상대 휘도 계산 (WCAG 2.1)
    
    Args:
        r, g, b: RGB 값 (0-255)
    
    Returns:
        상대 휘도 (0.0-1.0)
    """
    # 정규화
    def normalize(val):
        val = val / 255.0
        if val <= 0.03928:
            return val / 12.92
        else:
            return ((val + 0.055) / 1.055) ** 2.4
    
    r_norm = normalize(r)
    g_norm = normalize(g)
    b_norm = normalize(b)
    
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
    """
    l1 = calculate_relative_luminance(*color1)
    l2 = calculate_relative_luminance(*color2)
    
    lighter = max(l1, l2)
    darker = min(l1, l2)
    
    return (lighter + 0.05) / (darker + 0.05)

def evaluate_readability(
    text_color: str,  # hex color
    background_color: str,  # hex color
    text_size: Optional[int] = None  # 픽셀 단위
) -> Dict[str, Any]:
    """
    가독성 평가
    
    Args:
        text_color: 텍스트 색상 (hex, 예: "FFFFFF")
        background_color: 배경 색상 (hex, 예: "000000")
        text_size: 텍스트 크기 (픽셀) - None이면 일반 텍스트로 간주
    
    Returns:
        {
            "contrast_ratio": float,  # 대비 비율
            "wcag_aa_compliant": bool,  # WCAG AA 기준 충족
            "wcag_aaa_compliant": bool,  # WCAG AAA 기준 충족
            "readability_score": float,  # 가독성 점수 (0.0-1.0)
            "is_large_text": bool  # 큰 텍스트 여부 (18pt 이상 또는 14pt bold 이상)
        }
    """
    pass

def sample_background_color(
    image: Image.Image,
    text_region: Tuple[int, int, int, int]
) -> Tuple[int, int, int]:
    """
    텍스트 영역의 실제 배경 색상 샘플링
    
    Args:
        image: PIL Image 객체
        text_region: 텍스트 영역 (x, y, width, height)
    
    Returns:
        RGB 튜플 (0-255)
    """
    pass
```

#### 2.2 가독성 라우터 작성

**파일**: `routers/readability_eval.py` (신규 생성)

**엔드포인트**: `POST /api/yh/readability/evaluate`

**요청 모델**:
```python
class ReadabilityEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
```

**응답 모델**:
```python
class ReadabilityEvalOut(BaseModel):
    job_id: str
    evaluation_id: str
    overlay_id: str
    contrast_ratio: float
    wcag_aa_compliant: bool
    wcag_aaa_compliant: bool
    readability_score: float
```

#### 2.3 평가 결과 저장

**저장 위치**: `evaluations` 테이블
- `evaluation_type = 'readability'`
- `metrics` JSONB:
```json
{
  "contrast_ratio": 4.8,
  "wcag_aa_compliant": true,
  "wcag_aaa_compliant": false,
  "readability_score": 0.85,
  "text_color": "FFFFFF",
  "background_color": "000000",
  "is_large_text": false
}
```

---

### Phase 3: IoU 평가 구현

#### 3.1 IoU 계산 함수 재사용

**기존 함수**: `services/planner_service.py::_compute_forbidden_iou()`

**재사용 방안**:
- 텍스트 영역: `overlay_layouts`의 `x_ratio, y_ratio, width_ratio, height_ratio`
- 음식 바운딩 박스: `detections` 테이블의 `box` (xyxy 형식)
- 이미지 크기: `image_assets.width, height`

**새 함수 작성**:
```python
# services/iou_eval_service.py (신규 생성)

def calculate_iou_with_food(
    text_region: Tuple[float, float, float, float],  # 정규화된 좌표 (x, y, width, height)
    food_boxes: List[List[float]],  # xyxy 형식 (픽셀 좌표)
    image_width: int,
    image_height: int
) -> Dict[str, Any]:
    """
    텍스트 영역과 음식 바운딩 박스 간 IoU 계산
    
    Args:
        text_region: 텍스트 영역 (정규화된 좌표)
        food_boxes: 음식 바운딩 박스 리스트 (xyxy 형식, 픽셀 좌표)
        image_width, image_height: 이미지 크기
    
    Returns:
        {
            "iou_with_food": float,  # 최대 IoU 값
            "max_iou_detection_id": str,  # 최대 IoU를 가진 detection ID
            "overlap_detected": bool,  # 겹침 감지 여부
            "all_ious": List[float]  # 모든 음식과의 IoU 리스트
        }
    """
    pass
```

#### 3.2 IoU 평가 라우터 작성

**파일**: `routers/iou_eval.py` (신규 생성)

**엔드포인트**: `POST /api/yh/iou/evaluate`

**요청 모델**:
```python
class IoUEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
```

**응답 모델**:
```python
class IoUEvalOut(BaseModel):
    job_id: str
    evaluation_id: str
    overlay_id: str
    iou_with_food: float
    max_iou_detection_id: Optional[str]
    overlap_detected: bool
```

#### 3.3 평가 결과 저장

**저장 위치**: `evaluations` 테이블
- `evaluation_type = 'iou'`
- `metrics` JSONB:
```json
{
  "iou_with_food": 0.15,
  "max_iou_detection_id": "uuid-string",
  "overlap_detected": true,
  "all_ious": [0.15, 0.02, 0.0]
}
```

---

### Phase 4: 통합 평가 API

#### 4.1 통합 평가 엔드포인트

**파일**: `routers/evaluations.py` (기존 `routers/evals.py` 수정 또는 신규)

**엔드포인트**: `POST /api/yh/evaluations/full`

**요청 모델**:
```python
class FullEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
    evaluation_types: Optional[List[str]] = None  # ['ocr', 'readability', 'iou'] - None이면 모두 실행
```

**응답 모델**:
```python
class FullEvalOut(BaseModel):
    job_id: str
    overlay_id: str
    evaluations: Dict[str, Any]  # 각 평가 타입별 결과
    overall_score: float  # 종합 점수 (0.0-1.0)
```

#### 4.2 실행 순서

1. LLaVA Stage 2 결과 확인 (이미 실행되어 있어야 함)
2. OCR 평가 실행
3. 가독성 평가 실행
4. IoU 평가 실행
5. 종합 점수 계산
6. Job 상태 업데이트 (`current_step='evaluation'`, `status='done'`)

---

## 📊 데이터 흐름

```
1. Overlay 완료
   ↓
2. LLaVA Stage 2 실행 (이미 구현됨)
   ↓
3. 정량 평가 실행
   ├─ OCR 평가
   │  ├─ overlay_layouts에서 텍스트와 이미지 URL 조회
   │  ├─ OCR 실행
   │  └─ evaluations 테이블에 저장
   │
   ├─ 가독성 평가
   │  ├─ overlay_layouts에서 색상 정보 조회
   │  ├─ 대비 비율 계산
   │  └─ evaluations 테이블에 저장
   │
   └─ IoU 평가
      ├─ overlay_layouts에서 텍스트 영역 좌표 조회
      ├─ detections에서 음식 바운딩 박스 조회
      ├─ IoU 계산
      └─ evaluations 테이블에 저장
   ↓
4. 종합 판단
   ├─ LLaVA Stage 2 결과
   ├─ OCR 결과
   ├─ 가독성 결과
   └─ IoU 결과
   ↓
5. 최종 승인/거부 결정
```

---

## 🔧 구현 순서

### Step 1: 의존성 추가
```bash
# requirements.txt 또는 pyproject.toml에 추가
easyocr>=1.7.0  # OCR용
```

### Step 2: OCR 서비스 구현
1. `services/ocr_service.py` 생성
2. `extract_text_from_image()` 함수 구현
3. `calculate_ocr_accuracy()` 함수 구현

### Step 3: OCR 라우터 구현
1. `routers/ocr_eval.py` 생성
2. `POST /api/yh/ocr/evaluate` 엔드포인트 구현
3. DB 저장 로직 구현

### Step 4: 가독성 서비스 구현
1. `services/readability_service.py` 생성
2. `calculate_relative_luminance()` 함수 구현
3. `calculate_contrast_ratio()` 함수 구현
4. `evaluate_readability()` 함수 구현

### Step 5: 가독성 라우터 구현
1. `routers/readability_eval.py` 생성
2. `POST /api/yh/readability/evaluate` 엔드포인트 구현
3. DB 저장 로직 구현

### Step 6: IoU 평가 서비스 구현
1. `services/iou_eval_service.py` 생성
2. `calculate_iou_with_food()` 함수 구현
3. 기존 `_compute_forbidden_iou()` 함수 재사용

### Step 7: IoU 평가 라우터 구현
1. `routers/iou_eval.py` 생성
2. `POST /api/yh/iou/evaluate` 엔드포인트 구현
3. DB 저장 로직 구현

### Step 8: 통합 평가 API 구현
1. `routers/evaluations.py` 수정 또는 신규 생성
2. `POST /api/yh/evaluations/full` 엔드포인트 구현
3. 모든 평가를 순차적으로 실행
4. 종합 점수 계산

### Step 9: 모델 정의
1. `models.py`에 평가 관련 모델 추가
   - `OCREvalIn`, `OCREvalOut`
   - `ReadabilityEvalIn`, `ReadabilityEvalOut`
   - `IoUEvalIn`, `IoUEvalOut`
   - `FullEvalIn`, `FullEvalOut`

### Step 10: 테스트
1. 각 평가 API 단위 테스트
2. 통합 평가 API 테스트
3. DB 저장 및 조회 테스트

---

## ⚠️ 주의사항

1. **OCR 정확도**
   - 한글 인식률이 영어보다 낮을 수 있음
   - 폰트, 크기, 배경에 따라 인식률 차이 발생
   - 신뢰도 임계값 설정 필요

2. **대비 계산**
   - 실제 배경 색상은 이미지에서 샘플링해야 정확함
   - 오버레이 배경 색상과 실제 이미지 배경 색상 모두 고려

3. **IoU 계산**
   - 음식 바운딩 박스가 여러 개일 경우 최대 IoU 사용
   - 정규화된 좌표와 픽셀 좌표 변환 주의

4. **성능**
   - OCR은 시간이 오래 걸릴 수 있음 (비동기 처리 고려)
   - EasyOCR은 첫 실행 시 모델 다운로드 필요

5. **에러 처리**
   - 각 평가 단계에서 실패해도 다른 평가는 계속 진행
   - 부분 실패 시에도 가능한 결과는 반환

---

## 📚 참고 자료

- WCAG 2.1 대비 비율: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- EasyOCR: https://github.com/JaidedAI/EasyOCR
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- IoU 계산: https://en.wikipedia.org/wiki/Jaccard_index

---

**작성일:** 2025-11-26  
**작성자:** LEEYH205  
**버전:** 1.0.0


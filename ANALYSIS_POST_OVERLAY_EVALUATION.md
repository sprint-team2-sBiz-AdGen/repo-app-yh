# Overlay 이후 LLaVA Stage 2 및 정량 평가 구현 분석

## 📋 요구사항

Overlay 이후 다음 작업을 수행해야 함:

1. **LLaVA Stage 2 (Judge)**: 최종 광고 시각 결과물 판단
2. **정량 평가**:
   - **OCR**: 텍스트 인식률 확인
   - **가독성**: 텍스트와 배경 색상 대비 확인
   - **IoU**: 음식 바운딩 박스와 텍스트 영역 겹침 확인

---

## 🔍 현재 코드베이스 분석

### 1. LLaVA Stage 2 현황

#### 현재 구현 상태
- **파일**: `routers/llava_stage2.py`, `services/llava_service.py::judge_final_ad()`
- **기능**: 기본 구조만 존재, 파싱 로직이 매우 간단함
- **문제점**:
  - 응답 파싱이 키워드 기반으로만 동작 (신뢰도 낮음)
  - JSON 형식으로 구조화된 응답 추출 필요
  - DB 저장 로직 없음 (vlm_traces에 저장해야 함)
  - job 상태 업데이트 없음

#### 현재 반환값
```python
{
    "on_brief": bool,      # brief 준수 여부
    "occlusion": bool,     # 가림 여부 (True면 가림 있음)
    "contrast_ok": bool,   # 대비 적절성
    "cta_present": bool,   # CTA 존재 여부
    "analysis": str,       # LLaVA 분석 텍스트
    "issues": List[str]    # 발견된 이슈 목록
}
```

#### 개선 필요사항
1. **프롬프트 개선**: JSON 형식 응답 요구
2. **파싱 로직 개선**: 정규식 또는 JSON 파싱으로 구조화된 데이터 추출
3. **DB 저장**: `vlm_traces` 테이블에 `operation_type='judge'`로 저장
4. **job 상태 업데이트**: `current_step='vlm_judge'`, `status='running'` → `status='done'`

---

### 2. OCR (텍스트 인식률) 현황

#### 현재 구현 상태
- **구현 없음**: OCR 기능이 전혀 구현되어 있지 않음
- **필요 라이브러리**: `pytesseract` (Tesseract OCR) 또는 `easyocr`, `paddleocr`

#### 구현 방안
1. **라이브러리 선택**:
   - **Tesseract OCR (pytesseract)**: 가장 널리 사용, 한글 지원
   - **EasyOCR**: 딥러닝 기반, 정확도 높음, 한글 지원
   - **PaddleOCR**: 중국 개발, 한글 지원 우수

2. **구현 내용**:
   - 최종 렌더링된 이미지에서 텍스트 영역 추출
   - OCR 실행하여 인식된 텍스트와 원본 텍스트 비교
   - 인식률 계산: `(일치하는 문자 수 / 전체 문자 수) * 100`

3. **입력 데이터**:
   - `overlay_layouts.layout.text`: 원본 텍스트
   - `overlay_layouts.layout.render.url`: 최종 렌더링 이미지 URL
   - `overlay_layouts.x_ratio, y_ratio, width_ratio, height_ratio`: 텍스트 영역 좌표

4. **출력 메트릭**:
   - `ocr_confidence`: OCR 신뢰도 (0.0-1.0)
   - `ocr_accuracy`: 인식 정확도 (0.0-1.0)
   - `recognized_text`: 인식된 텍스트
   - `character_match_rate`: 문자 일치율

---

### 3. 가독성 (색상 대비) 현황

#### 현재 구현 상태
- **구현 없음**: 색상 대비 계산 기능이 없음

#### 구현 방안
1. **WCAG 2.1 대비 비율 계산**:
   - 텍스트 색상과 배경 색상의 상대 휘도 계산
   - 대비 비율 = (밝은 색 휘도 + 0.05) / (어두운 색 휘도 + 0.05)
   - WCAG AA 기준: 일반 텍스트 4.5:1, 큰 텍스트 3:1
   - WCAG AAA 기준: 일반 텍스트 7:1, 큰 텍스트 4.5:1

2. **구현 내용**:
   - `overlay_layouts.layout.text_color`: 텍스트 색상 (hex)
   - `overlay_layouts.layout.overlay_color`: 배경 색상 (hex)
   - 텍스트 영역의 실제 배경 색상 샘플링 (이미지에서 추출)
   - 상대 휘도 계산 및 대비 비율 계산

3. **입력 데이터**:
   - `overlay_layouts.layout.text_color`: 텍스트 색상
   - `overlay_layouts.layout.overlay_color`: 오버레이 배경 색상
   - 최종 렌더링 이미지에서 텍스트 영역의 실제 배경 색상

4. **출력 메트릭**:
   - `contrast_ratio`: 대비 비율 (예: 4.5:1 → 4.5)
   - `readability_score`: 가독성 점수 (0.0-1.0)
   - `wcag_aa_compliant`: WCAG AA 기준 충족 여부
   - `wcag_aaa_compliant`: WCAG AAA 기준 충족 여부

---

### 4. IoU (음식 바운딩 박스와 텍스트 영역 겹침) 현황

#### 현재 구현 상태
- **구현 있음**: `services/planner_service.py::_compute_forbidden_iou()`
- **기능**: 제안 영역과 금지 영역 간 IoU 계산
- **재사용 가능**: 기존 함수를 활용하여 평가용 IoU 계산

#### 구현 방안
1. **기존 함수 활용**:
   - `_compute_forbidden_iou()` 함수 재사용
   - 텍스트 영역: `overlay_layouts`의 `x_ratio, y_ratio, width_ratio, height_ratio`
   - 음식 바운딩 박스: `detections` 테이블의 `box` (xyxy 형식)

2. **입력 데이터**:
   - `overlay_layouts.x_ratio, y_ratio, width_ratio, height_ratio`: 텍스트 영역 (정규화된 좌표)
   - `detections.box`: 음식 바운딩 박스 (xyxy 형식, 픽셀 좌표)
   - 이미지 크기: `image_assets.width, height`

3. **계산 로직**:
   - 음식 바운딩 박스를 정규화된 좌표로 변환
   - 텍스트 영역과 각 음식 바운딩 박스 간 IoU 계산
   - 최대 IoU 값 반환 (여러 음식이 있을 경우)

4. **출력 메트릭**:
   - `iou_with_food`: 음식과의 IoU (0.0-1.0)
   - `max_iou_detection_id`: 최대 IoU를 가진 detection ID
   - `overlap_detected`: 겹침 감지 여부 (IoU > 0.0)

---

## 📊 데이터베이스 구조 분석

### 현재 테이블 구조

#### 1. `overlay_layouts` 테이블
```python
- overlay_id: UUID (PK)
- proposal_id: UUID (FK → planner_proposals)
- layout: JSONB {
    "text": str,              # 원본 텍스트
    "text_color": str,        # 텍스트 색상 (hex)
    "overlay_color": str,     # 배경 색상 (hex)
    "render": {               # 렌더링 메타데이터
        "url": str,           # 최종 이미지 URL
        "width": int,
        "height": int,
        ...
    }
}
- x_ratio: float              # 텍스트 영역 x 좌표 (정규화)
- y_ratio: float              # 텍스트 영역 y 좌표 (정규화)
- width_ratio: float          # 텍스트 영역 너비 (정규화)
- height_ratio: float         # 텍스트 영역 높이 (정규화)
```

#### 2. `detections` 테이블
```python
- detection_id: UUID (PK)
- job_id: UUID (FK → jobs)
- image_asset_id: UUID (FK → image_assets)
- box: JSONB [x1, y1, x2, y2]  # 바운딩 박스 (픽셀 좌표)
- label: str                   # 라벨 (예: "bowl", "person")
- score: float                 # 신뢰도
```

#### 3. `vlm_traces` 테이블
```python
- vlm_trace_id: UUID (PK)
- job_id: UUID (FK → jobs)
- provider: str                # "llava"
- operation_type: str          # "analyze", "planner", "judge"
- request: JSONB
- response: JSONB
```

### 평가 결과 저장 방안

#### 옵션 1: 새로운 `evaluations` 테이블 생성 (권장)
```sql
CREATE TABLE evaluations (
    evaluation_id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(job_id),
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),
    evaluation_type VARCHAR(50),  -- 'llava_judge', 'ocr', 'readability', 'iou'
    metrics JSONB,                -- 평가 메트릭
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### 옵션 2: `vlm_traces` 테이블 활용
- LLaVA Stage 2 결과는 `vlm_traces`에 저장
- OCR, 가독성, IoU는 별도 테이블 필요

#### 옵션 3: `overlay_layouts.layout` JSONB에 추가
- 평가 결과를 `layout.evaluation` 필드에 저장
- 단순하지만 쿼리 및 분석이 어려움

**추천**: 옵션 1 (새로운 `evaluations` 테이블)

---

## 🔧 구현 계획

### Phase 1: LLaVA Stage 2 개선

#### 1.1 프롬프트 개선
- JSON 형식 응답 요구
- 구조화된 필드 추출 (on_brief, occlusion, contrast_ok, cta_present)

#### 1.2 파싱 로직 개선
- JSON 파싱 시도
- 실패 시 정규식으로 fallback
- 신뢰도 높은 파싱 보장

#### 1.3 DB 저장
- `vlm_traces` 테이블에 저장
- `operation_type='judge'`
- `response` JSONB에 결과 저장

#### 1.4 Job 상태 업데이트
- `current_step='vlm_judge'`, `status='running'` → `status='done'`

---

### Phase 2: OCR 구현

#### 2.1 라이브러리 선택 및 설치
- **추천**: EasyOCR (한글 지원 우수, 정확도 높음)
- 또는 Tesseract OCR (pytesseract)

#### 2.2 OCR 서비스 함수 작성
- `services/ocr_service.py` 생성
- `extract_text_from_image()` 함수
- `calculate_ocr_accuracy()` 함수

#### 2.3 OCR 라우터 작성
- `routers/ocr.py` 생성
- `/api/yh/ocr/evaluate` 엔드포인트
- 입력: `job_id`, `overlay_id` (또는 `render_asset_url`)

#### 2.4 평가 결과 저장
- `evaluations` 테이블에 저장
- `evaluation_type='ocr'`
- `metrics` JSONB에 결과 저장

---

### Phase 3: 가독성 (색상 대비) 구현

#### 3.1 대비 계산 함수 작성
- `services/readability_service.py` 생성
- `calculate_contrast_ratio()` 함수
- `calculate_relative_luminance()` 함수
- WCAG 2.1 기준 검증

#### 3.2 배경 색상 추출
- 텍스트 영역의 실제 배경 색상 샘플링
- 오버레이 배경 색상과 실제 이미지 배경 색상 모두 고려

#### 3.3 가독성 라우터 작성
- `routers/readability.py` 생성
- `/api/yh/readability/evaluate` 엔드포인트

#### 3.4 평가 결과 저장
- `evaluations` 테이블에 저장
- `evaluation_type='readability'`

---

### Phase 4: IoU 평가 구현

#### 4.1 IoU 계산 함수 재사용
- `services/planner_service.py::_compute_forbidden_iou()` 활용
- 또는 별도 평가용 함수 작성

#### 4.2 데이터 조회
- `overlay_layouts`에서 텍스트 영역 좌표 조회
- `detections`에서 음식 바운딩 박스 조회
- `image_assets`에서 이미지 크기 조회

#### 4.3 IoU 평가 라우터 작성
- `routers/iou_eval.py` 생성
- `/api/yh/iou/evaluate` 엔드포인트

#### 4.4 평가 결과 저장
- `evaluations` 테이블에 저장
- `evaluation_type='iou'`

---

### Phase 5: 통합 평가 API

#### 5.1 통합 평가 엔드포인트
- `/api/yh/evaluations/full` 엔드포인트
- 모든 평가를 한 번에 실행
- 순서: LLaVA Stage 2 → OCR → 가독성 → IoU

#### 5.2 Job 상태 관리
- `current_step='evaluation'`, `status='running'` → `status='done'`

---

## 📝 API 설계

### 1. LLaVA Stage 2 Judge API

#### 엔드포인트
```
POST /api/yh/llava/stage2/judge
```

#### 요청 모델
```python
class JudgeIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: Optional[str] = None  # overlay_id가 있으면 자동으로 render_asset_url 조회
    render_asset_url: Optional[str] = None  # 직접 URL 제공 가능
```

#### 응답 모델
```python
class JudgeOut(BaseModel):
    job_id: str
    vlm_trace_id: str
    on_brief: bool
    occlusion: bool  # True면 가림 있음
    contrast_ok: bool
    cta_present: bool
    analysis: str
    issues: List[str]
```

---

### 2. OCR 평가 API

#### 엔드포인트
```
POST /api/yh/ocr/evaluate
```

#### 요청 모델
```python
class OCREvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str  # overlay_layouts에서 텍스트와 이미지 URL 조회
```

#### 응답 모델
```python
class OCREvalOut(BaseModel):
    evaluation_id: str
    job_id: str
    overlay_id: str
    ocr_confidence: float  # OCR 신뢰도 (0.0-1.0)
    ocr_accuracy: float   # 인식 정확도 (0.0-1.0)
    recognized_text: str   # 인식된 텍스트
    original_text: str    # 원본 텍스트
    character_match_rate: float  # 문자 일치율
```

---

### 3. 가독성 평가 API

#### 엔드포인트
```
POST /api/yh/readability/evaluate
```

#### 요청 모델
```python
class ReadabilityEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
```

#### 응답 모델
```python
class ReadabilityEvalOut(BaseModel):
    evaluation_id: str
    job_id: str
    overlay_id: str
    contrast_ratio: float  # 대비 비율 (예: 4.5)
    readability_score: float  # 가독성 점수 (0.0-1.0)
    wcag_aa_compliant: bool  # WCAG AA 기준 충족
    wcag_aaa_compliant: bool  # WCAG AAA 기준 충족
    text_color: str  # 텍스트 색상 (hex)
    background_color: str  # 배경 색상 (hex)
```

---

### 4. IoU 평가 API

#### 엔드포인트
```
POST /api/yh/iou/evaluate
```

#### 요청 모델
```python
class IoUEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
```

#### 응답 모델
```python
class IoUEvalOut(BaseModel):
    evaluation_id: str
    job_id: str
    overlay_id: str
    iou_with_food: float  # 음식과의 IoU (0.0-1.0)
    max_iou_detection_id: Optional[str]  # 최대 IoU를 가진 detection ID
    overlap_detected: bool  # 겹침 감지 여부
    text_region: Dict[str, float]  # 텍스트 영역 좌표
    food_boxes: List[Dict]  # 음식 바운딩 박스 리스트
```

---

### 5. 통합 평가 API

#### 엔드포인트
```
POST /api/yh/evaluations/full
```

#### 요청 모델
```python
class FullEvalIn(BaseModel):
    job_id: str
    tenant_id: str
    overlay_id: str
    skip_llava: bool = False
    skip_ocr: bool = False
    skip_readability: bool = False
    skip_iou: bool = False
```

#### 응답 모델
```python
class FullEvalOut(BaseModel):
    job_id: str
    overlay_id: str
    llava_judge: Optional[JudgeOut] = None
    ocr_eval: Optional[OCREvalOut] = None
    readability_eval: Optional[ReadabilityEvalOut] = None
    iou_eval: Optional[IoUEvalOut] = None
    overall_score: float  # 종합 점수 (0.0-1.0)
```

---

## 🗄️ 데이터베이스 스키마

### evaluations 테이블 생성

```sql
CREATE TABLE evaluations (
    evaluation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(job_id),
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),
    evaluation_type VARCHAR(50) NOT NULL,  -- 'llava_judge', 'ocr', 'readability', 'iou'
    metrics JSONB NOT NULL,  -- 평가 메트릭 (타입별로 다른 구조)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- 인덱스
    INDEX idx_evaluations_job_id (job_id),
    INDEX idx_evaluations_overlay_id (overlay_id),
    INDEX idx_evaluations_type (evaluation_type)
);
```

### metrics JSONB 구조 예시

#### LLaVA Judge
```json
{
    "on_brief": true,
    "occlusion": false,
    "contrast_ok": true,
    "cta_present": true,
    "analysis": "...",
    "issues": []
}
```

#### OCR
```json
{
    "ocr_confidence": 0.95,
    "ocr_accuracy": 0.98,
    "recognized_text": "매콤라면 떡볶이",
    "original_text": "매콤라면 떡볶이",
    "character_match_rate": 0.98
}
```

#### Readability
```json
{
    "contrast_ratio": 4.8,
    "readability_score": 0.85,
    "wcag_aa_compliant": true,
    "wcag_aaa_compliant": false,
    "text_color": "FFFFFF",
    "background_color": "000000"
}
```

#### IoU
```json
{
    "iou_with_food": 0.02,
    "max_iou_detection_id": "uuid",
    "overlap_detected": false,
    "text_region": {"x": 0.1, "y": 0.05, "width": 0.8, "height": 0.18},
    "food_boxes": [{"detection_id": "uuid", "box": [x1, y1, x2, y2], "iou": 0.02}]
}
```

---

## 🧪 테스트 계획

### 1. 단위 테스트
- OCR 정확도 계산 테스트
- 대비 비율 계산 테스트
- IoU 계산 테스트
- LLaVA Stage 2 파싱 테스트

### 2. 통합 테스트
- 전체 평가 파이프라인 테스트
- DB 저장 및 조회 테스트
- Job 상태 업데이트 테스트

### 3. 성능 테스트
- OCR 처리 시간 측정
- 전체 평가 시간 측정
- 동시 요청 처리 테스트

---

## 📦 의존성 추가

### OCR 라이브러리
```bash
# EasyOCR (추천)
pip install easyocr

# 또는 Tesseract OCR
pip install pytesseract
# 시스템에 Tesseract 설치 필요: apt-get install tesseract-ocr tesseract-ocr-kor
```

### 색상 계산
```python
# 이미 PIL, numpy 사용 중이므로 추가 의존성 없음
# 대비 계산은 수학적 계산으로 구현 가능
```

---

## 🚀 구현 순서

1. **데이터베이스 스키마 생성**: `evaluations` 테이블 생성
2. **LLaVA Stage 2 개선**: 프롬프트 및 파싱 로직 개선
3. **OCR 구현**: EasyOCR 또는 Tesseract 통합
4. **가독성 구현**: 대비 비율 계산 로직 구현
5. **IoU 평가 구현**: 기존 함수 재사용하여 평가 로직 구현
6. **통합 평가 API**: 모든 평가를 한 번에 실행하는 API 구현
7. **테스트**: 단위 테스트 및 통합 테스트 작성

---

## ⚠️ 주의사항

1. **OCR 정확도**: 한글 인식률이 영어보다 낮을 수 있음
2. **대비 계산**: 실제 배경 색상은 이미지에서 샘플링해야 정확함
3. **IoU 계산**: 음식 바운딩 박스가 여러 개일 경우 최대 IoU 사용
4. **성능**: OCR은 시간이 오래 걸릴 수 있음 (비동기 처리 고려)
5. **에러 처리**: 각 평가 단계에서 실패해도 다른 평가는 계속 진행

---

## 📚 참고 자료

- WCAG 2.1 대비 비율: https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html
- EasyOCR: https://github.com/JaidedAI/EasyOCR
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- IoU 계산: https://en.wikipedia.org/wiki/Jaccard_index


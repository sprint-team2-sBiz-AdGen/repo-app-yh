# LLaVA 폰트 추천 기능 구현 분석

## 1. 개요

LLaVA Stage 1에서 이미지와 광고문구를 분석한 결과를 바탕으로 폰트, 폰트 사이즈, 폰트 색깔을 추천하고, 이를 Overlay API로 전달하는 기능을 구현하는 방안을 분석합니다.

## 2. 현재 구조 분석

### 2.1 LLaVA Stage 1 (`routers/llava_stage1.py`)
- **기능**: 이미지와 광고문구의 적합성 검증
- **입력**: `LLaVaStage1In` (job_id, tenant_id, asset_url, ad_copy_text, prompt)
- **출력**: `LLaVaStage1Out` (job_id, vlm_trace_id, is_valid, relevance_score, analysis, issues, recommendations)
- **DB 저장**: `vlm_traces` 테이블의 `response` JSONB 필드에 검증 결과 저장
- **LLaVA 서비스**: `services/llava_service.py`의 `validate_image_and_text()` 함수 사용

### 2.2 Overlay API (`routers/overlay.py`)
- **기능**: 이미지에 텍스트 오버레이 적용
- **입력**: `OverlayIn` 모델
  - `text_size: int = 32` (기본값)
  - `text_color: Optional[str] = "ffffffff"` (기본값: 흰색)
  - 폰트는 하드코딩된 경로 리스트에서 선택 (`font_paths`)
- **현재 폰트 선택 로직**: 
  - 여러 폰트 경로 후보 중 사용 가능한 첫 번째 폰트 사용
  - 폰트 크기는 영역 크기에 따라 동적으로 조정 (`_fit_text()` 함수)
- **Planner 연동**: `proposal_id`를 통해 `planner_proposals` 테이블에서 `color`, `size` 정보를 가져옴

### 2.3 데이터베이스 스키마
- **`vlm_traces` 테이블**:
  - `response` (JSONB): LLaVA 분석 결과 저장
  - 현재 구조: `{is_valid, image_quality_ok, relevance_score, analysis, issues, recommendations}`
- **`planner_proposals` 테이블**:
  - `color` (String): 텍스트 색상 (hex)
  - `size` (Integer): 텍스트 크기
  - 이미 Planner에서 색상과 크기를 제안하고 있음

## 3. 구현 방안

### 3.1 방안 A: LLaVA Stage 1에서 폰트 추천 추가 (권장)

#### 3.1.1 LLaVA 프롬프트 확장
`services/llava_service.py`의 `validate_image_and_text()` 함수에서 폰트 추천을 위한 추가 프롬프트를 생성합니다.

**프롬프트 예시**:
```
Based on the image analysis and ad copy, recommend:
1. Font style: [serif/sans-serif/bold/italic] - Choose based on image mood (formal/casual/playful)
2. Font size: [small/medium/large] - Recommend based on image composition and text length
3. Font color: [hex color code] - Recommend based on image background colors for optimal contrast

Provide recommendations in JSON format:
{
  "font_style": "sans-serif",
  "font_size_category": "medium",
  "font_color_hex": "FFFFFF",
  "reasoning": "Brief explanation"
}
```

#### 3.1.2 응답 모델 확장
`models.py`의 `LLaVaStage1Out` 모델에 폰트 추천 필드 추가:

```python
class FontRecommendation(BaseModel):
    font_style: Optional[str] = None  # "serif", "sans-serif", "bold", "italic"
    font_size_category: Optional[str] = None  # "small", "medium", "large"
    font_color_hex: Optional[str] = None  # hex color code
    reasoning: Optional[str] = None

class LLaVaStage1Out(BaseModel):
    # ... 기존 필드들 ...
    font_recommendation: Optional[FontRecommendation] = None
```

#### 3.1.3 DB 저장 구조
`vlm_traces.response` JSONB에 폰트 추천 정보 추가:
```json
{
  "is_valid": true,
  "relevance_score": 0.9,
  "analysis": "...",
  "font_recommendation": {
    "font_style": "sans-serif",
    "font_size_category": "medium",
    "font_color_hex": "FFFFFF",
    "reasoning": "..."
  }
}
```

#### 3.1.4 Overlay API에서 LLaVA 추천 사용
`routers/overlay.py`에서:
1. `job_id`로 `vlm_traces` 테이블 조회 (operation_type='analyze')
2. `response` JSONB에서 `font_recommendation` 추출
3. LLaVA 추천이 있으면 우선 사용, 없으면 기존 로직 사용 (하위 호환성)

**우선순위**:
1. Overlay API 요청 파라미터 (명시적 지정)
2. LLaVA 추천 (DB에서 조회)
3. Planner 제안 (`planner_proposals.color`, `planner_proposals.size`)
4. 기본값 (현재 로직)

### 3.2 방안 B: 별도 LLaVA 폰트 추천 API 엔드포인트

#### 3.2.1 새로운 API 엔드포인트
- `/api/yh/llava/font-recommendation`
- LLaVA Stage 1과 독립적으로 실행 가능
- 폰트 추천만 수행

**장점**: 
- LLaVA Stage 1과 분리되어 독립적으로 실행 가능
- 폰트 추천만 필요한 경우 효율적

**단점**:
- 추가 API 호출 필요
- 데이터 흐름이 복잡해짐

### 3.3 방안 C: Planner와 통합

현재 Planner API가 이미 `color`와 `size`를 제안하고 있으므로, LLaVA 추천을 Planner에 통합하는 방안도 고려할 수 있습니다.

**장점**:
- 기존 구조 활용
- Planner가 이미 레이아웃과 함께 색상/크기를 제안

**단점**:
- LLaVA의 이미지 분석 기반 추천과 Planner의 규칙 기반 제안이 혼재
- 폰트 스타일 추천이 어려움

## 4. 권장 구현 방안: 방안 A (LLaVA Stage 1 확장)

### 4.1 구현 단계

#### Step 1: LLaVA 서비스 확장
1. `services/llava_service.py`의 `validate_image_and_text()` 함수 수정
2. 폰트 추천을 위한 추가 프롬프트 생성 및 LLaVA 호출
3. 응답 파싱하여 폰트 추천 정보 추출

#### Step 2: 모델 확장
1. `models.py`에 `FontRecommendation` 모델 추가
2. `LLaVaStage1Out`에 `font_recommendation` 필드 추가

#### Step 3: 라우터 수정
1. `routers/llava_stage1.py`에서 폰트 추천 결과를 `vlm_traces.response`에 저장
2. 응답에 폰트 추천 정보 포함

#### Step 4: Overlay API 수정
1. `routers/overlay.py`에서 `job_id`로 `vlm_traces` 조회
2. `response`에서 `font_recommendation` 추출
3. 폰트 경로 선택 로직에 `font_style` 반영
4. `text_size`에 `font_size_category` 반영 (small=24, medium=32, large=48 등)
5. `text_color`에 `font_color_hex` 사용

### 4.2 폰트 매핑 로직

**폰트 스타일 → 폰트 경로 매핑**:
```python
FONT_STYLE_MAP = {
    "serif": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"],
    "sans-serif": [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ],
    "bold": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/local/lib/python3.11/site-packages/cv2/qt/fonts/DejaVuSans-Bold.ttf"
    ],
    "italic": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"]
}
```

**폰트 크기 카테고리 → 크기 범위 매핑**:
```python
FONT_SIZE_MAP = {
    "small": (12, 24),
    "medium": (24, 48),
    "large": (48, 96)
}
```

### 4.3 데이터 흐름

```
1. LLaVA Stage 1 API 호출
   ↓
2. 이미지 + 광고문구 분석
   ↓
3. 폰트 추천 생성 (LLaVA)
   ↓
4. vlm_traces.response에 저장
   ↓
5. Overlay API 호출 시
   ↓
6. vlm_traces에서 폰트 추천 조회
   ↓
7. 폰트 추천 적용 (우선순위: 요청 파라미터 > LLaVA 추천 > Planner 제안 > 기본값)
```

## 5. 구현 시 고려사항

### 5.1 하위 호환성
- LLaVA 추천이 없어도 기존 로직으로 동작해야 함
- `font_recommendation`은 Optional 필드로 처리

### 5.2 에러 처리
- LLaVA가 폰트 추천을 생성하지 못한 경우 기본값 사용
- 폰트 경로가 존재하지 않는 경우 fallback 로직

### 5.3 성능
- LLaVA Stage 1에 폰트 추천 추가 시 응답 시간 증가 가능
- 필요시 별도 비동기 처리 고려

### 5.4 테스트
- LLaVA 폰트 추천 응답 파싱 테스트
- Overlay API에서 LLaVA 추천 사용 테스트
- 하위 호환성 테스트 (LLaVA 추천 없는 경우)

## 6. 예상 변경 파일

1. **`services/llava_service.py`**
   - `validate_image_and_text()` 함수에 폰트 추천 로직 추가

2. **`models.py`**
   - `FontRecommendation` 모델 추가
   - `LLaVaStage1Out` 모델에 `font_recommendation` 필드 추가

3. **`routers/llava_stage1.py`**
   - 폰트 추천 결과를 `vlm_traces.response`에 저장
   - 응답에 폰트 추천 정보 포함

4. **`routers/overlay.py`**
   - `vlm_traces` 조회 로직 추가
   - 폰트 추천 적용 로직 추가
   - 폰트 스타일 매핑 로직 추가

5. **테스트 파일**
   - `test/test_llava_stage1_db.py`: 폰트 추천 검증 추가
   - `test/test_pipeline_full.py`: 전체 파이프라인에서 폰트 추천 확인

## 7. 다음 단계

1. LLaVA 프롬프트 설계 및 테스트
2. 폰트 추천 응답 파싱 로직 구현
3. Overlay API 통합 구현
4. 테스트 및 검증


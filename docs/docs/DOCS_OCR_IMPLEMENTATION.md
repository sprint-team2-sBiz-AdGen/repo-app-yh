# OCR 구현 문서

## 📋 목차

1. [개요](#개요)
2. [아키텍처](#아키텍처)
3. [설정](#설정)
4. [모델 관리](#모델-관리)
5. [API 사용법](#api-사용법)
6. [서비스 함수](#서비스-함수)
7. [평가 메트릭](#평가-메트릭)
8. [테스트](#테스트)
9. [문제 해결](#문제-해결)
10. [참고 자료](#참고-자료)

---

## 개요

### 목적

OCR (Optical Character Recognition) 기능은 렌더링된 광고 이미지에서 텍스트를 추출하고, 원본 텍스트와 비교하여 인식 정확도를 평가합니다.

### 주요 기능

- **텍스트 추출**: EasyOCR을 사용하여 이미지에서 텍스트 추출
- **정확도 평가**: 원본 텍스트와 인식된 텍스트 비교
- **메트릭 계산**: 신뢰도, 정확도, 문자/단어 일치율 등 다양한 메트릭 제공
- **데이터 저장**: 평가 결과를 `evaluations` 테이블에 저장

### 기술 스택

- **OCR 엔진**: EasyOCR (한글, 영어 지원)
- **프레임워크**: FastAPI
- **이미지 처리**: PIL (Pillow)
- **데이터베이스**: PostgreSQL (evaluations 테이블)

---

## 아키텍처

### 파일 구조

```
feedlyai-work/
├── services/
│   └── ocr_service.py          # OCR 서비스 로직
├── routers/
│   └── ocr_eval.py             # OCR 평가 API 라우터
├── models.py                   # Pydantic 모델 (OCREvalIn/Out)
├── config.py                   # 설정 (EASYOCR_MODEL_DIR)
└── model/
    └── easyocr/                # EasyOCR 모델 저장 디렉토리
        ├── craft_mlt_25k.pth   # 텍스트 감지 모델 (80MB)
        └── korean_g2.pth       # 한글 인식 모델 (16MB)
```

### 데이터 흐름

```
1. API 요청 (OCREvalIn)
   ↓
2. overlay_layouts에서 원본 텍스트 및 렌더 이미지 URL 조회
   ↓
3. 이미지 로드 및 텍스트 영역 좌표 계산
   ↓
4. EasyOCR로 텍스트 추출
   ↓
5. 원본 텍스트와 비교하여 정확도 계산
   ↓
6. evaluations 테이블에 결과 저장
   ↓
7. API 응답 (OCREvalOut)
```

---

## 설정

### config.py

```python
# EasyOCR 모델 저장 디렉토리 (MODEL_DIR 내부)
EASYOCR_MODEL_DIR = os.path.join(MODEL_DIR, "easyocr")
os.makedirs(EASYOCR_MODEL_DIR, exist_ok=True)
```

### .env

```env
# EasyOCR
## EasyOCR model storage directory (프로젝트 model 폴더 내부)
EASYOCR_MODEL_DIR=./model/easyocr
```

### 환경 변수

- `EASYOCR_MODEL_DIR`: EasyOCR 모델 저장 경로 (기본값: `./model/easyocr`)

---

## 모델 관리

### 모델 다운로드

EasyOCR 모델은 첫 실행 시 자동으로 다운로드됩니다. 수동 다운로드가 필요한 경우:

```bash
docker exec feedlyai-work-yh python3 << 'EOF'
import sys
sys.path.insert(0, '/app')
import os
import easyocr
from config import EASYOCR_MODEL_DIR

# 디렉토리 생성
os.makedirs(EASYOCR_MODEL_DIR, exist_ok=True)

# 모델 다운로드 (한글, 영어)
reader = easyocr.Reader(['ko', 'en'], gpu=True, model_storage_directory=EASYOCR_MODEL_DIR)
print("✓ 모델 다운로드 완료!")
EOF
```

### 모델 파일

| 파일명 | 크기 | 설명 |
|--------|------|------|
| `craft_mlt_25k.pth` | 80MB | 텍스트 감지 모델 (CRAFT) |
| `korean_g2.pth` | 16MB | 한글 인식 모델 |

### 모델 저장 위치

- **컨테이너 내부**: `/app/model/easyocr/`
- **호스트**: `/home/leeyoungho/feedlyai-work/model/easyocr/`

### 모델 경로 변경

모델 경로를 변경하려면:

1. `config.py`에서 `EASYOCR_MODEL_DIR` 수정
2. `.env` 파일에 `EASYOCR_MODEL_DIR` 환경 변수 추가
3. Docker 컨테이너 재시작

---

## API 사용법

### 엔드포인트

```
POST /api/yh/ocr/evaluate
```

### 요청 (OCREvalIn)

```json
{
  "job_id": "9e39ceb8-1209-423f-a700-210f61a3e0d9",
  "tenant_id": "pipeline_test_tenant",
  "overlay_id": "f6325064-9d4b-4f3b-bd57-3b2472174729"
}
```

**필수 필드:**
- `job_id`: Job UUID
- `tenant_id`: 테넌트 ID
- `overlay_id`: Overlay Layout UUID

### 응답 (OCREvalOut)

```json
{
  "job_id": "9e39ceb8-1209-423f-a700-210f61a3e0d9",
  "evaluation_id": "32aa88db-8dd8-4308-a383-99f00321cb08",
  "overlay_id": "f6325064-9d4b-4f3b-bd57-3b2472174729",
  "ocr_confidence": 0.95,
  "ocr_accuracy": 0.92,
  "character_match_rate": 0.94,
  "recognized_text": "매콤라면 떡볶이",
  "original_text": "매콤라면 떡볶이"
}
```

### cURL 예제

```bash
curl -X POST "http://localhost:8011/api/yh/ocr/evaluate" \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "9e39ceb8-1209-423f-a700-210f61a3e0d9",
    "tenant_id": "pipeline_test_tenant",
    "overlay_id": "f6325064-9d4b-4f3b-bd57-3b2472174729"
  }'
```

### Python 예제

```python
import requests

url = "http://localhost:8011/api/yh/ocr/evaluate"
data = {
    "job_id": "9e39ceb8-1209-423f-a700-210f61a3e0d9",
    "tenant_id": "pipeline_test_tenant",
    "overlay_id": "f6325064-9d4b-4f3b-bd57-3b2472174729"
}

response = requests.post(url, json=data)
result = response.json()

print(f"OCR 정확도: {result['ocr_accuracy']:.2%}")
print(f"인식된 텍스트: {result['recognized_text']}")
```

---

## 서비스 함수

### `get_ocr_reader()`

EasyOCR Reader 싱글톤 인스턴스를 반환합니다.

```python
def get_ocr_reader():
    """EasyOCR Reader 싱글톤"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        from config import EASYOCR_MODEL_DIR
        
        _ocr_reader = easyocr.Reader(
            ['ko', 'en'], 
            gpu=True, 
            model_storage_directory=EASYOCR_MODEL_DIR
        )
    return _ocr_reader
```

**특징:**
- 싱글톤 패턴으로 모델을 한 번만 로드
- GPU 사용 (가능한 경우)
- 한글(ko)과 영어(en) 지원

### `extract_text_from_image()`

이미지에서 텍스트를 추출합니다.

```python
def extract_text_from_image(
    image: Image.Image,
    text_region: Optional[Tuple[int, int, int, int]] = None
) -> Dict[str, Any]:
```

**파라미터:**
- `image`: PIL Image 객체
- `text_region`: 텍스트 영역 `(x, y, width, height)` - None이면 전체 이미지

**반환값:**
```python
{
    "recognized_text": str,      # 인식된 전체 텍스트
    "confidence": float,          # 평균 신뢰도 (0.0-1.0)
    "details": List[Dict]         # 각 텍스트 박스별 정보
}
```

**예제:**
```python
from PIL import Image
from services.ocr_service import extract_text_from_image

image = Image.open("ad_image.jpg")
result = extract_text_from_image(image, text_region=(100, 100, 200, 50))

print(result["recognized_text"])  # "매콤라면 떡볶이"
print(result["confidence"])        # 0.95
```

### `calculate_ocr_accuracy()`

원본 텍스트와 인식된 텍스트를 비교하여 정확도를 계산합니다.

```python
def calculate_ocr_accuracy(
    original_text: str,
    recognized_text: str
) -> Dict[str, Any]:
```

**반환값:**
```python
{
    "accuracy": float,                # 전체 정확도 (0.0-1.0)
    "character_match_rate": float,    # 문자 일치율
    "word_match_rate": float,          # 단어 일치율
    "edit_distance": int,              # 편집 거리 (Levenshtein)
    "similarity": float                # 유사도 (SequenceMatcher)
}
```

**계산 방법:**
- **문자 일치율**: `difflib.SequenceMatcher`를 사용한 문자 단위 유사도
- **단어 일치율**: 정확히 일치하는 단어 수 / 전체 단어 수
- **전체 정확도**: (문자 일치율 + 단어 일치율) / 2
- **편집 거리**: Levenshtein 거리 알고리즘
- **유사도**: `difflib.SequenceMatcher`를 사용한 전체 텍스트 유사도

---

## 평가 메트릭

### 메트릭 설명

| 메트릭 | 타입 | 범위 | 설명 |
|--------|------|------|------|
| `ocr_confidence` | float | 0.0-1.0 | EasyOCR이 제공하는 평균 신뢰도 |
| `ocr_accuracy` | float | 0.0-1.0 | 전체 정확도 (문자/단어 일치율 평균) |
| `character_match_rate` | float | 0.0-1.0 | 문자 단위 일치율 |
| `word_match_rate` | float | 0.0-1.0 | 단어 단위 일치율 |
| `edit_distance` | int | 0+ | 편집 거리 (Levenshtein) |
| `similarity` | float | 0.0-1.0 | 전체 텍스트 유사도 |
| `latency_ms` | float | 0+ | OCR 실행 시간 (밀리초) |

### 메트릭 해석

- **ocr_confidence ≥ 0.9**: 매우 높은 신뢰도
- **ocr_accuracy ≥ 0.9**: 매우 높은 정확도
- **ocr_accuracy ≥ 0.7**: 양호한 정확도
- **ocr_accuracy < 0.5**: 낮은 정확도 (폰트, 대비, 해상도 문제 가능)

### 데이터베이스 저장

평가 결과는 `evaluations` 테이블에 저장됩니다:

```sql
INSERT INTO evaluations (
    evaluation_id, job_id, overlay_id, evaluation_type,
    metrics, created_at, updated_at
) VALUES (
    :evaluation_id, :job_id, :overlay_id, 'ocr',
    CAST(:metrics AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
)
```

**metrics JSON 구조:**
```json
{
  "ocr_confidence": 0.95,
  "ocr_accuracy": 0.92,
  "character_match_rate": 0.94,
  "word_match_rate": 0.90,
  "recognized_text": "매콤라면 떡볶이",
  "original_text": "매콤라면 떡볶이",
  "edit_distance": 0,
  "similarity": 1.0,
  "latency_ms": 1234.56
}
```

---

## 테스트

### 단위 테스트

```python
# test/test_ocr_service.py
from services.ocr_service import extract_text_from_image, calculate_ocr_accuracy
from PIL import Image

# 텍스트 추출 테스트
image = Image.open("test_image.jpg")
result = extract_text_from_image(image)
assert result["recognized_text"] != ""

# 정확도 계산 테스트
accuracy = calculate_ocr_accuracy("원본 텍스트", "인식된 텍스트")
assert 0.0 <= accuracy["accuracy"] <= 1.0
```

### API 테스트

```bash
# test/test_quantitative_eval.py 사용
python3 test/test_quantitative_eval.py --eval-type ocr
```

### 수동 테스트

```python
import requests

url = "http://localhost:8011/api/yh/ocr/evaluate"
data = {
    "job_id": "YOUR_JOB_ID",
    "tenant_id": "YOUR_TENANT_ID",
    "overlay_id": "YOUR_OVERLAY_ID"
}

response = requests.post(url, json=data, timeout=120)
print(response.json())
```

---

## 문제 해결

### 1. 타임아웃 오류

**증상:**
```
ReadTimeout: HTTPConnectionPool(host='localhost', port=8011): Read timed out
```

**원인:**
- EasyOCR 모델이 처음 로드될 때 시간이 오래 걸림 (수 분 소요)
- GPU 메모리 부족

**해결 방법:**
1. 타임아웃 시간 증가 (기본값: 120초)
2. 모델 사전 다운로드 (컨테이너 빌드 시)
3. GPU 메모리 확인

```python
# 타임아웃 증가
response = requests.post(url, json=data, timeout=300)  # 5분
```

### 2. 모델 로딩 실패

**증상:**
```
EasyOCR Reader 초기화 실패: ...
```

**원인:**
- 모델 파일이 없음
- 모델 경로 설정 오류
- 권한 문제

**해결 방법:**
1. 모델 다운로드 확인:
```bash
ls -lh model/easyocr/
```

2. 모델 경로 확인:
```python
from config import EASYOCR_MODEL_DIR
print(EASYOCR_MODEL_DIR)  # /app/model/easyocr
```

3. 모델 재다운로드:
```bash
docker exec feedlyai-work-yh python3 << 'EOF'
import easyocr
from config import EASYOCR_MODEL_DIR
reader = easyocr.Reader(['ko', 'en'], gpu=True, model_storage_directory=EASYOCR_MODEL_DIR)
EOF
```

### 3. 낮은 정확도

**증상:**
- `ocr_accuracy < 0.5`
- 텍스트가 잘못 인식됨

**원인:**
- 폰트 문제 (특수 폰트, 손글씨)
- 낮은 해상도
- 배경과 텍스트 대비 부족
- 텍스트 영역 좌표 오류

**해결 방법:**
1. 이미지 해상도 확인
2. 텍스트 영역 좌표 확인 (`overlay.x_ratio`, `overlay.y_ratio`)
3. 폰트 변경 (더 읽기 쉬운 폰트 사용)
4. 대비 개선 (텍스트 색상과 배경 색상 차이 증가)

### 4. GPU 메모리 부족

**증상:**
```
CUDA out of memory
```

**해결 방법:**
1. CPU 모드로 전환:
```python
_ocr_reader = easyocr.Reader(['ko', 'en'], gpu=False, model_storage_directory=EASYOCR_MODEL_DIR)
```

2. 다른 프로세스의 GPU 사용량 확인:
```bash
nvidia-smi
```

### 5. 한글 인식 실패

**증상:**
- 한글이 깨지거나 인식되지 않음

**원인:**
- 한글 모델이 다운로드되지 않음
- 언어 설정 오류

**해결 방법:**
1. 한글 모델 확인:
```bash
ls -lh model/easyocr/korean_g2.pth
```

2. 언어 설정 확인:
```python
reader = easyocr.Reader(['ko', 'en'], ...)  # 'ko' 포함 확인
```

---

## 참고 자료

### 공식 문서

- [EasyOCR GitHub](https://github.com/JaidedAI/EasyOCR)
- [EasyOCR Documentation](https://www.jaided.ai/easyocr/)

### 관련 파일

- `services/ocr_service.py`: OCR 서비스 로직
- `routers/ocr_eval.py`: OCR 평가 API
- `models.py`: Pydantic 모델 정의
- `config.py`: 설정 관리
- `test/test_quantitative_eval.py`: 테스트 코드

### 관련 API

- `/api/yh/readability/evaluate`: 가독성 평가
- `/api/yh/iou/evaluate`: IoU 평가
- `/api/yh/evaluations/full`: 통합 평가

### 데이터베이스

- `evaluations` 테이블: 평가 결과 저장
- `overlay_layouts` 테이블: 원본 텍스트 및 렌더 이미지 URL

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|----------|
| 2025-11-26 | 1.0.0 | 초기 구현 |
| 2025-11-26 | 1.0.1 | 모델 경로 설정 추가 |
| 2025-11-26 | 1.0.2 | 문서 작성 완료 |

---

## 문의

문제가 발생하거나 개선 사항이 있으면 개발팀에 문의하세요.

**작성자**: LEEYH205  
**최종 업데이트**: 2025-11-26


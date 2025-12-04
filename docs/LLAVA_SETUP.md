# LLaVa 모델 설정 가이드

## 개요

LLaVa (Large Language and Vision Assistant)는 이미지와 텍스트를 함께 처리할 수 있는 멀티모달 AI 모델입니다.

## 모델 선택

### 1. 기본 모델 (권장)
- **모델명**: `llava-hf/llava-1.5-7b-hf`
- **크기**: 7B 파라미터
- **메모리**: 약 14GB (FP16)
- **속도**: 중간
- **정확도**: 좋음

### 2. 더 큰 모델 (더 정확하지만 느림)
- **모델명**: `llava-hf/llava-1.5-13b-hf`
- **크기**: 13B 파라미터
- **메모리**: 약 26GB (FP16)
- **속도**: 느림
- **정확도**: 매우 좋음

### 3. 한국어 지원이 필요한 경우
- **KoLLaVA**: 한국어에 최적화된 LLaVa 모델
- GitHub: https://github.com/tabtoyou/KoLLaVA

## 설치 방법

### 1. 필수 패키지 설치

```bash
pip install transformers>=4.37.0
pip install torch>=2.0.0
pip install accelerate>=0.25.0
pip install bitsandbytes>=0.41.0  # 8-bit 양자화 (선택사항)
```

또는 requirements.txt 사용:
```bash
pip install -r requirements.txt
```

### 2. GPU 설정 (권장)

LLaVa 모델은 GPU에서 실행하는 것이 권장됩니다:

```bash
# CUDA 설치 확인
nvidia-smi

# PyTorch CUDA 버전 확인
python -c "import torch; print(torch.cuda.is_available())"
```

### 3. 모델 다운로드

모델은 첫 실행 시 자동으로 Hugging Face에서 다운로드됩니다.

수동 다운로드:
```python
from transformers import LlavaProcessor, LlavaForConditionalGeneration

processor = LlavaProcessor.from_pretrained("llava-hf/llava-1.5-7b-hf")
model = LlavaForConditionalGeneration.from_pretrained("llava-hf/llava-1.5-7b-hf")
```

## 환경 변수 설정

`.env` 파일 또는 환경 변수로 설정:

```bash
# 사용할 모델 선택
LLAVA_MODEL_NAME=llava-hf/llava-1.5-7b-hf

# 디바이스 선택 (cuda 또는 cpu)
DEVICE=cuda  # GPU 사용 시
# DEVICE=cpu  # CPU만 사용 시 (매우 느림)
```

## 메모리 최적화

### 8-bit 양자화 사용 (메모리 절약)

`services/llava_service.py`에서 모델 로드 부분 수정:

```python
from transformers import BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_8bit=True,
    bnb_8bit_compute_dtype=torch.float16
)

_model = LlavaForConditionalGeneration.from_pretrained(
    LLAVA_MODEL_NAME,
    quantization_config=quantization_config,
    device_map="auto"
)
```

### CPU 사용 시 주의사항

- CPU에서는 매우 느립니다 (추론에 수십 초 소요)
- 프로덕션 환경에서는 GPU 사용을 강력히 권장합니다

## 사용 예제

### Stage 1 Validation

```python
from services.llava_service import validate_image_and_text
from PIL import Image

image = Image.open("path/to/image.jpg")
result = validate_image_and_text(
    image=image,
    ad_copy_text="광고 문구 텍스트",
    validation_prompt="이미지와 광고 문구가 적합한지 검증해주세요."
)

print(result)
```

### Stage 2 Judge

```python
from services.llava_service import judge_final_ad
from PIL import Image

image = Image.open("path/to/final_ad.jpg")
result = judge_final_ad(image=image)

print(result)
```

## API 엔드포인트

### Stage 1 Validation
```
POST /api/yh/llava/stage1/validate
```

### Stage 2 Judge
```
POST /api/yh/llava/stage2/judge
```

## 문제 해결

### 1. CUDA out of memory
- 더 작은 모델 사용 (`llava-1.5-7b-hf`)
- 8-bit 양자화 사용
- 배치 크기 줄이기

### 2. 모델 다운로드 실패
- Hugging Face 토큰 설정 필요할 수 있음
- 네트워크 연결 확인

### 3. 느린 추론 속도
- GPU 사용 확인
- 모델 크기 줄이기
- 프롬프트 길이 줄이기

## 참고 자료

- LLaVa 공식 GitHub: https://github.com/haotian-liu/LLaVA
- Hugging Face 모델 허브: https://huggingface.co/llava-hf
- KoLLaVA (한국어): https://github.com/tabtoyou/KoLLaVA


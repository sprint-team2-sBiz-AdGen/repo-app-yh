# USE_QUANTIZATION 설정 가이드

## 개요
`USE_QUANTIZATION` 환경변수로 8-bit 양자화 사용 여부를 제어할 수 있습니다.

## 설정 방법

### 1. 환경변수로 직접 설정

#### 양자화 사용 (기본값)
```bash
export USE_QUANTIZATION=true
python3 test/compare_ad_copy.py
```

#### 양자화 비활성화
```bash
export USE_QUANTIZATION=false
python3 test/compare_ad_copy.py
```

### 2. .env 파일 사용 (권장)

프로젝트 루트에 `.env` 파일을 생성하고:

```bash
# .env 파일
USE_QUANTIZATION=true   # 양자화 사용
# 또는
USE_QUANTIZATION=false  # 양자화 비활성화
```

### 3. Docker Compose에서 설정

`docker-compose.yml`의 `environment` 섹션에 추가:

```yaml
services:
  app-yh:
    environment:
      - USE_QUANTIZATION=true   # 또는 false
```

### 4. 실행 시 직접 지정

```bash
USE_QUANTIZATION=false python3 test/compare_ad_copy.py
```

## 설정 값

다음 값들은 모두 양자화를 **사용**합니다:
- `true`
- `1`
- `yes`
- `on`

그 외의 값은 양자화를 **비활성화**합니다:
- `false`
- `0`
- `no`
- `off`
- 빈 문자열

## 기본값

기본값은 `true` (양자화 사용)입니다.

## GPU 메모리 사용량 비교

양자화 사용 여부에 따른 GPU 메모리 사용량을 확인하려면:

```bash
# 양자화 사용 (메모리 절약)
USE_QUANTIZATION=true python3 test/compare_ad_copy.py

# 양자화 비활성화 (더 많은 메모리 사용)
USE_QUANTIZATION=false python3 test/compare_ad_copy.py
```

모델 로드 시 GPU 메모리 사용량이 출력됩니다:
```
📊 GPU Memory Usage:
   - Allocated: X.XX GB
   - Peak (during load): X.XX GB
   - Total GPU: X.XX GB
   - Usage: XX.X%
```

## 디버그 모드

추론 중 GPU 메모리 사용량을 확인하려면:

```bash
DEBUG_GPU_MEMORY=true USE_QUANTIZATION=false python3 test/compare_ad_copy.py
```

## 예상 메모리 사용량

- **8-bit 양자화 사용**: 약 7-8 GB
- **FP16 (양자화 비활성화)**: 약 14-15 GB

*실제 사용량은 GPU와 모델에 따라 다를 수 있습니다.*


# 테스트 실행 가이드

이 문서는 `test/` 폴더에 있는 모든 테스트 파일들의 실행 방법을 정리한 가이드입니다.

## 목차

1. [테스트 파일 목록](#테스트-파일-목록)
2. [공통 사전 준비](#공통-사전-준비)
3. [개별 테스트 실행 방법](#개별-테스트-실행-방법)
4. [빠른 참조](#빠른-참조)

---

## 테스트 파일 목록

| 파일명 | 설명 | 옵션 |
|--------|------|------|
| `test_planner.py` | Planner 위치 제안 테스트 | `--test` |
| `test_yolo.py` | YOLO 금지 영역 감지 테스트 | `--mode` |
| `test_asset_db.py` | Asset 저장 및 DB 작업 테스트 | `--mode` |
| `test_llava_stage1.py` | LLaVa Stage 1 검증 테스트 | 없음 |
| `test_overlay.py` | 텍스트 오버레이 삽입 테스트 | `--test` |
| `compare_ad_copy.py` | 광고 문구 비교 테스트 | 없음 |

---

## 공통 사전 준비

### 1. 환경 변수 설정

```bash
# Assets 디렉토리 설정 (필수)
export ASSETS_DIR=/opt/feedlyai/assets

# DB 연결 정보 (선택사항 - DB 테스트를 하려면 설정)
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=feedlyai
export DB_USER=feedlyai
export DB_PASSWORD=your_password
```

### 2. 프로젝트 루트에서 실행

모든 테스트는 프로젝트 루트 디렉토리에서 실행합니다:

```bash
cd /home/leeyoungho/feedlyai-work
```

---

## 개별 테스트 실행 방법

### 1. test_planner.py - Planner 위치 제안 테스트

Planner가 텍스트 오버레이 위치를 제안하는 기능을 테스트합니다.

#### 기본 실행 (모든 테스트)

```bash
python3 test/test_planner.py
```

또는

```bash
python3 test/test_planner.py --test all
```

#### 개별 테스트 모드

```bash
# 기본 테스트 (금지 영역 없음)
python3 test/test_planner.py --test basic

# YOLO 감지 결과 포함 테스트 (기존 YOLO 결과 파일 사용)
python3 test/test_planner.py --test detections

# Planner 서비스 직접 테스트
python3 test/test_planner.py --test service
```

#### 테스트 결과

- `test/output/planner_basic_proposals.png` - 기본 테스트 시각화
- `test/output/planner_with_detections.png` - YOLO 감지 포함 테스트 시각화
- `test/output/planner_service_direct.png` - 서비스 직접 테스트 시각화
- `test/output/planner_result.json` - 결과 JSON 파일

---

### 2. test_yolo.py - YOLO 금지 영역 감지 테스트

YOLO 모델을 사용하여 이미지에서 금지 영역을 감지하는 기능을 테스트합니다.

#### 기본 실행 (단일 모델)

```bash
python3 test/test_yolo.py
```

또는

```bash
python3 test/test_yolo.py --mode single
```

#### 다중 모델 테스트

```bash
python3 test/test_yolo.py --mode multiple
```

#### 테스트 결과

- `test/output/yolo_detection_result.png` - 감지 결과 시각화
- `test/output/forbidden_mask.png` - 금지 영역 마스크
- `test/output/forbidden_area_overlay.png` - 금지 영역 오버레이
- `test/output/detections.json` - 감지 결과 JSON

#### 주의사항

- YOLO 모델이 `model/yolov8x-seg.pt`에 있어야 합니다.
- 모델이 없으면 `python3 download_yolo_model.py`를 실행하여 다운로드하세요.

---

### 3. test_asset_db.py - Asset 저장 및 DB 작업 테스트

Asset 파일 저장 및 데이터베이스 insert/delete 작업을 테스트합니다.

#### 기본 실행 (단일 Asset)

```bash
python3 test/test_asset_db.py
```

또는

```bash
python3 test/test_asset_db.py --mode single
```

#### 여러 Asset 일괄 테스트

```bash
python3 test/test_asset_db.py --mode multiple
```

#### 테스트 내용

1. **Asset 저장 테스트**
   - 테스트 이미지 생성
   - Asset 폴더에 이미지 저장
   - 파일 존재 확인

2. **DB Insert 테스트** (선택사항)
   - DB 연결 확인
   - `test_assets` 테이블 자동 생성
   - 레코드 Insert
   - 레코드 조회 확인

3. **DB Delete 테스트** (선택사항)
   - 레코드 Delete
   - 삭제 확인

#### 주의사항

- DB 연결이 없어도 Asset 저장 테스트는 진행됩니다.
- DB 테스트를 하려면 PostgreSQL이 설치되어 있어야 합니다.
- `test_assets` 테이블이 자동으로 생성됩니다.

---

### 4. test_llava_stage1.py - LLaVa Stage 1 검증 테스트

LLaVa 모델을 사용하여 이미지와 광고 문구의 적합성을 검증하는 기능을 테스트합니다.

#### 실행

```bash
python3 test/test_llava_stage1.py
```

#### 테스트 내용

- 이미지 로드
- LLaVa 모델 로드 및 검증 실행
- 검증 결과 출력 (적합성, 이미지 품질, 관련성 점수 등)

#### 주의사항

- LLaVa 모델이 처음 로드될 때 시간이 걸릴 수 있습니다.
- GPU가 있으면 자동으로 사용됩니다.

---

### 5. test_overlay.py - 텍스트 오버레이 삽입 테스트

Planner에서 제안한 위치에 광고 문구를 오버레이하는 기능을 테스트합니다.

#### 기본 실행 (단일 제안)

```bash
python3 test/test_overlay.py
```

또는

```bash
python3 test/test_overlay.py --test single
```

#### 모든 제안 각각 테스트

각 제안마다 별도의 이미지를 생성합니다:

```bash
python3 test/test_overlay.py --test all
```

#### 모든 제안 통합 테스트

하나의 이미지에 모든 제안을 표시합니다:

```bash
python3 test/test_overlay.py --test combined
```

#### 테스트 결과

- `test/output/overlay_single.png` - 첫 번째 제안에 텍스트 오버레이
- `test/output/overlay_XX_*.png` - 각 제안별 오버레이 이미지 (all 모드)
- `test/output/overlay_combined.png` - 모든 제안 통합 오버레이 (combined 모드)

#### 주의사항

- `planner_result.json` 파일이 있어야 합니다. 먼저 `test_planner.py`를 실행하세요.
- 실제로는 DB에서 planner 결과와 광고 문구를 가져옵니다.

---

### 6. compare_ad_copy.py - 광고 문구 비교 테스트

두 개의 광고 문구를 비교하여 LLaVa가 올바르게 구분하는지 테스트합니다.

#### 실행

```bash
python3 test/compare_ad_copy.py
```

#### 테스트 내용

- 좋은 광고 문구와 나쁜 광고 문구 비교
- LLaVa의 관련성 점수 비교
- 구분 정확도 확인

---

## 빠른 참조

### 모든 테스트 한 번에 실행

```bash
# Planner 테스트 (모든 모드)
python3 test/test_planner.py --test all

# YOLO 테스트 (단일 모델)
python3 test/test_yolo.py --mode single

# Asset/DB 테스트 (단일)
python3 test/test_asset_db.py --mode single

# LLaVa 테스트
python3 test/test_llava_stage1.py

# Overlay 테스트 (단일)
python3 test/test_overlay.py --test single

# 광고 문구 비교 테스트
python3 test/compare_ad_copy.py
```

### 테스트 결과 확인

모든 테스트 결과는 `test/output/` 폴더에 저장됩니다:

```bash
ls -lh test/output/
```

### 문제 해결

#### 1. "ModuleNotFoundError" 오류

필수 패키지가 설치되지 않았습니다:

```bash
pip install -r requirements.txt
```

#### 2. "FileNotFoundError" 오류 (이미지)

이미지 경로를 확인하세요:

```bash
# 기본 이미지 경로
/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png
```

#### 3. "DB 연결 실패" 경고

이 경고는 정상입니다. DB 연결이 없어도 Asset 저장 테스트는 진행됩니다.

DB 테스트를 하려면:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=feedlyai
export DB_USER=feedlyai
export DB_PASSWORD=your_password
```

#### 4. "YOLO 모델을 찾을 수 없습니다" 오류

YOLO 모델을 다운로드하세요:

```bash
python3 download_yolo_model.py
```

#### 5. "CUDA out of memory" 오류

GPU 메모리가 부족합니다. CPU 모드로 실행하거나 배치 크기를 줄이세요:

```bash
export DEVICE_TYPE=cpu
```

---

## 테스트 실행 순서 권장사항

1. **YOLO 테스트** → 금지 영역 감지 확인
2. **Planner 테스트** → YOLO 결과를 사용한 위치 제안 확인
3. **Overlay 테스트** → Planner 제안 위치에 텍스트 오버레이 확인
4. **Asset/DB 테스트** → 파일 저장 및 DB 작업 확인
5. **LLaVa 테스트** → 이미지-텍스트 검증 확인

---

## 추가 정보

- 각 테스트 파일의 상세한 설명은 파일 내부의 docstring을 참고하세요.
- 테스트 결과 파일은 `test/output/` 폴더에 저장됩니다.
- 문제가 발생하면 각 테스트 파일의 에러 메시지를 확인하세요.


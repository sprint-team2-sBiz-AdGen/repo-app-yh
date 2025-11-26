# Pipeline Test

이 폴더는 전체 Pipeline 테스트를 위한 테스트 데이터를 포함합니다.

## 폴더 구조

```
pipeline_test/
├── README.md                    # 이 파일
├── pipline_test_image1.png      # 테스트용 이미지 파일
└── pipline_test_txt1.txt        # 테스트용 광고 문구 텍스트 파일
```

## 파일 설명

### `pipline_test_image1.png`
- **용도**: Pipeline 테스트에 사용되는 이미지 파일
- **형식**: PNG 이미지
- **사용 위치**: 
  - `image_assets` 테이블에 저장
  - LLaVA Stage 1, YOLO, Planner, Overlay 단계에서 사용

### `pipline_test_txt1.txt`
- **용도**: Pipeline 테스트에 사용되는 광고 문구 텍스트 파일
- **형식**: 텍스트 파일 (UTF-8)
- **내용**: `"Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."`
- **사용 위치**:
  - `job_inputs` 테이블의 `desc_eng` 컬럼에 저장
  - LLaVA Stage 1 검증에 사용
  - Overlay 단계에서 텍스트 오버레이로 적용

## Pipeline 테스트 실행

전체 Pipeline 테스트는 `test/test_pipeline_full.py` 스크립트를 사용합니다.

### 기본 실행

```bash
# 전체 pipeline 테스트 실행
python3 test/test_pipeline_full.py --api-url http://localhost:8011
```

### 옵션

```bash
# 특정 단계 건너뛰기
python3 test/test_pipeline_full.py --skip-llava    # LLaVA Stage 1 건너뛰기
python3 test/test_pipeline_full.py --skip-yolo     # YOLO 건너뛰기
python3 test/test_pipeline_full.py --skip-planner  # Planner 건너뛰기
python3 test/test_pipeline_full.py --skip-overlay  # Overlay 건너뛰기

# 커스텀 경로 사용
python3 test/test_pipeline_full.py \
  --image-path /path/to/custom/image.png \
  --text-path /path/to/custom/text.txt

# 기존 job_id 사용
python3 test/test_pipeline_full.py --job-id <job_id>

# 커스텀 tenant_id 사용
python3 test/test_pipeline_full.py --tenant-id custom_tenant
```

### 전체 옵션 목록

- `--job-id`: 테스트할 job_id (없으면 새로 생성)
- `--tenant-id`: 테스트용 tenant_id (기본값: `pipeline_test_tenant`)
- `--image-path`: 사용할 이미지 경로 (기본값: `pipeline_test/pipline_test_image1.png`)
- `--text-path`: 사용할 텍스트 파일 경로 (기본값: `pipeline_test/pipline_test_txt1.txt`)
- `--api-url`: API 서버 URL (기본값: `http://localhost:8011`)
- `--skip-llava`: LLaVA Stage 1 건너뛰기
- `--skip-yolo`: YOLO 건너뛰기
- `--skip-planner`: Planner 건너뛰기
- `--skip-overlay`: Overlay 건너뛰기

## Pipeline 단계

테스트는 다음 순서로 진행됩니다:

1. **Job 생성 (img_gen 완료 상태)**
   - 이미지 파일을 `image_assets` 테이블에 저장
   - 텍스트 파일을 읽어서 `job_inputs` 테이블에 저장
   - `jobs` 테이블에 `current_step='img_gen'`, `status='done'` 상태로 생성

2. **LLaVA Stage 1** (`/api/yh/llava/stage1/validate`)
   - 이미지와 광고문구의 논리적 일관성 검증
   - `current_step='vlm_analyze'`, `status='running'` → `status='done'`
   - 결과를 `vlm_traces` 테이블에 저장

3. **YOLO** (`/api/yh/yolo/detect`)
   - 금지 영역 감지
   - `current_step='yolo_detect'`, `status='running'` → `status='done'`
   - 결과를 `detections` 및 `yolo_runs` 테이블에 저장

4. **Planner** (`/api/yh/planner`)
   - 텍스트 오버레이 위치 제안
   - `current_step='planner'`, `status='running'` → `status='done'`
   - 결과를 `planner_proposals` 테이블에 저장

5. **Overlay** (`/api/yh/overlay`)
   - 텍스트 오버레이 적용
   - `current_step='overlay'`, `status='running'` → `status='done'`
   - 결과를 `overlay_layouts` 테이블에 저장

## 예상 결과

테스트가 성공적으로 완료되면:

- 각 단계에서 Job 상태가 올바르게 업데이트됨
- 모든 단계의 결과가 DB에 저장됨
- 최종적으로 `current_step='overlay'`, `status='done'` 상태가 됨

## DB 테이블 확인

테스트 후 다음 테이블들을 확인할 수 있습니다:

- `jobs`: Job 상태 및 진행 단계
- `job_inputs`: 입력 이미지 및 광고 문구
- `image_assets`: 저장된 이미지 정보
- `vlm_traces`: LLaVA Stage 1 검증 결과
- `yolo_runs`: YOLO 실행 메타데이터
- `detections`: YOLO 감지 결과
- `planner_proposals`: Planner 제안 결과
- `overlay_layouts`: Overlay 레이아웃 결과

## 문제 해결

### 이미지 파일을 찾을 수 없음
- `--image-path` 옵션으로 올바른 경로를 지정하세요
- 파일이 존재하는지 확인하세요

### 텍스트 파일을 찾을 수 없음
- `--text-path` 옵션으로 올바른 경로를 지정하세요
- 파일이 UTF-8 인코딩인지 확인하세요

### API 서버 연결 실패
- `--api-url` 옵션으로 올바른 API 서버 URL을 지정하세요
- API 서버가 실행 중인지 확인하세요

### DB 연결 실패
- `config.py`의 `DATABASE_URL` 설정을 확인하세요
- PostgreSQL 서버가 실행 중인지 확인하세요

## 참고

- 테스트는 실제 DB에 데이터를 저장합니다
- 테스트 후 필요시 DB를 정리하세요
- 같은 `tenant_id`로 여러 번 실행하면 기존 데이터를 재사용할 수 있습니다



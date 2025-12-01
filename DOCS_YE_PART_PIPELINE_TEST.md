# YE 파트 파이프라인 테스트 가이드

## 📋 개요

이 문서는 YE 파트(이미지 생성) 파이프라인을 테스트하기 위한 Background Job Creator 사용 가이드입니다.

**작성일**: 2025-12-01  
**버전**: 1.2.0  
**작성자**: LEEYH205

---

## 🎯 목적

YE 파트 테스트용 Background Job Creator는:
- **기존 이미지 파일**을 사용하여 Job과 Job Variants를 생성합니다
- `user_img_input (done)` 상태로만 생성합니다
- **⚠️ 중요**: 이 스크립트는 트리거를 발동하지 않습니다. YE 파트가 실제로 `img_gen`을 완료할 때까지 기다립니다.

**⚠️ 중요**: 
- 이 스크립트는 **이미지를 생성하지 않습니다**. 기존 이미지 파일을 사용합니다.
- 이 스크립트는 **트리거를 발동하지 않습니다**. YE 파트가 실제로 `img_gen`을 완료하면 자동으로 YH 파트 파이프라인이 시작됩니다.

---

## 📁 파일 위치

```
scripts/background_ye_pipeline_test.py
```

---

## 🚀 사용 방법

### 기본 사용법

#### 1. 단일 Job 생성 (한 번만 실행)

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py --once
```

**결과**:
- Job 1개 생성
- Variants 3개 생성 (기본값)
- `user_img_input (done)` 상태로 생성
- YE 파트가 실제로 `img_gen`을 완료하면 자동으로 YH 파트 파이프라인 시작

#### 2. 백그라운드 실행 (이전 Job 완료 대기)

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --tenant-id ye_test_tenant \
  --wait-for-completion
```

**동작**:
- 이전 Job이 `iou_eval (done)` 상태가 될 때까지 대기
- 완료되면 새로운 Job 생성
- 계속 반복 (Ctrl+C로 종료)

#### 3. 주기적 생성 (일정 간격으로 생성)

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --tenant-id ye_test_tenant \
  --create-interval 60
```

**동작**:
- 60초마다 새로운 Job 생성
- 이전 Job 완료 여부와 관계없이 생성
- 계속 반복 (Ctrl+C로 종료)

---

## ⚙️ 옵션 설명

### 필수 옵션

없음 (모든 옵션은 선택사항)

### 선택 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `--tenant-id` | string | `ye_pipeline_test_tenant` | Tenant ID 지정 |
| `--variants-count` | int | `3` | 각 Job당 생성할 Variant 개수 |
| `--image-paths` | string[] | 자동 선택 | 사용할 이미지 파일 경로들 (여러 개 지정 가능) |
| `--create-interval` | int | `60` | Job 생성 간격 (초, `--wait-for-completion` 미사용 시) |
| `--once` | flag | `False` | Job을 한 번만 생성하고 종료 |
| `--wait-for-completion` | flag | `False` | 이전 Job 완료 대기 후 다음 Job 생성 |

---

## 📝 사용 예제

### 예제 1: 기본 단일 Job 생성

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py --once
```

**생성 결과**:
- Job ID: `bb0c38a8-3aaa-4591-99c4-3e13bfc985f8`
- Variants: 3개
- 상태: `user_img_input (done)`

### 예제 2: 특정 이미지 파일 사용

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --once \
  --image-paths pipeline_test/pipeline_test_image9.jpg \
                pipeline_test/pipeline_test_image1.png \
                pipeline_test/pipeline_test_image16.jpg
```

**설명**:
- 지정한 이미지 파일 중 **첫 번째 이미지만 사용**
- **모든 variants가 같은 이미지와 같은 `img_asset_id`를 사용**

### 예제 3: Variants 개수 변경

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --once \
  --variants-count 5
```

**설명**:
- 5개의 Variants 생성
- **모든 variants가 같은 이미지와 같은 `img_asset_id`를 사용**

### 예제 4: 백그라운드 실행 (완료 대기)

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --tenant-id ye_test_tenant_v2 \
  --wait-for-completion
```

**동작**:
1. Job 1 생성 → `user_img_input (done)` → [YE 파트가 `img_gen` 완료] → ... → `iou_eval (done)`
2. Job 1 완료 확인 → Job 2 생성
3. Job 2 완료 확인 → Job 3 생성
4. ... (반복)

### 예제 5: 주기적 생성 (60초 간격)

```bash
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --tenant-id ye_test_tenant \
  --create-interval 60
```

**동작**:
- 60초마다 새로운 Job 생성
- 이전 Job 완료 여부와 관계없이 생성

---

## 🔄 파이프라인 흐름

### 전체 흐름

```
[YE 파트 시작]
1. user_img_input (done)  ← 스크립트가 생성하는 상태
   ↓ [YE 파트가 실제로 img_gen 완료]
2. img_gen (running)  ← YE 파트가 처리
   ↓
3. img_gen (done)  ← YE 파트 완료
   ↓ [자동 트리거]
[YH 파트 시작]
4. vlm_analyze
   ↓
5. yolo_detect
   ↓
6. planner
   ↓
7. overlay
   ↓
8. vlm_judge
   ↓
9. ocr_eval
   ↓
10. readability_eval
   ↓
11. iou_eval (done)  ← 모든 Variants 완료
```

### 트리거 메커니즘

1. **스크립트 실행**: `user_img_input (done)` 상태로 Job과 Variants 생성
   - ⚠️ **트리거를 발동하지 않음** - YE 파트가 실제로 `img_gen`을 완료할 때까지 대기
2. **YE 파트 처리**: YE 파트가 실제로 `img_gen`을 완료하면 `img_gen (done)` 상태로 변경
3. **자동 진행**: PostgreSQL 트리거가 `img_gen (done)` 감지 → `vlm_analyze` API 호출
4. **파이프라인 진행**: 각 단계가 자동으로 다음 단계를 트리거

---

## 📊 생성되는 데이터 구조

### 1. Job 테이블

```sql
INSERT INTO jobs (
    job_id, tenant_id, store_id,
    status='done', current_step='user_img_input',
    created_at, updated_at
)
```

**상태**: `status='done'`, `current_step='user_img_input'`

### 2. Job Inputs 테이블

```sql
INSERT INTO job_inputs (
    job_id, img_asset_id, tone_style_id,
    desc_kor='YE 파트 테스트용 이미지',
    created_at, updated_at
)
```

**중요**: `img_asset_id`는 모든 variants와 동일한 `image_asset_id`를 사용합니다.

### 3. Image Assets 테이블

```sql
INSERT INTO image_assets (
    image_asset_id, image_type='generated',
    image_url, width, height,
    tenant_id, created_at, updated_at
)
```

**이미지 소스**: `pipeline_test/` 디렉토리의 기존 이미지 파일 (첫 번째 이미지만 사용)

**중요**: 
- **하나의 이미지만 로드**하고 **하나의 `image_asset_id`만 생성**합니다.
- 모든 variants와 `job_inputs`가 이 동일한 `image_asset_id`를 참조합니다.

### 4. Job Variants 테이블

```sql
INSERT INTO jobs_variants (
    job_variants_id, job_id, img_asset_id,
    creation_order, status='done',
    current_step='user_img_input',
    created_at, updated_at
)
```

**Variants 개수**: 기본 3개 (옵션으로 변경 가능)

**중요**: 
- **모든 variants가 동일한 `img_asset_id`를 사용**합니다.
- 각 variant는 같은 이미지를 참조하지만, `creation_order`로 구분됩니다.

---

## 🖼️ 이미지 파일 경로

### 기본 이미지 경로

스크립트는 다음 경로에서 이미지를 자동으로 찾습니다:

```
pipeline_test/
├── pipeline_test_image9.jpg      (우선순위 1)
├── pipeline_test_image1.png      (우선순위 2)
├── pipeline_test_image16.jpg      (우선순위 3)
├── pipeline_test_image10.jpg     (우선순위 4)
└── pipeline_test_image11.jpg     (우선순위 5)
```

**동작**:
- 위 순서대로 이미지 파일을 찾음
- **첫 번째로 찾은 이미지만 사용** (모든 variants가 같은 이미지 사용)
- `--image-paths` 옵션으로 직접 지정 가능

### 이미지 파일 지정

```bash
--image-paths pipeline_test/pipeline_test_image9.jpg \
              pipeline_test/pipeline_test_image1.png
```

**설명**:
- 지정한 이미지 파일 중 **첫 번째 이미지만 사용**
- **모든 variants가 같은 이미지와 같은 `img_asset_id`를 사용**
- `--image-paths`로 여러 이미지를 지정해도 첫 번째 이미지만 사용됩니다

---

## 🔍 Job 상태 확인

### 데이터베이스에서 확인

```sql
-- Job 상태 확인
SELECT job_id, status, current_step, created_at
FROM jobs
WHERE tenant_id = 'ye_pipeline_test_tenant'
ORDER BY created_at DESC
LIMIT 5;

-- Variants 상태 확인
SELECT 
    jv.job_variants_id,
    jv.job_id,
    jv.status,
    jv.current_step,
    jv.creation_order,
    ia.image_url
FROM jobs_variants jv
INNER JOIN image_assets ia ON jv.img_asset_id = ia.image_asset_id
WHERE jv.job_id = 'bb0c38a8-3aaa-4591-99c4-3e13bfc985f8'
ORDER BY jv.creation_order;
```

### Python 스크립트로 확인

```python
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # Job 상태
    job = db.execute(text("""
        SELECT job_id, status, current_step
        FROM jobs
        WHERE job_id = :job_id
    """), {"job_id": "bb0c38a8-3aaa-4591-99c4-3e13bfc985f8"}).first()
    
    print(f"Job: {job[0]}, Status: {job[1]}, Step: {job[2]}")
    
    # Variants 상태
    variants = db.execute(text("""
        SELECT job_variants_id, status, current_step
        FROM jobs_variants
        WHERE job_id = :job_id
        ORDER BY creation_order
    """), {"job_id": "bb0c38a8-3aaa-4591-99c4-3e13bfc985f8"}).fetchall()
    
    for variant in variants:
        print(f"Variant: {variant[0]}, Status: {variant[1]}, Step: {variant[2]}")
finally:
    db.close()
```

---

## ⚠️ 주의사항

### 1. 이미지 파일 존재 확인

**문제**: 이미지 파일을 찾을 수 없음

```
FileNotFoundError: 이미지 파일을 찾을 수 없습니다.
```

**해결**:
- `pipeline_test/` 디렉토리에 이미지 파일이 있는지 확인
- `--image-paths` 옵션으로 직접 경로 지정

### 2. 트리거 발동 확인

**문제**: 파이프라인이 진행되지 않음

**확인 사항**:
- `job_state_listener.py`가 실행 중인지 확인
- PostgreSQL 트리거가 정상 작동하는지 확인
- `jobs_variants` 상태가 `user_img_input (done)` → `img_gen (done)`으로 변경되었는지 확인

### 3. 백그라운드 실행 종료

**종료 방법**:
- `Ctrl+C`로 종료 신호 전송
- 프로세스가 정상 종료됨

**강제 종료** (필요 시):
```bash
# 실행 중인 프로세스 확인
docker exec feedlyai-work-yh python3 -c "
import os
pids = []
for pid_dir in os.listdir('/proc'):
    if not pid_dir.isdigit():
        continue
    try:
        with open(f'/proc/{pid_dir}/cmdline', 'rb') as f:
            cmdline = f.read().decode('utf-8', errors='ignore')
            if 'background_ye_pipeline_test' in cmdline:
                pids.append(pid_dir)
                print(f'PID: {pid_dir}, Command: {cmdline}')
    except:
        pass
"

# 프로세스 종료 (PID 확인 후)
docker exec feedlyai-work-yh kill <PID>
```

---

## 🔧 트러블슈팅

### 문제 1: 이미지 파일을 찾을 수 없음

**증상**:
```
FileNotFoundError: 이미지 파일을 찾을 수 없습니다.
```

**해결**:
1. `pipeline_test/` 디렉토리 확인
2. 이미지 파일이 존재하는지 확인
3. `--image-paths` 옵션으로 직접 경로 지정

### 문제 2: 파이프라인이 진행되지 않음

**증상**: `user_img_input (done)` 상태에서 멈춤

**확인 사항**:
1. `job_state_listener.py` 실행 상태 확인
2. PostgreSQL 트리거 정상 작동 확인
3. YE 파트가 실제로 `img_gen`을 완료했는지 확인

**해결**:
- 스크립트는 `user_img_input (done)` 상태로만 생성합니다
- **YE 파트 시작 트리거**: `user_img_input (done)` → YE 파트가 `img_gen` 시작
- **YE 파트 완료**: `img_gen (done)` → YH 파트 파이프라인 자동 시작
- YE 파트가 실제로 `img_gen`을 완료해야 YH 파트 파이프라인이 시작됩니다
- 만약 테스트 목적으로 YE 파트 완료를 시뮬레이션하려면 (권장하지 않음):
```sql
-- YE 파트 완료 시뮬레이션 (테스트용 - 권장하지 않음)
-- ⚠️ 실제 YE 파트가 img_gen을 완료하면 자동으로 YH 파트가 시작됩니다
UPDATE jobs_variants
SET status = 'running', current_step = 'img_gen', updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'bf19f5ad-029e-408b-9d65-25180ada9fd9';

UPDATE jobs_variants
SET status = 'done', current_step = 'img_gen', updated_at = CURRENT_TIMESTAMP
WHERE job_id = 'bf19f5ad-029e-408b-9d65-25180ada9fd9';
```

### 문제 3: Docker 컨테이너 내에서 실행 오류

**증상**: 모듈을 찾을 수 없음

**해결**:
- 반드시 Docker 컨테이너 내에서 실행
- `docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py`

---

## 📚 관련 문서

- `DOCS_PIPELINE_COMPLETE_FLOW.md`: 전체 파이프라인 흐름 설명
- `DOCS_JS_PART_IMPLEMENTATION.md`: JS 파트 구현 가이드
- `DOCS_YH_PART_IMPLEMENTATION.md`: YH 파트 구현 가이드
- `scripts/background_job_creator.py`: 기존 Job Creator (참고용)

---

## 📞 문의

문제가 발생하거나 질문이 있으면 개발팀에 문의하세요.

---

**버전 히스토리**:
- **v1.2.0** (2025-12-01): 모든 variants가 동일한 `img_asset_id`를 사용하도록 업데이트
- **v1.1.0** (2025-12-01): YE 파트 시작/종료 트리거 명확화
- **v1.0.0** (2025-12-01): 초기 버전 작성


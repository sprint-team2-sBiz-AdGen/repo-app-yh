# Assets 디렉토리 구조

## 공용 디렉토리: `/opt/feedlyai/assets`

```
/opt/feedlyai/assets/
├── ye/          # app-ye 파트 전용 (이미지 생성/분석)
├── yh/          # app-yh 파트 전용 (YOLO/Planner/Overlay/Eval/Judge)
├── js/          # app-js 파트 전용 (FE/BFF & 업로드/Job 제출)
├── sh/          # app-sh 파트 전용 (이미지 향상/배경 제거)
└── shared/      # 모든 파트가 공유하는 파일
```

## 각 파트별 내부 구조

각 파트 폴더 내부는 다음과 같은 구조를 권장합니다:

```
{PART_NAME}/
├── tenants/
│   └── {tenant_id}/
│       ├── original/      # 원본 이미지
│       ├── generated/     # 생성된 이미지
│       ├── enhanced/      # 향상된 이미지
│       ├── detection/     # YOLO 감지 결과
│       ├── overlay/       # 오버레이 레이아웃
│       └── final/         # 최종 렌더링 결과
├── models/                # 모델 파일 (선택사항)
└── temp/                  # 임시 파일
```

## 사용 예시

### app-yh에서 파일 저장
```python
# 저장 경로: /opt/feedlyai/assets/yh/tenants/{tenant_id}/final/2025/11/16/{uuid}.png
# URL: /assets/yh/tenants/{tenant_id}/final/2025/11/16/{uuid}.png
```

### app-ye에서 파일 저장
```python
# 저장 경로: /opt/feedlyai/assets/ye/tenants/{tenant_id}/generated/2025/11/16/{uuid}.png
# URL: /assets/ye/tenants/{tenant_id}/generated/2025/11/16/{uuid}.png
```

## 공유 파일 사용

모든 파트가 공유해야 하는 파일은 `shared/` 폴더에 저장:

```python
# 공유 파일 경로
shared_path = os.path.join(ASSETS_DIR, "shared", "common_model.pt")
# URL: /assets/shared/common_model.pt
```

## 권한

- 모든 파트 폴더: 777 권한 (모든 사용자 읽기/쓰기)
- 각 파트는 자신의 폴더에만 쓰기 권한을 사용하는 것을 권장
- shared 폴더는 모든 파트가 읽기/쓰기 가능

## 환경 변수 설정

각 파트의 `.env` 또는 `docker-compose.yml`에서:

```bash
# 공용 assets 디렉토리
ASSETS_DIR=/opt/feedlyai/assets

# 파트 이름 (각자 설정)
PART_NAME=yh  # 또는 ye, js, sh
```


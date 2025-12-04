# FeedlyAI - AI 기반 인스타그램 광고 자동 생성 시스템

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**FeedlyAI**는 사용자 입력만으로 완전 자동화된 인스타그램 광고 이미지와 피드 글을 생성하는 AI 기반 시스템입니다.

## 📋 목차

- [주요 기능](#주요-기능)
- [시스템 아키텍처](#시스템-아키텍처)
- [빠른 시작](#빠른-시작)
- [설치 방법](#설치-방법)
- [사용 방법](#사용-방법)
- [API 문서](#api-문서)
- [환경 변수](#환경-변수)
- [개발 가이드](#개발-가이드)
- [기여하기](#기여하기)

## ✨ 주요 기능

### 🎯 완전 자동화 파이프라인
- **10단계 자동 파이프라인**: 수동 개입 없이 전체 프로세스 실행
- **실시간 이벤트 기반**: PostgreSQL LISTEN/NOTIFY를 활용한 자동 트리거
- **다중 Variant 생성**: 각 Job당 3개의 다양한 레이아웃 variant 생성

### 🤖 AI 모델 통합
- **LLaVA (Vision-Language Model)**: 이미지-텍스트 검증 및 품질 평가
- **YOLO**: 금지 영역 감지 및 객체 탐지
- **GPT-4**: 텍스트 생성 및 번역
- **EasyOCR**: OCR 정확도 평가

### 📊 품질 평가 시스템
- **OCR 평가**: 텍스트 인식 정확도 측정
- **가독성 평가**: 텍스트 가독성 분석
- **IoU 평가**: 텍스트 위치 정확도 평가
- **VLM Judge**: AI 기반 최종 품질 판단

### 🔍 모니터링 및 추적
- **LLM 호출 추적**: 모든 GPT/LLaVA 호출 기록
- **파이프라인 상태 모니터링**: 실시간 Job 및 Variant 상태 추적
- **자동 재시도**: 실패한 단계 자동 재시도 메커니즘

## 🏗️ 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    사용자 입력                            │
│  (한국어 설명, 톤&스타일, 스토어 정보)                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              JS 파트 (텍스트 생성)                        │
│  - 한국어 → 영어 변환                                     │
│  - 영어 광고문구 생성                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              YE 파트 (이미지 생성)                        │
│  - 이미지 생성                                           │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              YH 파트 (이미지 처리 및 평가)                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Variant별 처리 (8단계)                           │   │
│  │  1. vlm_analyze (LLaVA 검증)                      │   │
│  │  2. yolo_detect (금지 영역 감지)                  │   │
│  │  3. planner (텍스트 배치 계획)                     │   │
│  │  4. overlay (텍스트 오버레이)                     │   │
│  │  5. vlm_judge (최종 품질 평가)                    │   │
│  │  6. ocr_eval (OCR 평가)                           │   │
│  │  7. readability_eval (가독성 평가)                 │   │
│  │  8. iou_eval (위치 정확도 평가)                    │   │
│  └──────────────────────────────────────────────────┘   │
│                        ↓                                 │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Job 레벨 처리 (2단계)                             │   │
│  │  9. ad_copy_gen_kor (영어 → 한글 변환)             │   │
│  │  10. instagram_feed_gen (피드 글 생성)            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│              최종 결과물                                   │
│  - 오버레이된 광고 이미지 (3개 variants)                 │
│  - 인스타그램 피드 글 + 해시태그                         │
└─────────────────────────────────────────────────────────┘
```

### 핵심 컴포넌트

1. **PostgreSQL LISTEN/NOTIFY**: 실시간 이벤트 기반 트리거
2. **Job State Listener**: 상태 변화 감지 및 파이프라인 트리거
3. **Pipeline Trigger**: 다음 단계 자동 실행
4. **AI 모델 서비스**: LLaVA, YOLO, GPT 통합
5. **품질 평가 시스템**: OCR, 가독성, IoU 평가

## 🚀 빠른 시작

### 사전 요구사항

- Docker & Docker Compose
- Python 3.11+
- PostgreSQL 14+
- NVIDIA GPU (LLaVA 모델 사용 시 권장)
- CUDA 11.8+ (GPU 사용 시)

### Docker로 실행

```bash
# 저장소 클론
git clone https://github.com/sprint-team2-sBiz-AdGen/repo-app-yh.git
cd repo-app-yh

# 환경 변수 설정
cp .env.example .env
# .env 파일 편집 (필요한 설정 추가)

# Docker Compose로 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f
```

### 로컬 개발 환경 설정

```bash
# 가상 환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
export DATABASE_URL="postgresql://user:password@localhost:5432/feedlyai"
export OPENAPI_KEY="your-openai-api-key"

# 애플리케이션 실행
uvicorn main:app --host 0.0.0.0 --port 8011 --reload
```

## 📦 설치 방법

### 1. 저장소 클론

```bash
git clone https://github.com/sprint-team2-sBiz-AdGen/repo-app-yh.git
cd repo-app-yh
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 다음 변수들을 설정하세요:

```env
# 데이터베이스
DB_HOST=postgres
DB_PORT=5432
DB_NAME=feedlyai
DB_USER=feedlyai
DB_PASSWORD=your_password

# OpenAI API
OPENAPI_KEY=your-openai-api-key

# 애플리케이션 설정
PART_NAME=yh
PORT=8011
HOST=0.0.0.0

# LLaVA 모델 설정
USE_QUANTIZATION=true
DEVICE_TYPE=cuda

# Job State Listener
ENABLE_JOB_STATE_LISTENER=true
```

### 3. 데이터베이스 초기화

```bash
# PostgreSQL 컨테이너 실행
docker-compose up -d postgres

# 스키마 초기화
docker-compose exec postgres psql -U feedlyai -d feedlyai -f /docker-entrypoint-initdb.d/01_schema.sql
```

### 4. 모델 다운로드

```bash
# YOLO 모델 다운로드
python download_yolo_model.py

# LLaVA 모델은 첫 실행 시 자동 다운로드됩니다
```

## 💻 사용 방법

### 파이프라인 실행

1. **Job 생성** (JS 파트에서 처리)
2. **이미지 생성** (YE 파트에서 처리)
3. **자동 파이프라인 실행** (YH 파트에서 자동 처리)

### 모니터링

```bash
# Job 상태 모니터링
python scripts/monitor_job_pipeline.py <job_id>

# 파이프라인 결과 분석
python scripts/analyze_pipeline_results.py <job_id>
```

### 배경 작업 실행

```bash
# 배경에서 파이프라인 테스트 실행
python scripts/background_pipeline_with_text_generation.py \
    --tenant-id your_tenant_id \
    --interval 300 \
    --wait-completion
```

## 📚 API 문서

애플리케이션 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:8011/docs
- **ReDoc**: http://localhost:8011/redoc

### 주요 API 엔드포인트

#### LLaVA Stage 1 (이미지 검증)
```
POST /api/yh/llava/stage1/validate
```

#### YOLO 감지
```
POST /api/yh/yolo/detect
```

#### Planner (텍스트 배치 계획)
```
POST /api/yh/planner
```

#### Overlay (텍스트 오버레이)
```
POST /api/yh/overlay
```

#### LLaVA Stage 2 (품질 평가)
```
POST /api/yh/llava/stage2/judge
```

#### OCR 평가
```
POST /api/yh/ocr/evaluate
```

#### 가독성 평가
```
POST /api/yh/readability/evaluate
```

#### IoU 평가
```
POST /api/yh/iou/evaluate
```

#### GPT 텍스트 생성
```
POST /api/yh/gpt/eng-to-kor
```

#### 인스타그램 피드 생성
```
POST /api/yh/instagram/feed
```

## 🔧 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `DB_HOST` | PostgreSQL 호스트 | `localhost` |
| `DB_PORT` | PostgreSQL 포트 | `5432` |
| `DB_NAME` | 데이터베이스 이름 | `feedlyai` |
| `DB_USER` | 데이터베이스 사용자 | `feedlyai` |
| `DB_PASSWORD` | 데이터베이스 비밀번호 | - |
| `OPENAPI_KEY` | OpenAI API 키 | - |
| `PART_NAME` | 파트 이름 (yh, ye, js) | `yh` |
| `PORT` | 애플리케이션 포트 | `8011` |
| `HOST` | 애플리케이션 호스트 | `0.0.0.0` |
| `USE_QUANTIZATION` | 8-bit 양자화 사용 여부 | `true` |
| `DEVICE_TYPE` | 디바이스 타입 (cuda/cpu) | `cuda` |
| `ENABLE_JOB_STATE_LISTENER` | Job State Listener 활성화 | `true` |

## 🛠️ 개발 가이드

### 프로젝트 구조

```
feedlyai-work/
├── routers/          # API 라우터
│   ├── llava_stage1.py
│   ├── llava_stage2.py
│   ├── yolo.py
│   ├── planner.py
│   ├── overlay.py
│   └── ...
├── services/         # 비즈니스 로직
│   ├── llava_service.py
│   ├── yolo_service.py
│   ├── planner_service.py
│   ├── job_state_listener.py
│   └── pipeline_trigger.py
├── scripts/          # 유틸리티 스크립트
│   ├── monitor_job_pipeline.py
│   ├── analyze_pipeline_results.py
│   └── ...
├── test/             # 테스트 코드
├── presentation/     # 발표 자료
└── main.py          # 애플리케이션 진입점
```

### 코드 스타일

- **Python**: PEP 8 준수
- **타입 힌팅**: 가능한 모든 곳에서 사용
- **문서화**: Docstring 작성 필수

### 테스트 실행

```bash
# 전체 테스트 실행
pytest test/

# 특정 테스트 실행
pytest test/test_llava_stage1.py

# 커버리지 포함
pytest --cov=. test/
```

### 브랜치 전략

- `main`: 프로덕션 브랜치
- `develop`: 개발 브랜치
- `feature/*`: 기능 개발 브랜치

## 📖 추가 문서

- [프로젝트 개요](presentation/00_PROJECT_OVERVIEW.md)
- [자동화 트리거 시스템](presentation/01_AUTOMATION_TRIGGER_SYSTEM.md)
- [LLaVA 통합](presentation/02-1_LLAVA_INTEGRATION.md)
- [YOLO 통합](presentation/02-2_YOLO_INTEGRATION.md)
- [GPT 통합](presentation/02-3_GPT_INTEGRATION.md)
- [이미지 처리 및 오버레이](presentation/03_IMAGE_PROCESSING_OVERLAY.md)
- [품질 평가 시스템](presentation/04_QUALITY_EVALUATION_SYSTEM.md)
- [모니터링 및 추적](presentation/06_MONITORING_TRACING.md)

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 👥 팀

- **LEEYH205**: 프로젝트 리더 및 주요 개발자

## 🙏 감사의 말

- LLaVA 팀: Vision-Language Model 제공
- Ultralytics: YOLO 모델 제공
- OpenAI: GPT API 제공

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 이슈를 생성해주세요.

---

**FeedlyAI** - AI로 만드는 완벽한 인스타그램 광고 ✨


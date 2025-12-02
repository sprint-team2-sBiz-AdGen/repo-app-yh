# FeedlyAI 프로젝트 기능 리스트 (발표용)

## 📋 프로젝트 개요

**프로젝트명**: FeedlyAI - AI 기반 인스타그램 광고 자동 생성 시스템

**목적**: 사용자 입력(한국어 설명, 톤&스타일)을 받아서 자동으로 인스타그램 광고 이미지와 피드 글을 생성하는 엔드투엔드 파이프라인

**핵심 가치**: 
- 완전 자동화된 파이프라인 (수동 개입 최소화)
- 실시간 이벤트 기반 아키텍처
- 다단계 품질 평가 시스템
- LLM 호출 추적 및 모니터링

---

## 🎯 주요 기능 카테고리

### 1. 자동화 및 트리거 시스템
### 2. AI 모델 통합 (LLaVA, YOLO, GPT)
### 3. 이미지 처리 및 오버레이
### 4. 품질 평가 시스템
### 5. 텍스트 생성 및 변환
### 6. 모니터링 및 추적
### 7. 테스트 및 개발 도구

---

## 1️⃣ 자동화 및 트리거 시스템

### 1.1 PostgreSQL LISTEN/NOTIFY 기반 자동 트리거
**목적**: 데이터베이스 상태 변화를 실시간 감지하여 다음 파이프라인 단계를 자동 실행

**주요 특징**:
- 이벤트 기반 아키텍처 (폴링 방식 아님)
- 실시간 반응 (지연 시간 최소화)
- 완전 자동화 (수동 개입 불필요)
- 트랜잭션 원자성 보장

**구현 위치**:
- `services/job_state_listener.py`: PostgreSQL NOTIFY 리스너
- `services/pipeline_trigger.py`: 파이프라인 단계 자동 트리거
- `db/init/03_job_variants_state_notify_trigger.sql`: PostgreSQL 트리거 함수

**발표 포인트**:
- ✅ 별도의 백그라운드 스크립트 없이도 완전 자동화
- ✅ 리소스 효율적 (이벤트 기반)
- ✅ 확장 가능한 아키텍처

---

### 1.2 Job State Listener
**목적**: FastAPI 애플리케이션과 통합된 실시간 상태 모니터링 시스템

**주요 특징**:
- FastAPI 생명주기와 통합 (lifespan 이벤트)
- 자동 재연결 메커니즘
- 뒤처진 Variants 자동 복구
- 주기적 수동 복구 체크

**구현 위치**:
- `services/job_state_listener.py`
- `main.py` (lifespan 함수)

**발표 포인트**:
- ✅ 서버 시작 시 자동 실행
- ✅ 연결 끊김 시 자동 재연결
- ✅ 장애 복구 메커니즘 내장

---

### 1.3 Pipeline Trigger Service
**목적**: 파이프라인 단계별 다음 단계를 자동으로 결정하고 API 호출

**주요 특징**:
- 단계별 매핑 테이블 기반 자동 진행
- 필요한 데이터 자동 조회 (overlay_id, text, proposal_id 등)
- 중복 실행 방지 (상태 재확인)
- 에러 처리 및 실패 상태 관리

**구현 위치**:
- `services/pipeline_trigger.py`

**파이프라인 단계**:
- `img_gen (done)` → `vlm_analyze`
- `vlm_analyze (done)` → `yolo_detect`
- `yolo_detect (done)` → `planner`
- `planner (done)` → `overlay`
- `overlay (done)` → `vlm_judge`
- `vlm_judge (done)` → `ocr_eval`
- `ocr_eval (done)` → `readability_eval`
- `readability_eval (done)` → `iou_eval`
- `iou_eval (done)` → `ad_copy_gen_kor`
- `ad_copy_gen_kor (done)` → `instagram_feed_gen`

**발표 포인트**:
- ✅ 10단계 파이프라인 완전 자동화
- ✅ 단계별 의존성 자동 관리
- ✅ 실패 시 자동 복구

---

## 2️⃣ AI 모델 통합

### 2.1 LLaVA (Large Language and Vision Assistant) 통합
**목적**: 생성된 이미지와 광고문구의 적합성을 검증하고 최종 품질을 평가

**주요 특징**:
- **Stage 1**: 이미지와 광고문구 검증 (초기 단계)
- **Stage 2**: 오버레이된 이미지 최종 품질 평가
- GPU 기반 추론
- Thread-safe 모델 로딩 (한 번만 로드)

**구현 위치**:
- `services/llava_service.py`
- `routers/llava_stage1.py`
- `routers/llava_stage2.py`

**발표 포인트**:
- ✅ 멀티모달 AI 모델 활용
- ✅ 이미지-텍스트 일관성 검증
- ✅ GPU 효율적 사용 (모델 재사용)

---

### 2.2 YOLO (You Only Look Once) 객체 감지
**목적**: 이미지에서 텍스트 오버레이 가능 영역 감지

**주요 특징**:
- 객체 감지 모델 (텍스트 영역 탐지)
- 바운딩 박스 좌표 반환
- 오버레이 위치 결정에 활용

**구현 위치**:
- `services/yolo_service.py`
- `routers/yolo.py`

**발표 포인트**:
- ✅ 실시간 객체 감지
- ✅ 텍스트 배치 최적화

---

### 2.3 GPT (Generative Pre-trained Transformer) 통합
**목적**: 텍스트 생성 및 변환 (한국어↔영어, 광고문구 생성, 피드 글 생성)

**주요 특징**:
- **kor_to_eng**: 한국어 → 영어 변환
- **ad_copy_eng**: 영어 광고문구 생성
- **ad_copy_kor**: 한글 광고문구 생성
- **eng_to_kor**: 영어 → 한글 변환
- **feed_gen**: 인스타그램 피드 글 생성
- 모든 호출 추적 (llm_traces 테이블)

**구현 위치**:
- `services/gpt_service.py`
- `routers/gpt.py`
- `routers/instagram_feed.py`
- `routers/refined_ad_copy.py`

**발표 포인트**:
- ✅ 다양한 텍스트 생성 작업 지원
- ✅ LLM 호출 완전 추적
- ✅ 토큰 사용량 모니터링

---

## 3️⃣ 이미지 처리 및 오버레이

### 3.1 Planner Service
**목적**: 텍스트 오버레이 위치 및 스타일 계획

**주요 특징**:
- YOLO 감지 결과 기반 위치 결정
- 텍스트 스타일 및 크기 결정
- 레이아웃 제안 생성

**구현 위치**:
- `services/planner_service.py`
- `routers/planner.py`

**발표 포인트**:
- ✅ 자동 레이아웃 최적화
- ✅ 텍스트 가독성 고려

---

### 3.2 Overlay Service
**목적**: 이미지에 텍스트 오버레이 적용

**주요 특징**:
- 한글 폰트 지원 (나눔고딕)
- 텍스트 위치 및 스타일 적용
- 오버레이된 이미지 저장

**구현 위치**:
- `routers/overlay.py`

**발표 포인트**:
- ✅ 한글 폰트 완벽 지원
- ✅ 고품질 텍스트 렌더링

---

## 4️⃣ 품질 평가 시스템

### 4.1 OCR 평가 (Optical Character Recognition)
**목적**: 오버레이된 텍스트의 OCR 인식 정확도 평가

**주요 특징**:
- EasyOCR 사용 (한글, 영어 지원)
- 원본 텍스트와 인식 결과 비교
- 다양한 메트릭 제공 (신뢰도, 정확도, 문자/단어 일치율)

**구현 위치**:
- `services/ocr_service.py`
- `routers/ocr_eval.py`

**발표 포인트**:
- ✅ 다국어 OCR 지원
- ✅ 정량적 품질 평가

---

### 4.2 가독성 평가 (Readability Evaluation)
**목적**: 오버레이된 텍스트의 가독성 평가

**주요 특징**:
- 텍스트와 배경의 대비 분석
- 가독성 점수 계산
- 시각적 품질 평가

**구현 위치**:
- `services/readability_service.py`
- `routers/readability_eval.py`

**발표 포인트**:
- ✅ 객관적 가독성 측정
- ✅ 사용자 경험 최적화

---

### 4.3 IoU 평가 (Intersection over Union)
**목적**: 오버레이된 텍스트와 원본 제안 위치의 일치도 평가

**주요 특징**:
- 바운딩 박스 IoU 계산
- 위치 정확도 평가
- 레이아웃 품질 측정

**구현 위치**:
- `services/iou_eval_service.py`
- `routers/iou_eval.py`

**발표 포인트**:
- ✅ 레이아웃 정확도 평가
- ✅ 자동 품질 검증

---

## 5️⃣ 텍스트 생성 및 변환

### 5.1 한국어 → 영어 변환 (kor_to_eng)
**목적**: 사용자 입력 한국어 설명을 영어로 변환

**구현 위치**:
- `routers/gpt.py` (eng-to-kor 엔드포인트)

**발표 포인트**:
- ✅ 정확한 번역
- ✅ LLM 추적 완비

---

### 5.2 광고문구 생성 (ad_copy_eng, ad_copy_kor)
**목적**: 제품 설명 기반 광고문구 생성

**주요 특징**:
- 영어 광고문구 생성
- 한글 광고문구 생성 (오버레이용)
- 톤&스타일 반영

**구현 위치**:
- JS 파트 (외부)
- `routers/gpt.py`

**발표 포인트**:
- ✅ 톤&스타일 맞춤 생성
- ✅ 다국어 지원

---

### 5.3 영어 → 한글 변환 (eng_to_kor)
**목적**: 최종 광고문구를 한글로 변환

**구현 위치**:
- `routers/gpt.py` (eng-to-kor 엔드포인트)

**발표 포인트**:
- ✅ 자연스러운 한글 변환

---

### 5.4 인스타그램 피드 글 생성 (instagram_feed_gen)
**목적**: 광고문구, 스토어 정보 기반 인스타그램 피드 글 생성

**주요 특징**:
- 해시태그 자동 생성
- 인스타그램 최적화 형식
- 스토어 정보 통합

**구현 위치**:
- `routers/instagram_feed.py`

**발표 포인트**:
- ✅ SNS 최적화 콘텐츠
- ✅ 해시태그 자동 생성

---

## 6️⃣ 모니터링 및 추적

### 6.1 LLM 추적 시스템 (llm_traces)
**목적**: 모든 LLM API 호출 추적 및 모니터링

**주요 특징**:
- 요청/응답 저장 (JSONB)
- 토큰 사용량 추적 (prompt_tokens, completion_tokens, total_tokens)
- 지연 시간 측정 (latency_ms)
- 모델 정보 추적 (llm_model_id)
- 작업 유형별 분류 (operation_type)

**데이터베이스 테이블**:
- `llm_traces`: 모든 LLM 호출 추적
- `llm_models`: LLM 모델 정보

**발표 포인트**:
- ✅ 완전한 LLM 호출 추적
- ✅ 비용 모니터링
- ✅ 성능 분석

---

### 6.2 Job 및 Variant 상태 관리
**목적**: 파이프라인 진행 상황 추적

**주요 특징**:
- Job 레벨 상태 관리
- Variant별 독립적 진행 추적
- 단계별 상태 기록
- 재시도 메커니즘 (retry_count)

**데이터베이스 테이블**:
- `jobs`: Job 레벨 상태
- `jobs_variants`: Variant별 상태

**발표 포인트**:
- ✅ 세밀한 진행 상황 추적
- ✅ 장애 복구 지원

---

## 7️⃣ 테스트 및 개발 도구

### 7.1 Background Job Creator
**목적**: 테스트용 Job 자동 생성

**주요 특징**:
- **background_pipeline_with_text_generation.py**: 전체 파이프라인 테스트용
- **background_ye_pipeline_test.py**: YE 파트 테스트용
- 완료 대기 모드 지원
- 주기적 생성 모드 지원

**구현 위치**:
- `scripts/background_pipeline_with_text_generation.py`
- `scripts/background_ye_pipeline_test.py`

**발표 포인트**:
- ✅ 자동화된 테스트 환경
- ✅ 다양한 테스트 시나리오 지원

---

### 7.2 리스너 상태 확인 도구
**목적**: 리스너 동작 확인 및 디버깅

**구현 위치**:
- `test/test_listener_status.py`
- `test/test_ye_img_gen_trigger.py`

**발표 포인트**:
- ✅ 개발자 친화적 디버깅 도구

---

## 📊 통계 및 성과

### 파이프라인 단계
- **총 10단계**: 8개 Variant별 단계 + 2개 Job 레벨 단계
- **완전 자동화**: 수동 개입 없이 전체 파이프라인 실행

### AI 모델 통합
- **LLaVA**: 이미지-텍스트 검증
- **YOLO**: 객체 감지
- **GPT**: 텍스트 생성 및 변환
- **EasyOCR**: OCR 평가

### 데이터베이스 테이블
- **20+ 테이블**: Job, Variant, Asset, Trace, Evaluation 등
- **완전한 추적**: 모든 단계의 입력/출력 저장

### 자동화 수준
- **이벤트 기반**: 실시간 반응
- **자동 복구**: 장애 시 자동 재시도
- **상태 관리**: 세밀한 진행 상황 추적

---

## 🎯 발표 시 강조할 핵심 포인트

1. **완전 자동화**: 수동 개입 없이 전체 파이프라인 실행
2. **실시간 이벤트 기반**: PostgreSQL LISTEN/NOTIFY 활용
3. **다단계 품질 평가**: OCR, 가독성, IoU 평가
4. **완전한 추적**: 모든 LLM 호출 및 파이프라인 단계 추적
5. **확장 가능한 아키텍처**: 모듈화된 설계
6. **장애 복구**: 자동 재시도 및 복구 메커니즘

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205


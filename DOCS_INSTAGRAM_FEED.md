# 인스타그램 피드 글 생성 기능

GPT를 활용한 인스타그램 피드 글 자동 생성 기능입니다.

## 📋 개요

이 기능은 조정된 광고문구(영어), 톤&스타일, 제품 설명, 스토어 정보, GPT 프롬프트를 입력받아 인스타그램에 최적화된 피드 글과 해시태그를 생성합니다.

## 🚀 실행 방법

### 1. 환경 변수 설정

`.env` 파일에 `OPENAPI_KEY` 설정:

```bash
# .env 파일 생성 또는 수정
echo "OPENAPI_KEY=your-openai-api-key-here" >> .env
```

또는 Docker Compose에서 환경 변수로 설정:

```yaml
environment:
  - OPENAPI_KEY=${OPENAPI_KEY}
```

### 2. 의존성 설치

**로컬 실행 시:**
```bash
pip install -r requirements.txt
# 또는
pip install openai python-dotenv
```

**Docker 실행 시:**
- `requirements.txt`에 이미 추가되어 있으므로 Docker 빌드 시 자동 설치됩니다.

### 3. 서버 실행

**방법 1: Docker Compose (권장)**
```bash
# Docker Compose로 실행
cd /home/leeyoungho/feedlyai-work
docker compose up --build

# 또는 백그라운드 실행
docker compose up -d --build

# 로그 확인
docker compose logs -f app-yh
```

**방법 2: 로컬 실행**
```bash
# 가상환경 활성화 (선택사항)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
python main.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8011 --reload
```

### 4. API 테스트

**방법 1: 테스트 스크립트 사용 (권장)**
```bash
# 기본 테스트
python test/test_instagram_feed.py

# 커스텀 파라미터로 테스트
python test/test_instagram_feed.py \
  --tenant-id "my_tenant" \
  --refined-ad-copy-eng "Your English ad copy here" \
  --tone-style "친근하고 따뜻한" \
  --product-description "제품 설명" \
  --store-information "스토어 정보" \
  --gpt-prompt "인스타그램에 어울리는 매력적인 피드 글을 작성해주세요"
```

**방법 2: curl 사용**
```bash
curl -X POST http://localhost:8011/api/yh/instagram/feed \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test_tenant",
    "refined_ad_copy_eng": "Delicious Korean Army Stew - A perfect blend of spicy, savory, and comforting flavors.",
    "tone_style": "친근하고 따뜻한",
    "product_description": "부대찌개 - 다양한 재료가 어우러진 한국의 대표적인 퓨전 요리",
    "store_information": "서울 강남구 테헤란로",
    "gpt_prompt": "인스타그램에 어울리는 매력적인 피드 글을 작성해주세요"
  }'
```

**방법 3: FastAPI 문서 사용**
브라우저에서 접속:
```
http://localhost:8011/docs
```
- `/api/yh/instagram/feed` 엔드포인트에서 직접 테스트 가능

**방법 4: Docker 컨테이너 내에서 테스트**
```bash
# Docker 컨테이너 내에서 테스트 실행
docker exec feedlyai-work-yh python3 test/test_instagram_feed.py
```

## 📝 API 명세

### 엔드포인트

```
POST /api/yh/instagram/feed
```

### 요청 (InstagramFeedIn)

```json
{
  "tenant_id": "string",
  "refined_ad_copy_eng": "string",
  "tone_style": "string",
  "product_description": "string",
  "store_information": "string",
  "gpt_prompt": "string"
}
```

**필드 설명:**
- `tenant_id`: 테넌트 ID (필수)
- `refined_ad_copy_eng`: 조정된 광고문구 (영어, 필수)
- `tone_style`: 톤 & 스타일 (필수)
- `product_description`: 제품 설명 (필수)
- `store_information`: 스토어 정보 (필수)
- `gpt_prompt`: GPT 프롬프트 (필수)

### 응답 (InstagramFeedOut)

```json
{
  "instagram_feed_id": "string",
  "tenant_id": "string",
  "instagram_ad_copy": "string",
  "hashtags": "string",
  "prompt_used": "string",
  "generated_at": "string"
}
```

**필드 설명:**
- `instagram_feed_id`: 생성된 피드 ID (UUID, DB에 저장된 레코드 ID)
- `tenant_id`: 테넌트 ID
- `instagram_ad_copy`: 생성된 인스타그램 피드 글
- `hashtags`: 생성된 해시태그 (예: "#태그1 #태그2 #태그3")
- `prompt_used`: 사용된 프롬프트 (디버깅용)
- `generated_at`: 생성 시간 (ISO 8601 형식)

### 응답 예시

```json
{
  "instagram_feed_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_id": "test_tenant",
  "instagram_ad_copy": "맛있는 부대찌개를 만나보세요! 🍲\n\n다양한 재료가 어우러진 한국의 대표적인 퓨전 요리로, 매콤하고 진한 국물이 일품입니다. 친구들과 함께 나누면 더욱 맛있는 특별한 경험을 선사합니다.\n\n서울 강남구 테헤란로에서 만나보실 수 있습니다!",
  "hashtags": "#부대찌개 #맛집 #서울강남 #한식 #데일리 #푸드스타그램 #맛스타그램 #한국음식",
  "prompt_used": "System: ...\n\nUser: ...",
  "generated_at": "2025-01-XXT12:00:00Z"
}
```

## ⚙️ 설정

### config.py

```python
# GPT API 설정
GPT_API_KEY = os.getenv("OPENAPI_KEY") or os.getenv("GPT_API_KEY", "")
GPT_MODEL_NAME = os.getenv("GPT_MODEL_NAME", "gpt-4o-mini")
GPT_MAX_TOKENS = int(os.getenv("GPT_MAX_TOKENS", "1000"))
```

### 환경 변수

- `OPENAPI_KEY`: OpenAI API 키 (우선 사용)
- `GPT_API_KEY`: OpenAI API 키 (OPENAPI_KEY가 없을 때 사용)
- `GPT_MODEL_NAME`: 사용할 GPT 모델 (기본값: "gpt-4o-mini")
- `GPT_MAX_TOKENS`: 최대 토큰 수 (기본값: 1000)

## 📁 파일 구조

```
feedlyai-work/
├── routers/
│   └── instagram_feed.py      # 인스타그램 피드 라우터
├── services/
│   └── gpt_service.py          # GPT 서비스
├── models.py                   # Pydantic 모델 (InstagramFeedIn, InstagramFeedOut)
├── config.py                   # 설정 (GPT_API_KEY 등)
├── test/
│   └── test_instagram_feed.py # 테스트 스크립트
└── DOCS_INSTAGRAM_FEED.md     # 이 문서
```

## 🔧 구현 세부사항

### GPT 서비스 (services/gpt_service.py)

- OpenAI API 클라이언트 싱글톤 패턴으로 관리
- 인스타그램 피드 글 생성 로직
- 해시태그 자동 생성
- JSON 형식 응답 처리

### 라우터 (routers/instagram_feed.py)

- FastAPI 엔드포인트: `POST /api/yh/instagram/feed`
- 입력 검증 및 에러 처리
- GPT 서비스 호출 및 응답 반환

## ⚠️ 주의사항

1. **OPENAPI_KEY 확인**: `.env` 파일에 올바른 OpenAI API 키가 설정되어 있는지 확인하세요.
2. **네트워크**: Docker 환경에서 호스트의 `.env` 파일을 사용하려면 볼륨 마운트가 필요할 수 있습니다.
3. **API 비용**: GPT API 호출 시 비용이 발생할 수 있습니다.
4. **타임아웃**: GPT API 호출은 최대 60초 타임아웃이 설정되어 있습니다.

## 🗄️ 데이터베이스 연동

인스타그램 피드 글 생성 결과는 자동으로 데이터베이스에 저장됩니다.

자세한 테이블 설계는 [DOCS_INSTAGRAM_FEED_DB.md](./DOCS_INSTAGRAM_FEED_DB.md)를 참고하세요.

### 주요 테이블: `instagram_feeds`

- **입력 데이터 저장**: refined_ad_copy_eng, tone_style, product_description, store_information, gpt_prompt
- **출력 데이터 저장**: instagram_ad_copy, hashtags
- **GPT 메타데이터**: gpt_model_name, gpt_max_tokens, gpt_temperature, gpt_response_raw
- **성능 메트릭**: latency_ms, token_usage
- **파이프라인 연동**: job_id, overlay_id (나중에 연결)

### DB 저장 내용

API 호출 시 다음 정보가 자동으로 `instagram_feeds` 테이블에 저장됩니다:

- 모든 입력 데이터 (refined_ad_copy_eng, tone_style, product_description, store_information, gpt_prompt)
- 생성된 결과 (instagram_ad_copy, hashtags)
- GPT API 메타데이터 (gpt_model_name, gpt_max_tokens, gpt_temperature, gpt_prompt_used, gpt_response_raw)
- 성능 메트릭 (latency_ms, token_usage)
- 타임스탬프 (created_at, updated_at)

## 🔄 향후 개선 사항

- [x] 기본 기능 구현
- [x] DB 연동 (결과 저장) - [구현 완료](./DOCS_INSTAGRAM_FEED_DB.md)
- [ ] 파이프라인 연동 (job_id, overlay_id 연결)
- [ ] 배치 처리 지원
- [ ] 다양한 소셜 미디어 플랫폼 지원 (페이스북, 트위터 등)
- [ ] 생성 히스토리 관리
- [ ] A/B 테스트 기능


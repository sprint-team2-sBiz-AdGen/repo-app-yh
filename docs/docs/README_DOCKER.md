# feedlyai-work 개별 개발 환경

이 폴더는 app-yh 파트의 개별 개발 환경입니다.

## 🚀 빠른 시작

### 1. 환경 변수 설정 (선택사항)

```bash
# .env 파일 생성 (선택사항)
cp .env.example .env
# 필요에 따라 .env 파일 수정
```

### 2. Docker Compose로 실행

```bash
# 빌드 및 실행
docker compose up --build

# 백그라운드 실행
docker compose up -d --build

# 로그 확인
docker compose logs -f app-yh

# 중지
docker compose down
```

## 📋 서비스 구성

- **app-yh**: 포트 8011 (YOLO/Planner/Overlay/Eval/Judge)
- **postgres**: 포트 5433 (팀 도커와 포트 충돌 방지)
- **adminer**: 포트 8082 (DB 관리 도구)

## 🔧 설정 옵션

### 옵션 1: 개별 PostgreSQL 사용 (기본)

현재 설정은 개별 PostgreSQL을 사용합니다.
- 포트: 5433 (팀 도커의 5432와 충돌 방지)
- 데이터는 `postgres_data` 볼륨에 저장

### 옵션 2: 팀 도커의 PostgreSQL 사용

팀 도커의 postgres를 사용하려면:

1. `docker-compose.yml`에서 `postgres` 서비스 섹션 주석 처리
2. `DATABASE_URL` 환경 변수를 팀 도커의 postgres로 변경:
   ```bash
   DATABASE_URL=postgresql://feedlyai:feedlyai_dev_password_74154@host.docker.internal:5432/feedlyai
   ```
3. Docker 네트워크 연결 (필요 시)

## 📁 볼륨 마운트

- **코드**: 현재 디렉토리(`.`) → `/app` (코드 변경 시 자동 반영)
- **Assets**: `/opt/feedlyai/assets` → `/assets` (팀 도커와 동일)

## 🧪 테스트

```bash
# Health check
curl http://localhost:8011/healthz

# API 테스트
curl -X POST http://localhost:8011/api/yh/planner \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test01","asset_url":"/assets/test.jpg"}'
```

## 📝 주의사항

1. **포트 충돌**: 팀 도커와 포트가 겹치지 않도록 설정됨
   - app-yh: 8011 (동일)
   - postgres: 5433 (팀은 5432)
   - adminer: 8082 (팀은 8081)

2. **Assets 디렉토리**: 팀 도커와 동일한 경로(`/opt/feedlyai/assets`) 사용

3. **코드 변경**: 볼륨 마운트로 코드 변경 시 자동 반영 (--reload 옵션)

## 🔍 유용한 명령어

```bash
# 컨테이너 상태 확인
docker compose ps

# 특정 서비스 재시작
docker compose restart app-yh

# 컨테이너 내부 접속
docker compose exec app-yh bash

# 로그 확인
docker compose logs app-yh
docker compose logs postgres

# 볼륨 확인
docker volume ls
```




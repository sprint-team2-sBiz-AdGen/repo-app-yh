# 백그라운드 실행 가이드

## 📋 개요

Job State Listener는 FastAPI 애플리케이션의 lifespan 이벤트를 통해 자동으로 시작됩니다. 따라서 FastAPI 애플리케이션을 백그라운드로 실행하면 리스너도 함께 백그라운드에서 실행됩니다.

---

## 🚀 백그라운드 실행 방법

### 방법 1: Docker Compose로 백그라운드 실행 (권장)

현재 프로젝트는 Docker Compose를 사용하여 실행됩니다.

#### 실행 명령어

```bash
# 백그라운드로 실행 (detached mode)
cd /home/leeyoungho/feedlyai-work
docker-compose up -d

# 또는 빌드와 함께 실행
docker-compose up -d --build
```

#### 확인

```bash
# 컨테이너 상태 확인
docker ps | grep feedlyai-work-yh

# 로그 확인
docker logs feedlyai-work-yh --tail 50

# 리스너 시작 확인
docker logs feedlyai-work-yh | grep "Job State Listener"
```

#### 중지

```bash
# 컨테이너 중지
docker-compose down

# 또는 특정 컨테이너만 중지
docker stop feedlyai-work-yh
```

---

### 방법 2: Docker로 직접 백그라운드 실행

```bash
# 백그라운드로 실행
docker run -d \
  --name feedlyai-work-yh \
  --gpus all \
  -p 8011:8011 \
  -v $(pwd):/app \
  -v /opt/feedlyai/assets:/assets:rw \
  -e PART_NAME=yh \
  -e PORT=8011 \
  -e DB_HOST=host.docker.internal \
  feedlyai-app-yh

# 로그 확인
docker logs -f feedlyai-work-yh
```

---

### 방법 3: 로컬에서 uvicorn으로 백그라운드 실행

#### Linux/Mac

```bash
# nohup으로 백그라운드 실행
nohup uvicorn main:app --host 0.0.0.0 --port 8011 > app.log 2>&1 &

# 프로세스 ID 확인
echo $!

# 로그 확인
tail -f app.log

# 프로세스 종료
kill <PID>
```

#### systemd 서비스로 실행 (프로덕션 권장)

1. **서비스 파일 생성** (`/etc/systemd/system/feedlyai-yh.service`):

```ini
[Unit]
Description=FeedlyAI YH Service
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/leeyoungho/feedlyai-work
Environment="PATH=/home/leeyoungho/feedlyai-work/venv/bin"
ExecStart=/home/leeyoungho/feedlyai-work/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8011
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. **서비스 시작**:

```bash
# 서비스 활성화
sudo systemctl enable feedlyai-yh

# 서비스 시작
sudo systemctl start feedlyai-yh

# 상태 확인
sudo systemctl status feedlyai-yh

# 로그 확인
sudo journalctl -u feedlyai-yh -f
```

---

## 🔍 백그라운드 실행 확인 방법

### 1. 리스너 시작 확인

```bash
# Docker 로그에서 확인
docker logs feedlyai-work-yh | grep "Job State Listener"

# 예상 출력:
# Job State Listener 시작...
# ✓ Job State Listener 시작 완료
# LISTEN 'job_state_changed' 시작
```

### 2. 프로세스 확인

```bash
# Docker 컨테이너 확인
docker ps | grep feedlyai-work-yh

# 컨테이너 내부 프로세스 확인
docker exec feedlyai-work-yh ps aux | grep uvicorn
```

### 3. API 엔드포인트 확인

```bash
# Health check
curl http://localhost:8011/health

# 메트릭 확인
curl http://localhost:8011/metrics
```

---

## 📊 현재 실행 상태 확인

현재 프로젝트는 **Docker Compose로 백그라운드 실행 중**입니다.

```bash
# 컨테이너 상태 확인
docker ps | grep feedlyai-work-yh

# 실행 중인지 확인
docker logs feedlyai-work-yh --tail 20 | grep -E "Application startup|Job State Listener"
```

---

## 🔄 리스너 재시작

리스너는 FastAPI 애플리케이션의 lifespan 이벤트를 통해 자동으로 시작/종료됩니다.

### 리스너만 재시작하려면

```bash
# 애플리케이션 재시작 (리스너도 함께 재시작됨)
docker restart feedlyai-work-yh

# 또는 Docker Compose 사용
docker-compose restart app-yh
```

---

## ⚠️ 주의사항

### 개발 환경

- **WatchFiles 자동 리로드**: 개발 환경에서는 `--reload` 옵션으로 인해 파일 변경 시 자동 리로드됩니다.
- **이벤트 손실 가능**: 리로드 중 NOTIFY 이벤트가 손실될 수 있습니다 (개발 환경 특성).

### 프로덕션 환경

- **자동 리로드 비활성화**: `--reload` 옵션을 제거하여 안정성 확보
- **백그라운드 실행**: systemd 또는 Docker Compose로 백그라운드 실행
- **재시작 정책**: `restart: unless-stopped` 또는 `Restart=always` 설정

---

## 🧪 백그라운드 실행 테스트

백그라운드에서 실행 중인 리스너를 테스트하려면:

```bash
# 테스트 스크립트 실행
docker exec feedlyai-work-yh python3 test/test_background_trigger.py
```

이 스크립트는:
1. img_gen 완료 상태의 job 생성
2. 백그라운드 리스너가 자동으로 감지
3. 전체 파이프라인 자동 실행
4. 진행 상황 모니터링

---

## 📝 요약

**현재 상태**: Docker Compose로 백그라운드 실행 중 ✅

**리스너 상태**: FastAPI lifespan 이벤트로 자동 시작 ✅

**테스트 방법**: `test/test_background_trigger.py` 실행

**확인 방법**: `docker logs feedlyai-work-yh | grep "Job State Listener"`

---

**작성일**: 2025-11-28  
**작성자**: LEEYH205


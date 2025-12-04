# FeedlyAI 포트 매핑 및 아키텍처 도식

## 전체 포트 구조

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         팀 도커 (feedlyai/)                              │
│                    /home/leeyoungho/feedlyai                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  NGINX (Reverse Proxy - 리버스 프록시)                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  Port: ${PORT_NGINX} (기본: 8080)                                 │  │
│  │  역할: 하나의 포트로 모든 API와 정적 파일을 통합 관리             │  │
│  │                                                                   │  │
│  │  경로별 라우팅:                                                   │  │
│  │  - /api/ye/ → app-ye:8000 (컨테이너 내부 포트)                  │  │
│  │  - /api/yh/ → app-yh:8000 (컨테이너 내부 포트)                  │  │
│  │  - /api/js/ → app-js:8000 (컨테이너 내부 포트)                  │  │
│  │  - /api/sh/ → app-sh:8000 (컨테이너 내부 포트)                  │  │
│  │  - /assets/ → 정적 파일 서빙 (이미지, CSS, JS 등)               │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Application Services (팀 도커 내)                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  app-ye      │  │  app-yh      │  │  app-js      │  │  app-sh      │ │
│  │  Port:       │  │  Port:       │  │  Port:       │  │  Port:       │ │
│  │  ${PORT_YE}  │  │  ${PORT_YH}  │  │  ${PORT_JS}  │  │  ${PORT_SH}  │ │
│  │  (내부:8000) │  │  (내부:8000) │  │  (내부:8000) │  │  (내부:8000) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  PostgreSQL Services                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  postgres    │  │  postgres-ye │  │  postgres-yh │  │  postgres-js │ │
│  │  (공용)      │  │              │  │              │  │              │ │
│  │  Port: 5432  │  │  Port: 5434  │  │  Port: 5435  │  │  Port: 5436  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│  ┌──────────────┐                                                       │
│  │  postgres-sh │                                                       │
│  │              │                                                       │
│  │  Port: 5437  │                                                       │
│  └──────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Adminer Services (DB 관리 도구)                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  adminer     │  │  adminer-ye  │  │  adminer-yh  │  │  adminer-js  │ │
│  │  (공용)      │  │              │  │              │  │              │ │
│  │  Port: 8081  │  │  Port: 8083  │  │  Port: 8084  │  │  Port: 8085  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│  ┌──────────────┐                                                       │
│  │  adminer-sh  │                                                       │
│  │              │                                                       │
│  │  Port: 8086  │                                                       │
│  └──────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    개별 개발 도커 (feedlyai-work/)                       │
│              /home/{계정}/feedlyai-work                                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  Individual Development Services                                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  app (app-yh, app-ye, app-js, app-sh)                            │  │
│  │  Port: ${PORT} (예: yh는 8011)                                   │  │
│  │  → 팀 도커의 postgres-{PART_NAME}에 연결                        │  │
│  │    (host.docker.internal:5434/5435/5436/5437)                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 포트 매핑 상세

### 팀 도커 (feedlyai/)

#### NGINX 상세 설명

**NGINX란?**
- **리버스 프록시(Reverse Proxy)**: 클라이언트 요청을 받아서 적절한 백엔드 서버로 전달하는 서버
- **왜 필요한가?**
  1. **하나의 포트로 통합**: 여러 개의 앱 서비스(app-ye, app-yh, app-js, app-sh)를 각각 다른 포트로 접근할 필요 없이, 하나의 포트(8080)에서 경로(`/api/ye/`, `/api/yh/` 등)로 구분해서 접근 가능
  2. **정적 파일 서빙**: 이미지, CSS, JavaScript 같은 정적 파일을 효율적으로 제공
  3. **로드 밸런싱 준비**: 나중에 서버가 여러 개일 때 부하를 분산시킬 수 있음

**작동 방식:**
```
사용자 요청: http://localhost:8080/api/yh/predict
              ↓
[NGINX:8080] → 경로 확인 (/api/yh/) 
              ↓
         app-yh 컨테이너 내부:8000으로 프록시
              ↓
http://app-yh:8000/predict (실제 처리)
```

**실제 설정 예시:**
- 사용자가 `http://localhost:8080/api/yh/predict` 요청
- NGINX가 `/api/yh/` 경로를 보고 `app-yh` 컨테이너의 `8000` 포트로 요청 전달
- NGINX는 컨테이너 이름으로 통신하므로 내부 네트워크를 통해 연결됨
- 정적 파일(`/assets/image.jpg`)은 NGINX가 직접 서빙 (앱 컨테이너 거치지 않음)

**NGINX 없이는?**
- 각 앱을 개별 포트로 접근해야 함:
  - `http://localhost:${PORT_YE}` (app-ye)
  - `http://localhost:${PORT_YH}` (app-yh)
  - `http://localhost:${PORT_JS}` (app-js)
  - `http://localhost:${PORT_SH}` (app-sh)
- 프론트엔드에서 어떤 포트를 사용해야 할지 알아야 함
- CORS 문제나 포트 관리가 복잡해짐

**NGINX 있으면?**
- 하나의 포트(8080)로 통합 접근:
  - `http://localhost:8080/api/ye/`
  - `http://localhost:8080/api/yh/`
  - `http://localhost:8080/api/js/`
  - `http://localhost:8080/api/sh/`
  - `http://localhost:8080/assets/` (정적 파일)
- 프론트엔드는 하나의 베이스 URL만 알면 됨

#### 공용 서비스
| 서비스 | 포트 | 설명 |
|--------|------|------|
| nginx | ${PORT_NGINX} (기본: 8080) | 리버스 프록시, 정적 파일 서빙, 모든 API 통합 엔트리 포인트 |
| postgres | 5432 | 공용 PostgreSQL |
| adminer | 8081 | 공용 Adminer |

#### 팀원별 서비스

##### ye (이미지 생성/분석)
| 서비스 | 포트 | 설명 |
|--------|------|------|
| app-ye | ${PORT_YE} | 애플리케이션 서비스 |
| postgres-ye | 5434 | 개별 PostgreSQL |
| adminer-ye | 8083 | 개별 Adminer |

##### yh (YOLO/Planner/Overlay/Eval/Judge)
| 서비스 | 포트 | 설명 |
|--------|------|------|
| app-yh | ${PORT_YH} | 애플리케이션 서비스 |
| postgres-yh | 5435 | 개별 PostgreSQL |
| adminer-yh | 8084 | 개별 Adminer |

##### js (FE/BFF & 업로드/Job 제출)
| 서비스 | 포트 | 설명 |
|--------|------|------|
| app-js | ${PORT_JS} | 애플리케이션 서비스 |
| postgres-js | 5436 | 개별 PostgreSQL |
| adminer-js | 8085 | 개별 Adminer |

##### sh (이미지 향상/배경 제거)
| 서비스 | 포트 | 설명 |
|--------|------|------|
| app-sh | ${PORT_SH} | 애플리케이션 서비스 |
| postgres-sh | 5437 | 개별 PostgreSQL |
| adminer-sh | 8086 | 개별 Adminer |

### 개별 개발 도커 (feedlyai-work/)

| 팀원 | 서비스 | 포트 | 연결 대상 |
|------|--------|------|-----------|
| ye | app | ${PORT} (예: 8000) | postgres-ye:5434 |
| yh | app | ${PORT} (예: 8011) | postgres-yh:5435 |
| js | app | ${PORT} (예: 8000) | postgres-js:5436 |
| sh | app | ${PORT} (예: 8000) | postgres-sh:5437 |

## 연결 관계도

```
개발자 브라우저/클라이언트
    │
    ├─→ http://localhost:8080 (NGINX - 통합 엔트리 포인트) ⭐
    │       │
    │       ├─→ /api/ye/predict → NGINX가 app-ye:8000 (컨테이너 내부)로 프록시
    │       ├─→ /api/yh/predict → NGINX가 app-yh:8000 (컨테이너 내부)로 프록시
    │       ├─→ /api/js/upload  → NGINX가 app-js:8000 (컨테이너 내부)로 프록시
    │       ├─→ /api/sh/enhance → NGINX가 app-sh:8000 (컨테이너 내부)로 프록시
    │       └─→ /assets/image.jpg → NGINX가 직접 서빙 (앱 컨테이너 거치지 않음)
    │
    ├─→ http://localhost:${PORT_YE} (app-ye 직접 접근 - 개발/디버깅용)
    ├─→ http://localhost:${PORT_YH} (app-yh 직접 접근 - 개발/디버깅용)
    ├─→ http://localhost:${PORT_JS} (app-js 직접 접근 - 개발/디버깅용)
    ├─→ http://localhost:${PORT_SH} (app-sh 직접 접근 - 개발/디버깅용)
    │
    ├─→ http://localhost:8081 (Adminer - 공용)
    ├─→ http://localhost:8083 (Adminer - ye)
    ├─→ http://localhost:8084 (Adminer - yh)
    ├─→ http://localhost:8085 (Adminer - js)
    ├─→ http://localhost:8086 (Adminer - sh)
    │
    └─→ http://localhost:${PORT} (개별 개발 도커)
            │
            └─→ host.docker.internal:5434/5435/5436/5437
                    │
                    └─→ postgres-{PART_NAME} (팀 도커)

개별 개발 도커 (feedlyai-work)
    │
    └─→ app 컨테이너
            │
            ├─→ DB_HOST=host.docker.internal
            ├─→ DB_PORT=5434 (ye) / 5435 (yh) / 5436 (js) / 5437 (sh)
            └─→ → postgres-{PART_NAME} (팀 도커)
```

**NGINX 동작 흐름 상세:**
```
[브라우저] 
  GET http://localhost:8080/api/yh/predict
       │
       ▼
[NGINX 컨테이너:80 (외부에서는 8080)]
  ├─ 경로 분석: /api/yh/ → app-yh로 라우팅
  ├─ Docker 내부 네트워크 사용 (컨테이너 이름으로 통신)
  └─ 프록시: http://app-yh:8000/predict
              │
              ▼
      [app-yh 컨테이너:8000]
            │
            ▼
      처리 결과 반환
            │
            ▼
      [NGINX] → [브라우저]로 응답 전달
```

## 포트 범위 요약

### PostgreSQL 포트
- 공용: **5432**
- ye: **5434**
- yh: **5435**
- js: **5436**
- sh: **5437**

### Adminer 포트
- 공용: **8081**
- ye: **8083**
- yh: **8084**
- js: **8085**
- sh: **8086**

### Application 포트
- NGINX: **${PORT_NGINX}** (기본: 8080)
- app-ye: **${PORT_YE}** (환경 변수)
- app-yh: **${PORT_YH}** (환경 변수)
- app-js: **${PORT_JS}** (환경 변수)
- app-sh: **${PORT_SH}** (환경 변수)
- 개별 개발 도커: **${PORT}** (예: yh는 8011)

## 접속 예시

### 팀 도커 서비스 접속
```bash
# NGINX를 통한 통합 접근 (추천)
# - 모든 API는 /api/{팀원}/ 경로로 접근
http://localhost:8080/api/yh/predict
http://localhost:8080/api/js/upload
http://localhost:8080/assets/image.jpg

# NGINX 없이 직접 접근 (개발/디버깅용)
# - 각 앱 서비스의 개별 포트 사용
http://localhost:${PORT_YH}/predict  # app-yh 직접 접근
http://localhost:${PORT_JS}/upload   # app-js 직접 접근

# Adminer (yh)
http://localhost:8084

# PostgreSQL (yh)
psql -h localhost -p 5435 -U feedlyai -d feedlyai
```

### 개별 개발 도커 접속
```bash
# 개발 서비스 (yh 예시)
http://localhost:8011

# 이 서비스는 팀 도커의 postgres-yh:5435에 연결됨
```

## 네트워크 흐름

```
[개발자] 
    │
    ├─→ [NGINX:8080] → [app-ye/yh/js/sh] → [postgres-{name}:5434~5437]
    │
    ├─→ [Adminer:8081/8083~8086] → [postgres-{name}:5432/5434~5437]
    │
    └─→ [개별 개발 도커:${PORT}] 
            │
            └─→ [host.docker.internal] → [postgres-{name}:5434~5437]
```

## 주의사항

1. **개별 개발 도커**는 팀 도커의 postgres를 사용하므로, 팀 도커에서 해당 postgres가 먼저 실행되어야 합니다.

2. **NGINX**는 모든 app 서비스를 프록시하므로, app 서비스들이 실행되어 있어야 프록시가 작동합니다.

3. **포트 충돌**: 각 팀원은 자신의 포트를 사용하므로 충돌이 없습니다.

4. **host.docker.internal**: Linux에서는 `extra_hosts` 설정이 필요합니다 (이미 설정됨).


# Jobs 테이블 상태 변화 감지 및 자동 파이프라인 실행 분석

## 📋 현재 파이프라인 구조

### 파이프라인 단계 순서
```
img_gen (done) 
  → vlm_analyze (LLaVA Stage 1) [status: running → done]
  → yolo_detect [status: running → done]
  → planner [status: running → done]
  → overlay [status: running → done]
```

### 현재 상태 변화 패턴
각 API 엔드포인트에서:
1. **이전 단계 완료 확인**: `current_step='이전단계'`, `status='done'` 체크
2. **현재 단계 시작**: `current_step='현재단계'`, `status='running'` 업데이트
3. **작업 수행**: 실제 작업 (LLaVA 분석, YOLO 감지 등)
4. **완료 처리**: `status='done'` 업데이트

### LLaVA 실행 조건
- **트리거 조건**: `current_step='img_gen'`, `status='done'`
- **실행 후 상태**: `current_step='vlm_analyze'`, `status='running'` → `status='done'`

---

## 🔍 상태 변화 감지 방법 옵션

### 옵션 1: PostgreSQL LISTEN/NOTIFY (이벤트 기반) ⭐ 추천

#### 작동 방식
- PostgreSQL 트리거가 `jobs` 테이블 변경 감지
- `pg_notify()`로 이벤트 발행
- Python에서 `psycopg2` 또는 `asyncpg`로 `LISTEN`하여 실시간 수신

#### 장점
- ✅ **실시간 반응**: DB 변경 즉시 감지
- ✅ **낮은 지연시간**: 폴링 오버헤드 없음
- ✅ **PostgreSQL 네이티브**: 추가 인프라 불필요
- ✅ **확장 가능**: 여러 워커가 동시에 LISTEN 가능
- ✅ **리소스 효율**: DB 연결만 유지하면 됨

#### 단점
- ⚠️ **연결 관리**: DB 연결이 끊기면 재연결 필요
- ⚠️ **트리거 작성**: PostgreSQL 트리거 함수 작성 필요
- ⚠️ **에러 처리**: 이벤트 손실 시 복구 로직 필요

#### 구현 복잡도
- **중간**: 트리거 함수 작성 + Python LISTEN 로직

#### 예상 코드 구조
```python
# 백그라운드 워커 (별도 프로세스 또는 FastAPI startup 이벤트)
async def job_state_listener():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.add_listener('job_state_changed', handle_job_state_change)
    
async def handle_job_state_change(conn, pid, channel, payload):
    # payload: JSON {"job_id": "...", "current_step": "...", "status": "..."}
    if payload['current_step'] == 'img_gen' and payload['status'] == 'done':
        # LLaVA 실행
        await trigger_llava_stage1(payload['job_id'])
```

```sql
-- PostgreSQL 트리거 함수
CREATE OR REPLACE FUNCTION notify_job_state_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('job_state_changed', 
        json_build_object(
            'job_id', NEW.job_id,
            'current_step', NEW.current_step,
            'status', NEW.status
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER job_state_change_trigger
AFTER UPDATE ON jobs
FOR EACH ROW
WHEN (OLD.current_step IS DISTINCT FROM NEW.current_step 
   OR OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION notify_job_state_change();
```

---

### 옵션 2: Polling (주기적 조회)

#### 작동 방식
- 주기적으로 `jobs` 테이블을 조회
- `current_step='img_gen'`, `status='done'`인 job 찾기
- LLaVA 실행 후 상태 업데이트

#### 장점
- ✅ **구현 간단**: 단순한 SELECT 쿼리
- ✅ **안정적**: 연결 끊김 걱정 없음
- ✅ **디버깅 용이**: 로그로 확인 가능

#### 단점
- ❌ **지연시간**: 폴링 간격만큼 지연 (예: 5초 간격)
- ❌ **리소스 낭비**: 불필요한 DB 쿼리 반복
- ❌ **확장성 제한**: 여러 워커 시 중복 실행 가능성
- ❌ **실시간성 부족**: 즉시 반응 불가

#### 구현 복잡도
- **낮음**: 단순 SELECT + 주기적 실행

#### 예상 코드 구조
```python
# 백그라운드 태스크 (FastAPI BackgroundTasks 또는 별도 프로세스)
async def poll_jobs_for_llava():
    while True:
        db = SessionLocal()
        try:
            # LLaVA 실행 대기 중인 job 찾기
            jobs = db.query(Job).filter(
                Job.current_step == 'img_gen',
                Job.status == 'done'
            ).all()
            
            for job in jobs:
                await trigger_llava_stage1(job.job_id)
        finally:
            db.close()
        
        await asyncio.sleep(5)  # 5초 간격
```

---

### 옵션 3: Database Trigger + 외부 워커 (파일/HTTP)

#### 작동 방식
- PostgreSQL 트리거가 변경 감지
- 외부 파일 생성 또는 HTTP 웹훅 호출
- 별도 워커 프로세스가 파일/웹훅 모니터링

#### 장점
- ✅ **느슨한 결합**: DB와 워커 분리
- ✅ **다양한 구현**: 파일, HTTP, 메시지 큐 등 선택 가능

#### 단점
- ❌ **복잡도 높음**: 트리거 + 외부 시스템 연동
- ❌ **에러 처리 복잡**: 여러 시스템 간 동기화
- ❌ **인프라 추가**: 파일 시스템 또는 HTTP 서버 필요

#### 구현 복잡도
- **높음**: 트리거 + 외부 시스템 연동

---

### 옵션 4: Change Data Capture (CDC)

#### 작동 방식
- PostgreSQL WAL (Write-Ahead Log) 모니터링
- Debezium, pg_logical 등 CDC 도구 사용
- 변경사항을 Kafka/이벤트 스트림으로 전달

#### 장점
- ✅ **완전한 변경 추적**: 모든 변경사항 기록
- ✅ **확장성**: 이벤트 스트림 기반 아키텍처
- ✅ **복구 가능**: 과거 변경사항 재처리 가능

#### 단점
- ❌ **과도한 복잡도**: 현재 요구사항에 비해 과함
- ❌ **인프라 부담**: Kafka 등 추가 인프라 필요
- ❌ **설정 복잡**: CDC 도구 설정 및 운영 필요

#### 구현 복잡도
- **매우 높음**: CDC 도구 설정 및 운영

---

## 🎯 추천 방안

### 1순위: PostgreSQL LISTEN/NOTIFY (옵션 1) ⭐

**이유:**
- 실시간 반응 가능
- 추가 인프라 불필요 (PostgreSQL만 사용)
- 구현 복잡도 적절
- 현재 아키텍처와 잘 맞음

**구현 단계:**
1. PostgreSQL 트리거 함수 작성
2. FastAPI startup 이벤트에서 LISTEN 시작
3. 이벤트 핸들러에서 LLaVA 실행

**주의사항:**
- DB 연결 관리 (재연결 로직)
- 중복 실행 방지 (job 상태 체크)
- 에러 처리 및 재시도 로직

---

### 2순위: Polling (옵션 2)

**이유:**
- 구현이 가장 간단
- 안정적이고 예측 가능
- 빠른 프로토타이핑에 적합

**구현 단계:**
1. FastAPI BackgroundTasks 또는 별도 프로세스
2. 주기적 SELECT 쿼리 (5-10초 간격)
3. LLaVA 실행 및 상태 업데이트

**주의사항:**
- 폴링 간격 조정 (너무 짧으면 부하, 너무 길면 지연)
- 중복 실행 방지 (job 상태 체크)
- 여러 워커 시 동시성 제어

---

## 📊 비교표

| 방법 | 실시간성 | 복잡도 | 인프라 | 확장성 | 안정성 |
|------|---------|--------|--------|--------|--------|
| LISTEN/NOTIFY | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Polling | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Trigger + 외부 | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| CDC | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 🔧 구현 고려사항

### 공통 고려사항

1. **중복 실행 방지**
   - LLaVA 실행 전 job 상태 재확인
   - `current_step='img_gen'`, `status='done'`인지 재검증
   - 실행 시작 시 즉시 상태 업데이트 (`status='running'`)

2. **에러 처리**
   - LLaVA 실행 실패 시 `status='failed'` 업데이트
   - 재시도 로직 (선택사항)
   - 로깅 및 모니터링

3. **동시성 제어**
   - 여러 워커가 같은 job 처리 시도 방지
   - DB 트랜잭션 및 락 활용

4. **확장성**
   - 여러 워커 인스턴스 지원
   - 부하 분산 고려

---

## 💡 다음 단계

1. **방법 선택**: LISTEN/NOTIFY 또는 Polling
2. **구현 계획 수립**: 상세 설계
3. **프로토타입 개발**: 최소 기능 구현
4. **테스트**: 다양한 시나리오 테스트
5. **운영 모니터링**: 로그 및 메트릭 수집


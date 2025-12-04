# 테스트 및 개발 도구 발표자료

## 📋 개요

**기능명**: 자동화된 테스트 및 개발 도구

**목적**: 파이프라인 테스트를 위한 Job 자동 생성 및 리스너 상태 확인 도구 제공

**핵심 가치**: 
- 자동화된 테스트 환경
- 다양한 테스트 시나리오 지원
- 개발자 친화적 디버깅 도구
- 효율적인 개발 워크플로우

---

## 🎯 목적

### 문제 해결
- **수동 테스트의 한계**: 매번 수동으로 Job을 생성해야 함
- **테스트 데이터 관리**: 테스트용 데이터를 일관되게 관리하기 어려움
- **디버깅 어려움**: 리스너 상태를 확인하기 어려움
- **개발 효율성**: 반복적인 작업으로 인한 시간 낭비

### 해결 방안
- **Background Job Creator**: 테스트용 Job 자동 생성
- **리스너 상태 확인 도구**: 리스너 동작 확인 및 디버깅
- **다양한 모드 지원**: 완료 대기, 주기적 생성 등
- **자동화된 워크플로우**: 개발 효율성 향상

---

## ✨ 주요 특징

### 1. Background Job Creator
- **전체 파이프라인 테스트**: `background_pipeline_with_text_generation.py`
- **YE 파트 테스트**: `background_ye_pipeline_test.py`
- **완료 대기 모드**: 이전 Job 완료 후 다음 Job 생성
- **주기적 생성 모드**: 일정 간격으로 Job 생성

### 2. 리스너 상태 확인 도구
- **리스너 상태 확인**: `test_listener_status.py`
- **YE 파트 트리거 테스트**: `test_ye_img_gen_trigger.py`
- **실시간 모니터링**: 리스너 동작 실시간 확인

---

## 🏗️ 아키텍처

### 테스트 도구 구조

```
[Background Job Creator]
Job 자동 생성
  ↓
[파이프라인 실행]
자동으로 파이프라인 진행
  ↓
[리스너 상태 확인]
리스너 동작 확인
  ↓
[결과 분석]
테스트 결과 분석
```

---

## 💻 구현 코드

### 1. Job Pipeline 모니터링 상세

**파일**: `scripts/monitor_job_pipeline.py`

```python
def monitor_job(job_id: str, max_iterations: int = 120, check_interval: int = 10):
    """
    Job의 진행 상황을 모니터링합니다.
    
    Args:
        job_id: 모니터링할 Job ID
        max_iterations: 최대 반복 횟수 (기본값: 120, 약 20분)
        check_interval: 확인 간격 (초, 기본값: 10초)
    """
    # Job 및 Variants 상태 확인
    # Planner 이미지 경로 조회
    # 최종 오버레이 이미지 경로 조회
    # GPT 광고문구 조회
    # Instagram Feed 정보 조회
    # 리스너 및 트리거 상태 확인
```

**사용 예시**:
```bash
# Job 모니터링
python scripts/monitor_job_pipeline.py <job_id> [max_iterations] [check_interval]

# 예시
python scripts/monitor_job_pipeline.py cc6b3fb9-ef53-42c2-a811-fbd10d43e6f2
```

**주요 기능**:
- 실시간 Job 및 Variants 상태 모니터링
- Planner 이미지 절대 경로 출력
- 최종 오버레이 이미지 절대 경로 출력
- GPT 광고문구 출력
- Instagram Feed 글 및 해시태그 출력
- 리스너 및 트리거 상태 확인 안내

---

### 2. 파이프라인 결과 분석

**파일**: `scripts/analyze_pipeline_results.py`

```python
def analyze_job(job_id: str, db: SessionLocal):
    """Job ID를 기반으로 결과 분석"""
    # Job 정보
    # Variants 정보
    # Overlay Layout 정보
    # Planner Proposal 정보
    # 평가 결과 (OCR, Readability, IoU, VLM Judge)
    # 최종 이미지 경로
```

**사용 예시**:
```bash
# Job 분석
python scripts/analyze_pipeline_results.py --job-id <job_id>

# Tenant 분석 (최근 Job들)
python scripts/analyze_pipeline_results.py --tenant-id <tenant_id> --limit 5
```

**주요 기능**:
- Job 및 Variants 상세 정보 분석
- Overlay Layout 및 텍스트 분석
- Planner Proposal 선택 분석
- 평가 결과 상세 분석
- 최종 이미지 경로 확인

---

### 3. 전체 파이프라인 테스트

**파일**: `scripts/background_pipeline_with_text_generation.py`

```python
import argparse
import time
import uuid
from database import SessionLocal
from sqlalchemy import text

def create_job_with_variants(
    tenant_id: str,
    variants_count: int = 3,
    image_paths: Optional[List[str]] = None
) -> str:
    """Job과 Variants 생성"""
    db = SessionLocal()
    try:
        # 1. Job 생성
        job_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step,
                created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, 'queued', 'img_gen',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id
        })
        
        # 2. Job Inputs 생성
        job_input_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO job_inputs (
                job_input_id, job_id, desc_kor, tone_style_id,
                created_at, updated_at
            ) VALUES (
                :job_input_id, :job_id, :desc_kor, :tone_style_id,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_input_id": job_input_id,
            "job_id": job_id,
            "desc_kor": "테스트용 제품 설명",
            "tone_style_id": get_default_tone_style_id(db)
        })
        
        # 3. Image Asset 생성
        image_asset_id = uuid.uuid4()
        image_url = upload_image(image_paths[0] if image_paths else get_default_image())
        db.execute(text("""
            INSERT INTO image_assets (
                image_asset_id, image_type, image_url,
                tenant_id, created_at, updated_at
            ) VALUES (
                :image_asset_id, 'generated', :image_url,
                :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "image_asset_id": image_asset_id,
            "image_url": image_url,
            "tenant_id": tenant_id
        })
        
        # 4. Job Variants 생성
        for i in range(variants_count):
            job_variants_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO jobs_variants (
                    job_variants_id, job_id, img_asset_id,
                    creation_order, status, current_step,
                    created_at, updated_at
                ) VALUES (
                    :job_variants_id, :job_id, :img_asset_id,
                    :creation_order, 'queued', 'img_gen',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "job_variants_id": job_variants_id,
                "job_id": job_id,
                "img_asset_id": image_asset_id,
                "creation_order": i + 1
            })
        
        db.commit()
        logger.info(f"✅ Job 생성 완료: job_id={job_id}, variants={variants_count}")
        return str(job_id)
        
    finally:
        db.close()

def check_job_completed(job_id: str) -> bool:
    """Job 완료 확인"""
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT status, current_step
            FROM jobs
            WHERE job_id = :job_id
        """), {"job_id": uuid.UUID(job_id)}).first()
        
        if not result:
            return False
        
        # instagram_feed_gen (done) 상태면 완료
        return result.status == 'done' and result.current_step == 'instagram_feed_gen'
    finally:
        db.close()

def main():
    parser = argparse.ArgumentParser(description="Background Job Creator")
    parser.add_argument("--tenant-id", default="pipeline_test_tenant_v2")
    parser.add_argument("--variants-count", type=int, default=3)
    parser.add_argument("--wait-for-completion", action="store_true")
    parser.add_argument("--create-interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    
    args = parser.parse_args()
    
    job_count = 0
    
    while True:
        # Job 생성
        job_id = create_job_with_variants(
            tenant_id=args.tenant_id,
            variants_count=args.variants_count
        )
        job_count += 1
        logger.info(f"📝 Job #{job_count} 생성: {job_id}")
        
        if args.once:
            break
        
        if args.wait_for_completion:
            # 완료 대기
            logger.info(f"⏳ Job 완료 대기 중: {job_id}")
            while not check_job_completed(job_id):
                time.sleep(10)
            logger.info(f"✅ Job 완료: {job_id}")
        else:
            # 주기적 생성
            time.sleep(args.create_interval)

if __name__ == "__main__":
    main()
```

**핵심 포인트**:
- **자동 Job 생성**: 필요한 모든 데이터 자동 생성
- **완료 대기 모드**: 이전 Job 완료 후 다음 Job 생성
- **주기적 생성 모드**: 일정 간격으로 Job 생성
- **한 번만 실행**: `--once` 옵션으로 한 번만 실행

---

### 2. YE 파트 테스트

**파일**: `scripts/background_ye_pipeline_test.py`

```python
def create_ye_job_with_variants(
    tenant_id: str,
    variants_count: int = 3,
    image_paths: Optional[List[str]] = None
) -> str:
    """YE 파트 테스트용 Job 생성 (user_img_input done 상태)"""
    db = SessionLocal()
    try:
        # 1. Job 생성 (user_img_input done 상태)
        job_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step,
                created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, 'done', 'user_img_input',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id
        })
        
        # 2. Image Asset 생성 (첫 번째 이미지만 사용)
        image_asset_id = uuid.uuid4()
        image_path = image_paths[0] if image_paths else get_default_image()
        image_url = upload_image(image_path)
        db.execute(text("""
            INSERT INTO image_assets (
                image_asset_id, image_type, image_url,
                tenant_id, created_at, updated_at
            ) VALUES (
                :image_asset_id, 'generated', :image_url,
                :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "image_asset_id": image_asset_id,
            "image_url": image_url,
            "tenant_id": tenant_id
        })
        
        # 3. Job Inputs 생성 (동일한 img_asset_id 사용)
        job_input_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO job_inputs (
                job_input_id, job_id, img_asset_id, desc_kor,
                created_at, updated_at
            ) VALUES (
                :job_input_id, :job_id, :img_asset_id, :desc_kor,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_input_id": job_input_id,
            "job_id": job_id,
            "img_asset_id": image_asset_id,
            "desc_kor": "YE 파트 테스트용 이미지"
        })
        
        # 4. Job Variants 생성 (모두 동일한 img_asset_id 사용)
        for i in range(variants_count):
            job_variants_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO jobs_variants (
                    job_variants_id, job_id, img_asset_id,
                    creation_order, status, current_step,
                    created_at, updated_at
                ) VALUES (
                    :job_variants_id, :job_id, :img_asset_id,
                    :creation_order, 'done', 'user_img_input',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "job_variants_id": job_variants_id,
                "job_id": job_id,
                "img_asset_id": image_asset_id,  # 모든 variants가 동일한 이미지 사용
                "creation_order": i + 1
            })
        
        db.commit()
        logger.info(f"✅ YE 파트 테스트용 Job 생성 완료: job_id={job_id}, variants={variants_count}")
        return str(job_id)
        
    finally:
        db.close()
```

**핵심 포인트**:
- **user_img_input done 상태**: YE 파트가 시작할 수 있는 상태로 생성
- **동일한 이미지 사용**: 모든 variants가 같은 이미지와 img_asset_id 사용
- **트리거 발동 안 함**: 스크립트는 트리거를 발동하지 않음 (YE 파트가 실제로 img_gen 완료할 때까지 대기)

---

### 3. 리스너 상태 확인 도구

**파일**: `test/test_listener_status.py`

```python
import asyncio
import asyncpg
from config import DATABASE_URL

async def check_listener_status():
    """리스너 상태 확인"""
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    
    conn = await asyncpg.connect(asyncpg_url)
    try:
        # 1. FastAPI 서버 상태 확인
        print("1. FastAPI 서버 상태 확인...")
        # (HTTP 요청으로 확인)
        
        # 2. 리스너 설정 확인
        print("2. 리스너 설정 확인...")
        # (환경 변수 확인)
        
        # 3. PostgreSQL 트리거 확인
        print("3. PostgreSQL 트리거 확인...")
        trigger_exists = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'job_variant_state_change_trigger'
            )
        """)
        print(f"   트리거 존재: {trigger_exists}")
        
        # 4. 트리거 함수 확인
        function_exists = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM pg_proc
                WHERE proname = 'notify_job_variant_state_change'
            )
        """)
        print(f"   트리거 함수 존재: {function_exists}")
        
        # 5. 실제 트리거 테스트 (선택적)
        test_trigger = input("실제 트리거 테스트를 실행하시겠습니까? (y/n): ")
        if test_trigger.lower() == 'y':
            await test_trigger_execution(conn)
        
    finally:
        await conn.close()

async def test_trigger_execution(conn):
    """실제 트리거 테스트"""
    print("4. 실제 트리거 테스트...")
    
    # 테스트용 variant 생성
    job_variants_id = await conn.fetchval("""
        INSERT INTO jobs_variants (
            job_variants_id, job_id, img_asset_id,
            creation_order, status, current_step
        ) VALUES (
            gen_random_uuid(), gen_random_uuid(), gen_random_uuid(),
            1, 'done', 'img_gen'
        )
        RETURNING job_variants_id
    """)
    
    print(f"   테스트 variant 생성: {job_variants_id}")
    print("   상태 업데이트 중...")
    
    # 상태 업데이트 (트리거 발동)
    await conn.execute("""
        UPDATE jobs_variants
        SET status = 'done',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = $1
    """, job_variants_id)
    
    print("   ✅ 트리거 발동 완료")
    print("   리스너 로그를 확인하여 이벤트 수신 여부를 확인하세요")

if __name__ == "__main__":
    asyncio.run(check_listener_status())
```

**핵심 포인트**:
- **FastAPI 서버 상태**: 서버가 실행 중인지 확인
- **리스너 설정**: 환경 변수 확인
- **PostgreSQL 트리거**: 트리거 및 함수 존재 확인
- **실제 테스트**: 실제 트리거 실행 테스트

---

### 4. YE 파트 트리거 테스트

**파일**: `test/test_ye_img_gen_trigger.py`

```python
from database import SessionLocal
from sqlalchemy import text
import time

def test_ye_img_gen_trigger(job_variants_id: str):
    """YE 파트 img_gen 완료 시뮬레이션 및 트리거 테스트"""
    db = SessionLocal()
    try:
        # 1. 현재 상태 확인
        current = db.execute(text("""
            SELECT status, current_step
            FROM jobs_variants
            WHERE job_variants_id = :job_variants_id
        """), {"job_variants_id": job_variants_id}).first()
        
        print(f"현재 상태: {current.status}, {current.current_step}")
        
        # 2. img_gen 완료 상태로 업데이트 (트리거 발동)
        db.execute(text("""
            UPDATE jobs_variants
            SET status = 'done',
                current_step = 'img_gen',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_variants_id = :job_variants_id
        """), {"job_variants_id": job_variants_id})
        db.commit()
        
        print("✅ img_gen 완료 상태로 업데이트 완료")
        print("⏳ 10초 대기 중... (리스너가 트리거를 처리할 시간)")
        
        # 3. 10초 대기
        time.sleep(10)
        
        # 4. 상태 확인 (vlm_analyze로 변경되었는지 확인)
        updated = db.execute(text("""
            SELECT status, current_step
            FROM jobs_variants
            WHERE job_variants_id = :job_variants_id
        """), {"job_variants_id": job_variants_id}).first()
        
        print(f"업데이트 후 상태: {updated.status}, {updated.current_step}")
        
        if updated.current_step == 'vlm_analyze':
            print("✅ 트리거가 정상적으로 작동했습니다!")
        else:
            print("⚠️ 트리거가 작동하지 않았습니다. 리스너 로그를 확인하세요.")
        
    finally:
        db.close()

if __name__ == "__main__":
    import sys
    job_variants_id = sys.argv[1] if len(sys.argv) > 1 else input("job_variants_id를 입력하세요: ")
    test_ye_img_gen_trigger(job_variants_id)
```

**핵심 포인트**:
- **상태 시뮬레이션**: img_gen 완료 상태로 업데이트
- **트리거 테스트**: 실제 트리거가 발동하는지 확인
- **결과 확인**: 다음 단계로 진행되었는지 확인

---

## 📊 사용 예시

### 예시 1: 전체 파이프라인 테스트

```bash
# 한 번만 실행
docker exec feedlyai-work-yh python3 scripts/background_pipeline_with_text_generation.py --once

# 완료 대기 모드
docker exec feedlyai-work-yh python3 scripts/background_pipeline_with_text_generation.py \
  --tenant-id pipeline_test_tenant_v2 \
  --wait-for-completion

# 주기적 생성 (60초 간격)
docker exec feedlyai-work-yh python3 scripts/background_pipeline_with_text_generation.py \
  --tenant-id pipeline_test_tenant_v2 \
  --create-interval 60
```

---

### 예시 2: YE 파트 테스트

```bash
# 한 번만 실행
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py --once

# 완료 대기 모드
docker exec feedlyai-work-yh python3 scripts/background_ye_pipeline_test.py \
  --tenant-id ye_test_tenant \
  --wait-for-completion
```

---

### 예시 3: 리스너 상태 확인

```bash
# 리스너 상태 확인
docker exec feedlyai-work-yh python3 test/test_listener_status.py

# YE 파트 트리거 테스트
docker exec feedlyai-work-yh python3 test/test_ye_img_gen_trigger.py <job_variants_id>
```

---

## 🔧 트러블슈팅

### 문제 1: Job이 생성되지 않음

**증상**: 스크립트 실행 시 오류 발생

**확인 사항**:
1. 데이터베이스 연결 확인
2. 필요한 테이블 존재 확인
3. 이미지 파일 경로 확인

**해결 방법**:
```bash
# 데이터베이스 연결 테스트
docker exec feedlyai-work-yh python3 -c "
from database import SessionLocal
db = SessionLocal()
print('✅ 데이터베이스 연결 성공')
db.close()
"
```

---

### 문제 2: 리스너가 트리거를 감지하지 못함

**증상**: 상태를 업데이트해도 다음 단계로 진행되지 않음

**확인 사항**:
1. 리스너가 실행 중인지 확인
2. PostgreSQL 트리거가 존재하는지 확인
3. 로그 확인

**해결 방법**:
```bash
# 리스너 상태 확인
docker exec feedlyai-work-yh python3 test/test_listener_status.py

# 리스너 로그 확인
docker logs feedlyai-work-yh | grep -i "listener\|trigger"
```

---

## 🎯 주요 포인트

1. **자동화된 테스트**: 수동 작업 없이 테스트 환경 구축
2. **다양한 모드**: 완료 대기, 주기적 생성 등 다양한 모드 지원
3. **개발자 친화적**: 간단한 명령어로 테스트 실행
4. **디버깅 도구**: 리스너 상태 확인 및 트리거 테스트 도구

---

## 📚 관련 문서

- `DOCS_YE_PART_PIPELINE_TEST.md`: YE 파트 테스트 가이드
- `DOCS_JOB_STATE_LISTENER.md`: 리스너 사용 가이드
- `DOCS_BACKGROUND_EXECUTION.md`: 백그라운드 실행 가이드

---

**작성일**: 2025-12-02  
**작성자**: LEEYH205  
**버전**: 1.0.0


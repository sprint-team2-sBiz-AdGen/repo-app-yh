"""Job State Listener 팀원 테스트 스크립트
간단하게 리스너 동작을 테스트할 수 있는 스크립트
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 팀원용 Job State Listener 테스트 스크립트
# version: 1.0.0
########################################################

import sys
import os
import uuid
import time
from pathlib import Path
from PIL import Image

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
from utils import save_asset
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def print_section(title):
    """섹션 제목 출력"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)

def create_test_job(db, tenant_id: str = "team_test_tenant") -> dict:
    """테스트용 job 생성"""
    print_section("1. 테스트용 Job 생성")
    
    # Tenant 생성
    db.execute(text("""
        INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
        VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id) DO NOTHING
    """), {
        "tenant_id": tenant_id,
        "display_name": f"Team Test Tenant"
    })
    print(f"✓ Tenant 생성/확인: {tenant_id}")
    
    # 이미지 파일 찾기
    default_image_path = project_root / "pipeline_test" / "pipeline_test_image9.jpg"
    if not default_image_path.exists():
        # 다른 이미지 파일 시도
        pipeline_dir = project_root / "pipeline_test"
        image_files = list(pipeline_dir.glob("*.jpg")) + list(pipeline_dir.glob("*.png"))
        if image_files:
            default_image_path = image_files[0]
        else:
            print("⚠ 이미지 파일을 찾을 수 없습니다. 더미 데이터로 진행합니다.")
            default_image_path = None
    
    # Image Asset 생성
    if default_image_path and default_image_path.exists():
        image = Image.open(default_image_path)
        asset_meta = save_asset(tenant_id, "team_test", image, default_image_path.suffix)
        asset_url = asset_meta["url"]
        print(f"✓ 이미지 저장: {asset_url}")
        
        # image_assets 확인/생성
        existing = db.execute(
            text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
            {"url": asset_url, "tenant_id": tenant_id}
        ).first()
        
        if existing:
            image_asset_id = existing[0]
        else:
            image_asset_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO image_assets (
                    image_asset_id, image_type, image_url, width, height, tenant_id, created_at, updated_at
                ) VALUES (
                    :image_asset_id, 'generated', :asset_url, :width, :height, :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "image_asset_id": image_asset_id,
                "asset_url": asset_url,
                "width": image.width,
                "height": image.height,
                "tenant_id": tenant_id
            })
            db.commit()
    else:
        # 더미 데이터
        image_asset_id = uuid.uuid4()
        asset_url = "/assets/test.jpg"
        db.execute(text("""
            INSERT INTO image_assets (
                image_asset_id, image_type, image_url, tenant_id, created_at, updated_at
            ) VALUES (
                :image_asset_id, 'generated', :asset_url, :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT DO NOTHING
        """), {
            "image_asset_id": image_asset_id,
            "asset_url": asset_url,
            "tenant_id": tenant_id
        })
        print(f"⚠ 더미 이미지 URL 사용: {asset_url}")
    
    # Job 생성 (img_gen 완료 상태)
    job_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO jobs (
            job_id, tenant_id, status, current_step, created_at, updated_at
        ) VALUES (
            :job_id, :tenant_id, 'done', 'img_gen', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {
        "job_id": job_id,
        "tenant_id": tenant_id
    })
    
    # Job Input 생성
    db.execute(text("""
        INSERT INTO job_inputs (
            job_id, img_asset_id, desc_eng, created_at, updated_at
        ) VALUES (
            :job_id, :image_asset_id, :desc_eng, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {
        "job_id": job_id,
        "image_asset_id": image_asset_id,
        "desc_eng": "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    })
    
    db.commit()
    
    print(f"✓ Job 생성 완료")
    print(f"  - Job ID: {job_id}")
    print(f"  - Status: done")
    print(f"  - Current Step: img_gen")
    
    return {
        "job_id": str(job_id),
        "tenant_id": tenant_id,
        "status": "done",
        "current_step": "img_gen"
    }

def check_listener_status():
    """리스너 상태 확인"""
    print_section("2. 리스너 상태 확인")
    
    try:
        from config import ENABLE_JOB_STATE_LISTENER
        if ENABLE_JOB_STATE_LISTENER:
            print("✓ 리스너 활성화됨")
        else:
            print("⚠ 리스너 비활성화됨 (ENABLE_JOB_STATE_LISTENER=false)")
            print("  리스너를 활성화하려면 환경 변수를 설정하세요.")
    except Exception as e:
        print(f"⚠ 설정 확인 실패: {e}")
    
    print("\n💡 로그 확인 명령어:")
    print("  docker logs feedlyai-work-yh --tail 50 | grep -i 'listener\\|trigger'")

def trigger_pipeline(db, job_id: str):
    """파이프라인 트리거 발동"""
    print_section("3. 파이프라인 트리거 발동")
    
    print("Job 상태를 변경하여 트리거를 발동합니다...")
    print("  (running → done으로 변경)")
    
    # running으로 변경
    db.execute(text("""
        UPDATE jobs 
        SET status = 'running', 
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    db.commit()
    print("✓ 상태를 'running'으로 변경")
    
    time.sleep(1)
    
    # done으로 변경하여 트리거 발동
    db.execute(text("""
        UPDATE jobs 
        SET status = 'done', 
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    db.commit()
    print("✓ 상태를 'done'으로 변경 (트리거 발동!)")
    
    print("\n💡 예상 동작:")
    print("  1. PostgreSQL 트리거가 NOTIFY 이벤트 발행")
    print("  2. 리스너가 이벤트 수신")
    print("  3. LLaVA Stage 1 API 자동 호출")
    print("  4. Job 상태가 'vlm_analyze'로 변경")

def verify_result(db, job_id: str, wait_seconds: int = 10):
    """결과 확인"""
    print_section("4. 결과 확인")
    
    print(f"{wait_seconds}초 대기 중... (파이프라인 실행 시간)")
    time.sleep(wait_seconds)
    
    result = db.execute(text("""
        SELECT job_id, tenant_id, status, current_step, updated_at
        FROM jobs
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    
    row = result.fetchone()
    if row:
        print(f"\n📊 Job 상태:")
        print(f"  - Job ID: {row[0]}")
        print(f"  - Tenant ID: {row[1]}")
        print(f"  - Status: {row[2]}")
        print(f"  - Current Step: {row[3]}")
        print(f"  - Updated At: {row[4]}")
        
        if row[3] == 'vlm_analyze':
            print("\n✅ 성공! 자동 파이프라인 실행됨")
            print("   current_step이 'vlm_analyze'로 변경되었습니다.")
            print("   LLaVA Stage 1이 자동으로 실행되었습니다.")
        elif row[2] == 'running' and row[3] == 'vlm_analyze':
            print("\n⏳ 진행 중... LLaVA Stage 1 실행 중")
            print("   조금 더 기다린 후 다시 확인하세요.")
        else:
            print(f"\n⚠ 자동 실행 대기 중... (현재: {row[3]})")
            print("   로그를 확인하여 리스너가 정상 작동하는지 확인하세요.")
            print("\n💡 로그 확인:")
            print("   docker logs feedlyai-work-yh --tail 50 | grep -i 'listener\\|trigger\\|pipeline'")
    else:
        print(f"❌ Job을 찾을 수 없습니다: {job_id}")

def main():
    """메인 테스트 함수"""
    print("\n" + "=" * 60)
    print("Job State Listener 팀원 테스트")
    print("=" * 60)
    print("\n이 스크립트는 다음을 수행합니다:")
    print("1. 테스트용 job 생성")
    print("2. 리스너 상태 확인")
    print("3. 파이프라인 트리거 발동")
    print("4. 자동 실행 결과 확인")
    
    db = SessionLocal()
    try:
        # 1. 테스트용 job 생성
        job_info = create_test_job(db, tenant_id="team_test_tenant")
        job_id = job_info["job_id"]
        
        # 2. 리스너 상태 확인
        check_listener_status()
        
        # 3. 트리거 발동
        trigger_pipeline(db, job_id)
        
        # 4. 결과 확인
        verify_result(db, job_id, wait_seconds=10)
        
        print_section("테스트 완료")
        print("\n📝 다음 단계:")
        print("1. 로그에서 '[LISTENER] Job 상태 변화 감지' 메시지 확인")
        print("2. 로그에서 '[TRIGGER] 파이프라인 단계 트리거' 메시지 확인")
        print("3. LLaVA Stage 1 API 호출 확인")
        print("\n💡 로그 확인 명령어:")
        print("   docker logs feedlyai-work-yh --tail 100 | grep -i 'listener\\|trigger\\|pipeline'")
        
    except Exception as e:
        logger.error(f"테스트 중 오류: {e}", exc_info=True)
        db.rollback()
        print(f"\n❌ 오류 발생: {e}")
        print("\n💡 문제 해결:")
        print("1. Docker 컨테이너가 실행 중인지 확인")
        print("2. 데이터베이스 연결 확인")
        print("3. 로그 확인: docker logs feedlyai-work-yh")
    finally:
        db.close()

if __name__ == "__main__":
    main()


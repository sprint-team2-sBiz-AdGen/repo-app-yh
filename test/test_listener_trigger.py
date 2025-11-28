"""Job State Listener 트리거 테스트
PostgreSQL LISTEN/NOTIFY를 통한 자동 파이프라인 실행 테스트
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: Job State Listener 트리거 테스트
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

from database import SessionLocal, Job, JobInput, ImageAsset
from sqlalchemy import text
from utils import save_asset, abs_from_url
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_job(db, tenant_id: str = "pipeline_test_tenant", image_path: str = None) -> str:
    """테스트용 job 생성"""
    job_id = uuid.uuid4()
    
    # Tenant 생성 (없으면)
    db.execute(text("""
        INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
        VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id) DO NOTHING
    """), {
        "tenant_id": tenant_id,
        "display_name": f"Test Tenant ({tenant_id})"
    })
    
    # 이미지 파일이 제공되면 실제로 저장
    if image_path and os.path.exists(image_path):
        image = Image.open(image_path)
        asset_meta = save_asset(tenant_id, "listener_test", image, ".png")
        asset_url = asset_meta["url"]
        logger.info(f"이미지 저장 완료: {asset_url}")
    else:
        # 기본 테스트 이미지 경로 시도
        default_image_path = project_root / "pipeline_test" / "pipeline_test_image9.jpg"
        if default_image_path.exists():
            image = Image.open(default_image_path)
            asset_meta = save_asset(tenant_id, "listener_test", image, ".jpg")
            asset_url = asset_meta["url"]
            logger.info(f"기본 이미지 사용: {asset_url}")
        else:
            # 이미지가 없으면 더미 URL 사용 (API 호출은 실패할 수 있음)
            asset_url = "/assets/test.jpg"
            logger.warning(f"이미지 파일이 없어 더미 URL 사용: {asset_url}")
    
    # image_assets 확인/생성
    existing = db.execute(
        text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
        {"url": asset_url, "tenant_id": tenant_id}
    ).first()
    
    if existing:
        image_asset_id = existing[0]
        logger.info(f"기존 image_asset 레코드 발견: {image_asset_id}")
    else:
        image_asset_id = uuid.uuid4()
        image_width = asset_meta.get("width", 1920) if 'asset_meta' in locals() else 1920
        image_height = asset_meta.get("height", 1080) if 'asset_meta' in locals() else 1080
        db.execute(text("""
            INSERT INTO image_assets (
                image_asset_id, image_type, image_url, width, height, tenant_id, created_at, updated_at
            ) VALUES (
                :image_asset_id, 'generated', :asset_url, :width, :height, :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "image_asset_id": image_asset_id,
            "asset_url": asset_url,
            "width": image_width,
            "height": image_height,
            "tenant_id": tenant_id
        })
        db.commit()
        logger.info(f"image_asset 레코드 생성 완료: {image_asset_id}")
    
    # Job 생성 (img_gen 단계, done 상태)
    db.execute(text("""
        INSERT INTO jobs (
            job_id, tenant_id, status, current_step, created_at, updated_at
        ) VALUES (
            :job_id, :tenant_id, 'done', 'img_gen', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        ON CONFLICT (job_id) DO UPDATE
        SET status = 'done', current_step = 'img_gen', updated_at = CURRENT_TIMESTAMP
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
        ON CONFLICT (job_id) DO UPDATE
        SET img_asset_id = :image_asset_id, desc_eng = :desc_eng, updated_at = CURRENT_TIMESTAMP
    """), {
        "job_id": job_id,
        "image_asset_id": image_asset_id,
        "desc_eng": "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    })
    
    db.commit()
    logger.info(f"✓ 테스트 job 생성: job_id={job_id}, tenant_id={tenant_id}")
    return str(job_id)

def trigger_next_stage(db, job_id: str):
    """다음 단계 트리거 (job 상태 업데이트)"""
    # 이미 done 상태이므로, 다시 업데이트하여 트리거 발동
    # (실제로는 img_gen -> done으로 변경되면 트리거가 발동됨)
    db.execute(text("""
        UPDATE jobs 
        SET status = 'done', 
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    db.commit()
    logger.info(f"✓ Job 상태 업데이트 (트리거 발동): job_id={job_id}")

def check_job_status(db, job_id: str):
    """Job 상태 확인"""
    result = db.execute(text("""
        SELECT job_id, tenant_id, status, current_step, updated_at
        FROM jobs
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    
    row = result.fetchone()
    if row:
        logger.info(f"Job 상태: job_id={row[0]}, status={row[2]}, current_step={row[3]}")
        return {
            "job_id": str(row[0]),
            "tenant_id": row[1],
            "status": row[2],
            "current_step": row[3],
            "updated_at": row[4]
        }
    return None

def main():
    """메인 테스트 함수"""
    print("\n" + "=" * 60)
    print("Job State Listener 트리거 테스트")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # 1. 테스트용 job 생성
        print("\n[1/3] 테스트용 job 생성 중...")
        job_id = create_test_job(db, tenant_id="pipeline_test_tenant")
        print(f"  Job ID: {job_id}")
        
        # 2. 초기 상태 확인
        print("\n[2/3] 초기 job 상태 확인...")
        initial_status = check_job_status(db, job_id)
        print(f"  Status: {initial_status['status']}, Current Step: {initial_status['current_step']}")
        
        # 3. 트리거 발동 (상태 업데이트)
        print("\n[3/3] Job 상태 업데이트하여 트리거 발동...")
        print("  (이미 done 상태이므로, updated_at만 변경하여 트리거 발동)")
        
        # 실제로는 current_step이나 status가 변경되어야 트리거가 발동됨
        # 하지만 이미 'img_gen', 'done' 상태이므로, 
        # 다른 상태로 변경 후 다시 'img_gen', 'done'으로 변경
        db.execute(text("""
            UPDATE jobs 
            SET status = 'running', 
                current_step = 'img_gen',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = :job_id
        """), {"job_id": job_id})
        db.commit()
        time.sleep(1)  # 1초 대기
        
        # 다시 done으로 변경하여 트리거 발동
        trigger_next_stage(db, job_id)
        
        print("\n" + "=" * 60)
        print("트리거 발동 완료!")
        print("=" * 60)
        print("\n다음 단계:")
        print("1. Docker 로그에서 'Job 상태 변화 감지' 메시지 확인")
        print("2. '파이프라인 단계 트리거' 메시지 확인")
        print("3. LLaVA Stage 1 API가 자동으로 호출되는지 확인")
        print("\n로그 확인 명령어:")
        print("  docker logs feedlyai-work-yh --tail 50 | grep -i 'listener\\|trigger\\|pipeline\\|job 상태'")
        
        # 4. 잠시 대기 후 상태 확인
        print("\n[4/4] 5초 대기 후 job 상태 재확인...")
        time.sleep(5)
        final_status = check_job_status(db, job_id)
        print(f"  Status: {final_status['status']}, Current Step: {final_status['current_step']}")
        
        if final_status['current_step'] == 'vlm_analyze':
            print("\n✓ 자동 파이프라인 실행 성공! (current_step이 'vlm_analyze'로 변경됨)")
        else:
            print(f"\n⚠ 자동 파이프라인 실행 대기 중... (현재: {final_status['current_step']})")
            print("  로그를 확인하여 리스너가 정상 작동하는지 확인하세요.")
        
    except Exception as e:
        logger.error(f"테스트 중 오류: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()


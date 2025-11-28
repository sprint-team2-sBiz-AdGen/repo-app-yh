"""백그라운드 리스너 테스트
백그라운드에서 실행 중인 리스너가 img_gen 완료 상태의 job을 감지하고
파이프라인을 자동으로 실행하는지 테스트
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 백그라운드 리스너 테스트
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
from utils import save_asset
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_img_gen_job(tenant_id: str = "background_test_tenant") -> str:
    """img_gen 완료 상태의 job 생성"""
    print("\n" + "=" * 60)
    print("img_gen 완료 상태 Job 생성")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Tenant 생성
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"Background Test Tenant ({tenant_id})"
        })
        print(f"✓ Tenant 생성/확인: {tenant_id}")
        
        # 이미지 파일 찾기
        default_image_path = project_root / "pipeline_test" / "pipeline_test_image9.jpg"
        if not default_image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {default_image_path}")
        
        image = Image.open(default_image_path)
        
        # 이미지 저장
        asset_meta = save_asset(tenant_id, "background_test", image, ".jpg")
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
                "width": image.size[0],
                "height": image.size[1],
                "tenant_id": tenant_id
            })
            db.commit()
        
        # 텍스트 파일 읽기
        default_text_path = project_root / "pipeline_test" / "pipeline_test_txt_kor1.txt"
        if default_text_path.exists():
            with open(default_text_path, 'r', encoding='utf-8') as f:
                ad_copy_text = f.read().strip().strip('"').strip("'")
        else:
            ad_copy_text = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
        
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
        
        # JobInput 생성
        db.execute(text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, desc_eng, created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :desc_eng, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "img_asset_id": image_asset_id,
            "desc_eng": ad_copy_text
        })
        
        db.commit()
        
        print(f"✓ Job 생성 완료")
        print(f"  - Job ID: {job_id}")
        print(f"  - Status: done")
        print(f"  - Current Step: img_gen")
        
        return str(job_id)
        
    except Exception as e:
        db.rollback()
        print(f"❌ 오류 발생: {e}")
        raise
    finally:
        db.close()

def monitor_job_progress(job_id: str, timeout: int = 300):
    """Job 진행 상황 모니터링"""
    print("\n" + "=" * 60)
    print("파이프라인 진행 상황 모니터링")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        start_time = time.time()
        last_step = None
        
        while time.time() - start_time < timeout:
            result = db.execute(
                text("SELECT status, current_step, updated_at FROM jobs WHERE job_id = :job_id"),
                {"job_id": job_id}
            ).first()
            
            if not result:
                print(f"❌ Job을 찾을 수 없습니다: {job_id}")
                return
            
            status, current_step, updated_at = result
            
            # 단계가 변경되었을 때만 출력
            if current_step != last_step:
                elapsed = int(time.time() - start_time)
                print(f"[{elapsed:3d}초] {current_step} - Status: {status}")
                last_step = current_step
            
            # 파이프라인 완료 확인
            if current_step == 'iou_eval' and status == 'done':
                elapsed = int(time.time() - start_time)
                print(f"\n✅ 파이프라인 완료! (총 {elapsed}초 소요)")
                return
            
            # 실패 확인
            if status == 'failed':
                elapsed = int(time.time() - start_time)
                print(f"\n❌ 파이프라인 실패: {current_step} 단계에서 실패 (총 {elapsed}초 소요)")
                return
            
            time.sleep(2)  # 2초마다 확인
        
        # 타임아웃
        elapsed = int(time.time() - start_time)
        print(f"\n⚠ 타임아웃: {timeout}초 내에 파이프라인이 완료되지 않았습니다.")
        print(f"  현재 상태: {current_step}, {status}")
        
    finally:
        db.close()

def check_final_status(job_id: str):
    """최종 Job 상태 확인"""
    print("\n" + "=" * 60)
    print("최종 Job 상태 확인")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        result = db.execute(
            text("SELECT job_id, status, current_step, updated_at FROM jobs WHERE job_id = :job_id"),
            {"job_id": job_id}
        ).first()
        
        if result:
            job_id, status, current_step, updated_at = result
            print(f"  Job ID: {job_id}")
            print(f"  Status: {status}")
            print(f"  Current Step: {current_step}")
            print(f"  Updated At: {updated_at}")
        else:
            print(f"❌ Job을 찾을 수 없습니다: {job_id}")
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("백그라운드 리스너 테스트")
    print("=" * 60)
    print("\n이 테스트는 다음을 수행합니다:")
    print("1. img_gen 완료 상태의 job 생성")
    print("2. 백그라운드 리스너가 자동으로 감지하여 파이프라인 실행")
    print("3. 파이프라인 진행 상황 모니터링")
    print("4. 최종 결과 확인")
    
    try:
        # Job 생성
        job_id = create_img_gen_job()
        
        # 트리거 발동을 위해 상태를 다시 업데이트 (NOTIFY 이벤트 발행)
        print("\n" + "=" * 60)
        print("트리거 발동 (상태 업데이트)")
        print("=" * 60)
        
        db = SessionLocal()
        try:
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
            print("  2. 백그라운드 리스너가 이벤트 수신")
            print("  3. LLaVA Stage 1 API 자동 호출")
            print("  4. 이후 단계들이 순차적으로 자동 실행")
        finally:
            db.close()
        
        # 진행 상황 모니터링
        monitor_job_progress(job_id, timeout=10*60)
        
        # 최종 상태 확인
        check_final_status(job_id)
        
        print("\n" + "=" * 60)
        print("✅ 테스트 완료")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


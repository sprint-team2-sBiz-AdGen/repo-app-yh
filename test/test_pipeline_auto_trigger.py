"""전체 파이프라인 자동 트리거 테스트
img_gen 단계부터 트리거를 통해 전체 파이프라인이 자동으로 실행되는지 확인
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 전체 파이프라인 자동 트리거 테스트
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

def create_img_gen_job(db, tenant_id: str = "pipeline_auto_test_tenant", image_path: str = None, text_path: str = None) -> dict:
    """img_gen 완료 상태의 job 생성"""
    print("\n" + "=" * 60)
    print("img_gen 완료 상태 Job 생성")
    print("=" * 60)
    
    # Tenant 생성
    db.execute(text("""
        INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
        VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (tenant_id) DO NOTHING
    """), {
        "tenant_id": tenant_id,
        "display_name": f"Pipeline Auto Test Tenant ({tenant_id})"
    })
    print(f"✓ Tenant 생성/확인: {tenant_id}")
    
    # 이미지 파일 찾기
    if image_path and os.path.exists(image_path):
        image = Image.open(image_path)
    else:
        default_image_path = project_root / "pipeline_test" / "pipeline_test_image9.jpg"
        if default_image_path.exists():
            image = Image.open(default_image_path)
        else:
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {default_image_path}")
    
    # 이미지 저장
    asset_meta = save_asset(tenant_id, "auto_test", image, ".jpg")
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
    if text_path and os.path.exists(text_path):
        with open(text_path, 'r', encoding='utf-8') as f:
            ad_copy_text = f.read().strip().strip('"').strip("'")
    else:
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
    
    # Job Input 생성
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
    
    return {
        "job_id": str(job_id),
        "tenant_id": tenant_id
    }

def check_job_status(db, job_id: str):
    """Job 상태 확인"""
    result = db.execute(text("""
        SELECT job_id, tenant_id, status, current_step, updated_at
        FROM jobs
        WHERE job_id = :job_id
    """), {"job_id": job_id})
    
    row = result.fetchone()
    if row:
        return {
            "job_id": str(row[0]),
            "tenant_id": row[1],
            "status": row[2],
            "current_step": row[3],
            "updated_at": row[4]
        }
    return None

def trigger_pipeline(db, job_id: str):
    """파이프라인 트리거 발동 (img_gen done 상태로 업데이트)"""
    print("\n" + "=" * 60)
    print("파이프라인 트리거 발동")
    print("=" * 60)
    
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
    print("  4. 이후 단계들이 순차적으로 자동 실행")

def monitor_pipeline_progress(db, job_id: str, max_wait_seconds: int = 300, check_interval: int = 5):
    """파이프라인 진행 상황 모니터링"""
    print("\n" + "=" * 60)
    print("파이프라인 진행 상황 모니터링")
    print("=" * 60)
    
    expected_steps = [
        'img_gen',
        'vlm_analyze',
        'yolo_detect',
        'planner',
        'overlay',
        'vlm_judge',
        'ocr_eval',
        'readability_eval',
        'iou_eval'
    ]
    
    start_time = time.time()
    last_step = None
    
    while time.time() - start_time < max_wait_seconds:
        status = check_job_status(db, job_id)
        if not status:
            print("❌ Job을 찾을 수 없습니다.")
            return False
        
        current_step = status['current_step']
        current_status = status['status']
        
        # 단계가 변경되었으면 출력
        if current_step != last_step:
            step_index = expected_steps.index(current_step) if current_step in expected_steps else -1
            step_name = {
                'img_gen': '이미지 생성',
                'vlm_analyze': 'LLaVA Stage 1',
                'yolo_detect': 'YOLO',
                'planner': 'Planner',
                'overlay': 'Overlay',
                'vlm_judge': 'LLaVA Stage 2',
                'ocr_eval': 'OCR 평가',
                'readability_eval': '가독성 평가',
                'iou_eval': 'IoU 평가'
            }.get(current_step, current_step)
            
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed:3d}초] {step_name} ({current_step}) - Status: {current_status}")
            last_step = current_step
        
        # 파이프라인 완료 확인
        if current_step == 'iou_eval' and current_status == 'done':
            elapsed = int(time.time() - start_time)
            print(f"\n✅ 파이프라인 완료! (총 소요 시간: {elapsed}초)")
            return True
        
        # 실패 확인
        if current_status == 'failed':
            print(f"\n❌ 파이프라인 실패: {current_step} 단계에서 실패")
            return False
        
        time.sleep(check_interval)
    
    print(f"\n⚠ 타임아웃: {max_wait_seconds}초 내에 파이프라인이 완료되지 않았습니다.")
    print(f"  현재 상태: {current_step}, {current_status}")
    return False

def main():
    """메인 테스트 함수"""
    print("\n" + "=" * 60)
    print("전체 파이프라인 자동 트리거 테스트")
    print("=" * 60)
    print("\n이 테스트는 다음을 수행합니다:")
    print("1. img_gen 완료 상태의 job 생성")
    print("2. Job 상태 업데이트하여 트리거 발동")
    print("3. 전체 파이프라인 자동 실행 모니터링")
    print("4. 최종 결과 확인")
    
    db = SessionLocal()
    try:
        # 1. img_gen 완료 상태의 job 생성
        job_info = create_img_gen_job(db, tenant_id="pipeline_auto_test_tenant")
        job_id = job_info["job_id"]
        tenant_id = job_info["tenant_id"]
        
        # 2. 초기 상태 확인
        print("\n" + "=" * 60)
        print("초기 Job 상태 확인")
        print("=" * 60)
        initial_status = check_job_status(db, job_id)
        print(f"  Job ID: {job_id}")
        print(f"  Status: {initial_status['status']}")
        print(f"  Current Step: {initial_status['current_step']}")
        
        # 3. 트리거 발동
        trigger_pipeline(db, job_id)
        
        # 4. 파이프라인 진행 상황 모니터링
        success = monitor_pipeline_progress(db, job_id, max_wait_seconds=300, check_interval=5)
        
        # 5. 최종 상태 확인
        print("\n" + "=" * 60)
        print("최종 Job 상태 확인")
        print("=" * 60)
        final_status = check_job_status(db, job_id)
        print(f"  Job ID: {final_status['job_id']}")
        print(f"  Status: {final_status['status']}")
        print(f"  Current Step: {final_status['current_step']}")
        print(f"  Updated At: {final_status['updated_at']}")
        
        if success:
            print("\n" + "=" * 60)
            print("✅ 테스트 성공!")
            print("=" * 60)
            print("\n전체 파이프라인이 자동으로 실행되었습니다.")
            print("모든 단계가 트리거를 통해 순차적으로 완료되었습니다.")
        else:
            print("\n" + "=" * 60)
            print("⚠ 테스트 완료 (일부 실패 또는 타임아웃)")
            print("=" * 60)
            print("\n로그를 확인하여 문제를 파악하세요:")
            print("  docker logs feedlyai-work-yh --tail 100 | grep -i 'listener\\|trigger\\|pipeline'")
        
        print("\n💡 로그 확인 명령어:")
        print("  docker logs feedlyai-work-yh --tail 200 | grep -i 'listener\\|trigger\\|pipeline\\|job 상태'")
        
    except Exception as e:
        logger.error(f"테스트 중 오류: {e}", exc_info=True)
        db.rollback()
        print(f"\n❌ 테스트 중 오류 발생: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()


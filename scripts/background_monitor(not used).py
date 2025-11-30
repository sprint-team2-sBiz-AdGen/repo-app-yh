"""백그라운드 모니터링 스크립트
백그라운드에서 계속 실행되면서 새로운 img_gen 완료 상태의 job을 감지하고
파이프라인 진행 상황을 모니터링하는 스크립트
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: 백그라운드 모니터링 스크립트
# version: 1.0.0
########################################################

import sys
import os
import uuid
import time
from pathlib import Path
from datetime import datetime
from PIL import Image

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
from utils import save_asset
import logging
import signal

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 전역 변수
running = True
monitored_jobs = set()  # 모니터링 중인 job_id들

def signal_handler(sig, frame):
    """종료 신호 처리"""
    global running
    print("\n\n종료 신호 수신. 모니터링을 종료합니다...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_img_gen_job(tenant_id: str = "background_monitor_tenant") -> str:
    """img_gen 완료 상태의 job 생성"""
    db = SessionLocal()
    try:
        # Tenant 생성
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"Background Monitor Tenant ({tenant_id})"
        })
        
        # 이미지 파일 찾기
        default_image_path = project_root / "pipeline_test" / "pipeline_test_image9.jpg"
        if not default_image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {default_image_path}")
        
        image = Image.open(default_image_path)
        
        # 이미지 저장
        asset_meta = save_asset(tenant_id, "background_monitor", image, ".jpg")
        asset_url = asset_meta["url"]
        
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
        
        return str(job_id)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Job 생성 오류: {e}")
        raise
    finally:
        db.close()

def trigger_job(job_id: str):
    """Job 상태를 업데이트하여 트리거 발동"""
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
        
    finally:
        db.close()

def check_job_status(job_id: str) -> tuple:
    """Job 상태 확인"""
    db = SessionLocal()
    try:
        result = db.execute(
            text("SELECT status, current_step, updated_at FROM jobs WHERE job_id = :job_id"),
            {"job_id": job_id}
        ).first()
        
        if result:
            return result[0], result[1], result[2]
        return None, None, None
    finally:
        db.close()

def monitor_job(job_id: str):
    """개별 Job 모니터링"""
    global monitored_jobs
    
    last_step = None
    start_time = time.time()
    
    while running:
        status, current_step, updated_at = check_job_status(job_id)
        
        if not status:
            logger.warning(f"Job을 찾을 수 없습니다: {job_id}")
            monitored_jobs.discard(job_id)
            return
        
        # 단계가 변경되었을 때만 출력
        if current_step != last_step:
            elapsed = int(time.time() - start_time)
            logger.info(f"[Job {job_id[:8]}...] [{elapsed:3d}초] {current_step} - Status: {status}")
            last_step = current_step
        
        # 파이프라인 완료 확인
        if current_step == 'iou_eval' and status == 'done':
            elapsed = int(time.time() - start_time)
            logger.info(f"[Job {job_id[:8]}...] ✅ 파이프라인 완료! (총 {elapsed}초 소요)")
            monitored_jobs.discard(job_id)
            return
        
        # 실패 확인
        if status == 'failed':
            elapsed = int(time.time() - start_time)
            logger.warning(f"[Job {job_id[:8]}...] ❌ 파이프라인 실패: {current_step} 단계에서 실패 (총 {elapsed}초 소요)")
            monitored_jobs.discard(job_id)
            return
        
        # 타임아웃 (10분)
        if time.time() - start_time > 600:
            logger.warning(f"[Job {job_id[:8]}...] ⚠ 타임아웃: 10분 내에 파이프라인이 완료되지 않았습니다.")
            monitored_jobs.discard(job_id)
            return
        
        time.sleep(5)  # 5초마다 확인

def find_new_jobs(tenant_id: str = "background_monitor_tenant", check_interval: int = 10):
    """새로운 img_gen 완료 상태의 job 찾기"""
    global monitored_jobs
    
    db = SessionLocal()
    try:
        # 최근 생성된 img_gen 완료 상태의 job 찾기
        result = db.execute(text("""
            SELECT job_id, created_at 
            FROM jobs 
            WHERE tenant_id = :tenant_id 
              AND current_step = 'img_gen' 
              AND status = 'done'
              AND created_at > NOW() - INTERVAL '1 hour'
            ORDER BY created_at DESC
            LIMIT 10
        """), {"tenant_id": tenant_id})
        
        new_jobs = []
        for row in result:
            job_id = str(row[0])
            if job_id not in monitored_jobs:
                new_jobs.append(job_id)
        
        return new_jobs
    finally:
        db.close()

def main_loop(auto_create: bool = False, create_interval: int = 60):
    """메인 루프"""
    global running, monitored_jobs
    
    logger.info("=" * 60)
    logger.info("백그라운드 모니터링 시작")
    logger.info("=" * 60)
    logger.info(f"자동 생성: {auto_create}")
    if auto_create:
        logger.info(f"생성 간격: {create_interval}초")
    logger.info("종료하려면 Ctrl+C를 누르세요")
    logger.info("=" * 60)
    
    last_create_time = 0
    
    while running:
        try:
            # 자동 생성 모드
            if auto_create and time.time() - last_create_time >= create_interval:
                try:
                    logger.info("새로운 job 생성 중...")
                    job_id = create_img_gen_job()
                    logger.info(f"✓ Job 생성 완료: {job_id}")
                    
                    # 트리거 발동
                    trigger_job(job_id)
                    logger.info(f"✓ 트리거 발동: {job_id}")
                    
                    monitored_jobs.add(job_id)
                    last_create_time = time.time()
                except Exception as e:
                    logger.error(f"Job 생성 실패: {e}")
            
            # 새로운 job 찾기
            new_jobs = find_new_jobs()
            for job_id in new_jobs:
                if job_id not in monitored_jobs:
                    logger.info(f"새로운 job 발견: {job_id}")
                    monitored_jobs.add(job_id)
                    # 별도 스레드로 모니터링 시작 (간단하게 동기 처리)
                    # 실제로는 threading이나 asyncio를 사용하는 것이 좋지만,
                    # 여기서는 간단하게 처리
            
            # 모니터링 중인 job들 상태 확인
            for job_id in list(monitored_jobs):
                monitor_job(job_id)
            
            # 모니터링 중인 job이 없으면 잠시 대기
            if not monitored_jobs:
                time.sleep(5)
            else:
                time.sleep(2)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"오류 발생: {e}", exc_info=True)
            time.sleep(5)
    
    logger.info("=" * 60)
    logger.info("백그라운드 모니터링 종료")
    logger.info("=" * 60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="백그라운드 모니터링 스크립트")
    parser.add_argument(
        "--auto-create",
        action="store_true",
        help="자동으로 job 생성 (기본: False)"
    )
    parser.add_argument(
        "--create-interval",
        type=int,
        default=60,
        help="자동 생성 간격 (초, 기본: 60)"
    )
    
    args = parser.parse_args()
    
    try:
        main_loop(auto_create=args.auto_create, create_interval=args.create_interval)
    except Exception as e:
        logger.error(f"프로그램 오류: {e}", exc_info=True)
        sys.exit(1)


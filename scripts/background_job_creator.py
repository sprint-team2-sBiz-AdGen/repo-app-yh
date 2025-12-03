"""백그라운드 Job 생성 스크립트
백그라운드에서 계속 실행되면서 주기적으로 job과 job_variants를 생성하고
트리거를 발동하여 파이프라인을 시작하는 스크립트
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-12-03
# author: LEEYH205
# description: 백그라운드 Job 생성 스크립트
# version: 2.0.1
########################################################

import sys
import os
import uuid
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Optional

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
from utils import save_asset
from PIL import Image
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 전역 변수
running = True
created_jobs = []  # 생성된 job_id들 (통계용)

def signal_handler(sig, frame):
    """종료 신호 처리"""
    global running
    print("\n\n종료 신호 수신. Job 생성을 종료합니다...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_job_with_variants(
    tenant_id: str = "background_job_creator_tenant",
    image_path: Optional[str] = None,
    text_path: Optional[str] = None,
    variants_count: int = 3
) -> dict:
    """job 1개와 job_variants N개 생성"""
    logger.info("\n" + "=" * 60)
    logger.info("Job 및 Job Variants 생성")
    logger.info("=" * 60)
    
    db = SessionLocal()
    try:
        # Tenant 생성
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"Background Job Creator Tenant ({tenant_id})"
        })
        logger.info(f"✓ Tenant 생성/확인: {tenant_id}")
        
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
        
        # Job 생성 (ye 파트에서 yh 파트 시작 시 설정)
        job_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step, created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, :status, :current_step, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "running",  # yh 파트 시작
            "current_step": "vlm_analyze"  # yh 파트 시작 단계
        })
        logger.info(f"✓ Job 생성: job_id={job_id}")
        logger.info(f"  - status=running, current_step=vlm_analyze")
        
        # Job Input 생성 (텍스트 정보 저장)
        db.execute(text("""
            INSERT INTO job_inputs (
                job_id, desc_eng, created_at, updated_at
            ) VALUES (
                :job_id, :desc_eng, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (job_id) DO UPDATE
            SET desc_eng = :desc_eng, updated_at = CURRENT_TIMESTAMP
        """), {
            "job_id": job_id,
            "desc_eng": ad_copy_text
        })
        logger.info(f"✓ Job Input 생성: desc_eng={ad_copy_text[:50]}...")
        
        # 이미지 파일 찾기 (variants_count개의 variant를 위해 이미지 필요)
        image_paths = []
        if image_path and os.path.exists(image_path):
            image_paths = [image_path] * variants_count  # 같은 이미지를 반복 사용
        else:
            # 기본 이미지 경로들 시도
            default_image_paths = [
                project_root / "pipeline_test" / "pipeline_test_image9.jpg",
                project_root / "pipeline_test" / "pipeline_test_image1.png",
            ]
            for img_path in default_image_paths:
                if img_path.exists():
                    image_paths.append(str(img_path))
            # variants_count개가 안 되면 첫 번째 이미지를 반복 사용
            while len(image_paths) < variants_count:
                if image_paths:
                    image_paths.append(image_paths[0])
                else:
                    raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {default_image_paths[0] if default_image_paths else 'pipeline_test'}")
        
        # Job Variants N개 생성
        job_variants = []
        for i, img_path in enumerate(image_paths[:variants_count], 1):
            logger.info(f"\n[Variant {i}/{variants_count}] 생성 중...")
            
            # 이미지 로드 및 저장
            image = Image.open(img_path)
            asset_meta = save_asset(tenant_id, f"variant_{i}", image, ".jpg")
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
                        image_asset_id, image_type, image_url, width, height, tenant_id, job_id, created_at, updated_at
                    ) VALUES (
                        :image_asset_id, 'generated', :asset_url, :width, :height, :tenant_id, :job_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """), {
                    "image_asset_id": image_asset_id,
                    "asset_url": asset_url,
                    "width": image.size[0],
                    "height": image.size[1],
                    "tenant_id": tenant_id,
                    "job_id": str(job_id)
                })
                db.commit()
            
            # Job Variant 생성 (img_gen 완료 상태)
            job_variants_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO jobs_variants (
                    job_variants_id, job_id, img_asset_id, creation_order,
                    status, current_step, created_at, updated_at
                ) VALUES (
                    :job_variants_id, :job_id, :img_asset_id, :creation_order,
                    :status, :current_step, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "job_variants_id": job_variants_id,
                "job_id": job_id,
                "img_asset_id": image_asset_id,
                "creation_order": i,
                "status": "done",  # img_gen 완료 상태
                "current_step": "img_gen"  # img_gen 완료 상태
            })
            db.commit()
            
            job_variants.append({
                "job_variants_id": str(job_variants_id),
                "img_asset_id": str(image_asset_id),
                "asset_url": asset_url,
                "creation_order": i,
                "job_id": str(job_id)  # job_id 추가
            })
            logger.info(f"✓ Variant {i} 생성 완료:")
            logger.info(f"  - job_variants_id: {job_variants_id}")
            logger.info(f"  - img_asset_id: {image_asset_id}")
            logger.info(f"  - status=done, current_step=img_gen")
        
        logger.info(f"\n✓ 총 {len(job_variants)}개 Variant 생성 완료")
        
        return {
            "job_id": str(job_id),
            "tenant_id": tenant_id,
            "job_variants": job_variants
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Job 생성 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()

def trigger_job_variants(job_id: str, job_variants: list):
    """Job Variants 상태를 업데이트하여 트리거 발동"""
    db = SessionLocal()
    try:
        for variant in job_variants:
            job_variants_id = variant["job_variants_id"]
            
            # 상태를 running으로 변경
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'running',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            time.sleep(0.1)  # 트리거 발동 대기
            
            # 상태를 done으로 변경하여 트리거 발동
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            time.sleep(0.1)  # 트리거 발동 대기
        
        logger.info(f"[Job {job_id[:8]}...] 트리거 발동 완료 ({len(job_variants)}개 variants)")
        
    except Exception as e:
        db.rollback()
        logger.error(f"트리거 발동 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()

def create_and_trigger_job(
    tenant_id: str = "background_job_creator_tenant",
    variants_count: int = 3
) -> Optional[str]:
    """Job 생성 및 트리거 발동"""
    global created_jobs
    
    try:
        logger.info(f"새로운 job 생성 시작 (variants: {variants_count}개)...")
        
        # Job 및 Variants 생성
        result = create_job_with_variants(
            tenant_id=tenant_id,
            variants_count=variants_count
        )
        
        job_id = result["job_id"]
        job_variants = result["job_variants"]
        
        logger.info(
            f"✓ Job 생성 완료: {job_id[:8]}... "
            f"(tenant: {tenant_id}, variants: {len(job_variants)}개)"
        )
        
        # 트리거 발동
        trigger_job_variants(job_id, job_variants)
        
        created_jobs.append({
            "job_id": job_id,
            "created_at": datetime.now(),
            "variants_count": len(job_variants)
        })
        
        return job_id
        
    except Exception as e:
        logger.error(f"Job 생성 및 트리거 발동 실패: {e}", exc_info=True)
        return None

def check_job_completed(db, job_id: str) -> bool:
    """Job이 완료되었는지 확인 (iou_eval, done)"""
    result = db.execute(
        text("""
            SELECT status, current_step
            FROM jobs
            WHERE job_id = :job_id
        """),
        {"job_id": job_id}
    ).first()
    
    if result:
        status, current_step = result[0], result[1]
        return current_step == 'iou_eval' and status == 'done'
    return False

def check_all_variants_completed(db, job_id: str) -> bool:
    """모든 Variants가 완료되었는지 확인 (iou_eval, done)"""
    variants = db.execute(
        text("""
            SELECT status, current_step
            FROM jobs_variants
            WHERE job_id = :job_id
        """),
        {"job_id": job_id}
    ).fetchall()
    
    if not variants:
        return False
    
    for variant in variants:
        status, current_step = variant[0], variant[1]
        if not (current_step == 'iou_eval' and status == 'done'):
            return False
    
    return True

def main_loop(
    tenant_id: str = "background_job_creator_tenant",
    create_interval: int = 60,
    variants_count: int = 3,
    once: bool = False,
    wait_for_completion: bool = False
):
    """메인 루프"""
    global running, created_jobs
    
    if once:
        logger.info("=" * 60)
        logger.info("Job 생성 (단일 실행)")
        logger.info("=" * 60)
        logger.info(f"Tenant ID: {tenant_id}")
        logger.info(f"Variants 개수: {variants_count}개")
        logger.info("=" * 60)
        
        # 한 번만 생성
        job_id = create_and_trigger_job(
            tenant_id=tenant_id,
            variants_count=variants_count
        )
        
        if job_id:
            logger.info("=" * 60)
            logger.info("✅ Job 생성 완료")
            logger.info("=" * 60)
            logger.info(f"Job ID: {job_id}")
            logger.info(f"Variants: {variants_count}개")
            logger.info("=" * 60)
            return job_id
        else:
            logger.error("❌ Job 생성 실패")
            return None
    else:
        logger.info("=" * 60)
        logger.info("백그라운드 Job 생성 시작")
        logger.info("=" * 60)
        logger.info(f"Tenant ID: {tenant_id}")
        if wait_for_completion:
            logger.info("모드: 이전 Job 완료 대기 후 생성")
        else:
            logger.info(f"생성 간격: {create_interval}초")
        logger.info(f"Variants 개수: {variants_count}개")
        logger.info("종료하려면 Ctrl+C를 누르세요")
        logger.info("=" * 60)
        
        last_create_time = 0
        start_time = time.time()
        current_job_id = None  # 현재 실행 중인 job 추적
        
        while running:
            try:
                current_time = time.time()
                
                if wait_for_completion:
                    # 이전 job 완료 대기 모드
                    if current_job_id:
                        # 현재 job 완료 확인
                        db = SessionLocal()
                        try:
                            job_completed = check_job_completed(db, current_job_id)
                            variants_completed = check_all_variants_completed(db, current_job_id)
                            
                            if job_completed and variants_completed:
                                logger.info(
                                    f"✅ 이전 Job 완료: {current_job_id[:8]}... "
                                    f"(iou_eval, done)"
                                )
                                current_job_id = None  # 다음 job 생성 준비
                            else:
                                # 아직 완료되지 않음, 대기
                                time.sleep(10)  # 10초마다 확인
                                continue
                        finally:
                            db.close()
                    else:
                        # 이전 job이 없거나 완료됨, 새 job 생성
                        job_id = create_and_trigger_job(
                            tenant_id=tenant_id,
                            variants_count=variants_count
                        )
                        
                        if job_id:
                            current_job_id = job_id
                            elapsed = int(current_time - start_time)
                            logger.info(
                                f"📊 통계: 총 {len(created_jobs)}개 job 생성 "
                                f"(경과 시간: {elapsed}초)"
                            )
                            logger.info(
                                f"⏳ 다음 Job 생성을 위해 완료 대기 중... "
                                f"(현재 Job: {job_id[:8]}...)"
                            )
                        time.sleep(10)  # 10초마다 확인
                else:
                    # 기존 방식: 주기적 생성
                    if current_time - last_create_time >= create_interval:
                        job_id = create_and_trigger_job(
                            tenant_id=tenant_id,
                            variants_count=variants_count
                        )
                        
                        if job_id:
                            elapsed = int(current_time - start_time)
                            logger.info(
                                f"📊 통계: 총 {len(created_jobs)}개 job 생성 "
                                f"(경과 시간: {elapsed}초, "
                                f"평균 간격: {elapsed // len(created_jobs) if created_jobs else 0}초)"
                            )
                        
                        last_create_time = current_time
                    
                    time.sleep(1)  # 1초마다 확인
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"오류 발생: {e}", exc_info=True)
                time.sleep(5)
        
        # 종료 시 통계 출력
        logger.info("=" * 60)
        logger.info("백그라운드 Job 생성 종료")
        logger.info("=" * 60)
        logger.info(f"총 생성된 Job 개수: {len(created_jobs)}개")
        
        if created_jobs:
            total_time = time.time() - start_time
            logger.info(f"총 실행 시간: {int(total_time)}초")
            if wait_for_completion:
                logger.info("모드: 이전 Job 완료 대기 후 생성")
            else:
                logger.info(f"평균 생성 간격: {int(total_time / len(created_jobs))}초")
            
            logger.info("\n생성된 Job 목록:")
            for i, job_info in enumerate(created_jobs[-10:], 1):  # 최근 10개만 출력
                logger.info(
                    f"  {i}. {job_info['job_id'][:8]}... "
                    f"(variants: {job_info['variants_count']}개, "
                    f"created: {job_info['created_at'].strftime('%Y-%m-%d %H:%M:%S')})"
                )
        
        logger.info("=" * 60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="백그라운드 Job 생성 스크립트")
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="background_job_creator_tenant",
        help="Tenant ID (기본: background_job_creator_tenant)"
    )
    parser.add_argument(
        "--create-interval",
        type=int,
        default=60,
        help="Job 생성 간격 (초, 기본: 60)"
    )
    parser.add_argument(
        "--variants-count",
        type=int,
        default=3,
        help="각 Job당 생성할 Variant 개수 (기본: 3)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Job을 한 번만 생성하고 종료 (기본: False, 주기적으로 생성)"
    )
    parser.add_argument(
        "--wait-for-completion",
        action="store_true",
        help="이전 Job 완료 (iou_eval, done) 대기 후 다음 Job 생성 (기본: False)"
    )
    
    args = parser.parse_args()
    
    try:
        main_loop(
            tenant_id=args.tenant_id,
            create_interval=args.create_interval,
            variants_count=args.variants_count,
            once=args.once,
            wait_for_completion=args.wait_for_completion
        )
    except Exception as e:
        logger.error(f"프로그램 오류: {e}", exc_info=True)
        sys.exit(1)


#!/usr/bin/env python3
"""YE 파트(이미지 생성) 파이프라인 테스트용 Background Job Creator
- 기존 이미지 파일을 사용하여 user_img_input (done) 상태로 Job 생성
- YE 파트가 실제로 img_gen을 완료하면 자동으로 YH 파트 파이프라인 시작
- ⚠️ 주의: 이 스크립트는 user_img_input (done) 상태로만 생성하며, 
  YE 파트가 실제로 img_gen을 완료할 때까지 기다립니다.
"""
########################################################
# created_at: 2025-12-01
# updated_at: 2025-12-03
# author: LEEYH205
# description: YE 파트 파이프라인 테스트용 Background Job Creator
# version: 1.2.1
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
    logger.info("종료 신호 수신. Job 생성을 종료합니다...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_ye_job_with_variants(
    tenant_id: str = "ye_pipeline_test_tenant",
    image_paths: Optional[list] = None,
    variants_count: int = 3
) -> dict:
    """YE 파트 테스트용: 기존 이미지를 사용하여 job과 job_variants 생성 (user_img_input done 상태)"""
    logger.info("\n" + "=" * 60)
    logger.info("YE 파트 테스트: Job 및 Job Variants 생성")
    logger.info("=" * 60)
    
    db = SessionLocal()
    try:
        # 1. Tenant 생성/확인
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"YE Pipeline Test Tenant ({tenant_id})"
        })
        db.commit()
        logger.info(f"✓ Tenant 확인/생성: {tenant_id}")
        
        # 2. Store 확인/생성 (선택적)
        store_row = db.execute(text("""
            SELECT store_id
            FROM stores
            LIMIT 1
        """)).first()
        
        store_id = None
        if store_row:
            store_id = store_row[0]
            logger.info(f"✓ Store 사용: {store_id}")
        else:
            logger.info(f"⚠ Store 없음 (NULL 사용)")
        
        # 3. 이미지 파일 찾기 (하나의 이미지만 사용, 모든 variants가 같은 이미지 사용)
        if image_paths:
            # 사용자가 지정한 이미지 경로 사용 (첫 번째 이미지만)
            available_images = [Path(p) for p in image_paths if os.path.exists(p)]
        else:
            # 기본 이미지 경로들 시도
            default_image_paths = [
                project_root / "pipeline_test" / "pipeline_test_image9.jpg",
                project_root / "pipeline_test" / "pipeline_test_image1.png",
                project_root / "pipeline_test" / "pipeline_test_image16.jpg",
                project_root / "pipeline_test" / "pipeline_test_image10.jpg",
                project_root / "pipeline_test" / "pipeline_test_image11.jpg",
            ]
            available_images = [p for p in default_image_paths if p.exists()]
        
        if not available_images:
            raise FileNotFoundError(
                f"이미지 파일을 찾을 수 없습니다. "
                f"기본 경로: {project_root / 'pipeline_test'}"
            )
        
        # 첫 번째 이미지만 사용 (모든 variants가 같은 이미지 사용)
        selected_image = available_images[0]
        logger.info(f"✓ 이미지 선택 완료: {selected_image.name}")
        logger.info(f"  - 모든 variants가 같은 이미지를 사용합니다")
        
        # 4. Job 생성 (user_img_input 완료 상태로 시작)
        job_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, store_id, status, current_step,
                created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, :store_id, :status, :current_step,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "store_id": store_id,
            "status": "done",  # user_img_input 완료 상태
            "current_step": "user_img_input"  # user_img_input 완료 상태
        })
        db.commit()
        logger.info(f"✓ Job 생성: job_id={job_id}")
        logger.info(f"  - status=done, current_step=user_img_input")
        
        # 5. 이미지 로드 및 image_asset 생성 (하나의 이미지만 사용)
        logger.info(f"\n[이미지 준비] 이미지 로드 및 저장 중...")
        image = Image.open(selected_image)
        asset_meta = save_asset(tenant_id, "ye_pipeline_test", image, ".jpg")
        asset_url = asset_meta["url"]
        
        # image_assets 확인/생성 (하나의 image_asset_id만 생성)
        existing = db.execute(
            text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
            {"url": asset_url, "tenant_id": tenant_id}
        ).first()
        
        if existing:
            image_asset_id = existing[0]
            logger.info(f"  - 기존 image_asset 사용: {image_asset_id}")
        else:
            image_asset_id = uuid.uuid4()
            db.execute(text("""
                INSERT INTO image_assets (
                    image_asset_id, image_type, image_url, width, height,
                    tenant_id, job_id, created_at, updated_at
                ) VALUES (
                    :image_asset_id, 'generated', :asset_url, :width, :height,
                    :tenant_id, :job_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
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
            logger.info(f"  - 새 image_asset 생성: {image_asset_id}")
        
        logger.info(f"✓ 이미지 준비 완료: {selected_image.name}")
        logger.info(f"  - image_asset_id: {image_asset_id}")
        logger.info(f"  - asset_url: {asset_url}")
        
        # 6. Job Input 생성 (선택적, 기본값)
        tone_style_row = db.execute(text("""
            SELECT tone_style_id
            FROM tone_styles
            LIMIT 1
        """)).first()
        
        tone_style_id = tone_style_row[0] if tone_style_row else None
        
        db.execute(text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, tone_style_id, desc_kor,
                created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :tone_style_id, :desc_kor,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (job_id) DO UPDATE
            SET updated_at = CURRENT_TIMESTAMP
        """), {
            "job_id": job_id,
            "img_asset_id": image_asset_id,  # 모든 variants와 같은 image_asset_id 사용
            "tone_style_id": tone_style_id,
            "desc_kor": "YE 파트 테스트용 이미지"
        })
        db.commit()
        logger.info(f"✓ Job Input 생성 완료 (img_asset_id: {image_asset_id})")
        
        # 7. Job Variants N개 생성 (user_img_input 완료 상태, 모두 같은 img_asset_id 사용)
        job_variants = []
        for i in range(1, variants_count + 1):
            logger.info(f"\n[Variant {i}/{variants_count}] 생성 중...")
            
            # Job Variant 생성 (user_img_input 완료 상태, 모든 variants가 같은 img_asset_id 사용)
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
                "img_asset_id": image_asset_id,  # 모든 variants가 같은 image_asset_id 사용
                "creation_order": i,
                "status": "done",  # user_img_input 완료 상태
                "current_step": "user_img_input"  # user_img_input 완료 상태
            })
            db.commit()
            
            job_variants.append({
                "job_variants_id": str(job_variants_id),
                "img_asset_id": str(image_asset_id),
                "asset_url": asset_url,
                "creation_order": i,
                "job_id": str(job_id)
            })
            logger.info(f"✓ Variant {i} 생성 완료:")
            logger.info(f"  - job_variants_id: {job_variants_id}")
            logger.info(f"  - img_asset_id: {image_asset_id} (모든 variants와 동일)")
            logger.info(f"  - status=done, current_step=user_img_input")
        
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

# ⚠️ 이 함수는 더 이상 사용되지 않습니다.
# YE 파트가 실제로 img_gen을 완료하면 자동으로 트리거됩니다.
# def trigger_job_variants(job_id: str, job_variants: list):
#     """Job Variants 상태를 업데이트하여 트리거 발동 (YE 파트 시작: user_img_input → img_gen)"""
#     ...

def create_and_trigger_job(
    tenant_id: str = "ye_pipeline_test_tenant",
    image_paths: Optional[list] = None,
    variants_count: int = 3
) -> Optional[str]:
    """Job 생성 (YE 파트가 실제로 img_gen을 완료할 때까지 대기)"""
    global created_jobs
    
    try:
        logger.info(f"새로운 job 생성 시작 (variants: {variants_count}개)...")
        
        # Job 및 Variants 생성
        result = create_ye_job_with_variants(
            tenant_id=tenant_id,
            image_paths=image_paths,
            variants_count=variants_count
        )
        
        job_id = result["job_id"]
        job_variants = result["job_variants"]
        
        logger.info(
            f"✓ Job 생성 완료: {job_id[:8]}... "
            f"(tenant: {tenant_id}, variants: {len(job_variants)}개)"
        )
        logger.info(
            f"  → 상태: user_img_input (done)"
        )
        logger.info(
            f"  → YE 파트가 실제로 img_gen을 완료하면 자동으로 YH 파트 파이프라인이 시작됩니다."
        )
        
        # ⚠️ 트리거 발동하지 않음 - YE 파트가 실제로 img_gen을 완료할 때까지 대기
        # trigger_job_variants(job_id, job_variants)  # 제거됨
        
        created_jobs.append({
            "job_id": job_id,
            "created_at": datetime.now(),
            "variants_count": len(job_variants)
        })
        
        return job_id
        
    except Exception as e:
        logger.error(f"Job 생성 실패: {e}", exc_info=True)
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

def main_loop(
    tenant_id: str = "ye_pipeline_test_tenant",
    create_interval: int = 60,
    image_paths: Optional[list] = None,
    variants_count: int = 3,
    once: bool = False,
    wait_for_completion: bool = False
):
    """메인 루프"""
    global running, created_jobs
    
    if once:
        logger.info("=" * 60)
        logger.info("YE 파트 테스트: Job 생성 (단일 실행)")
        logger.info("=" * 60)
        logger.info(f"Tenant ID: {tenant_id}")
        logger.info(f"Variants 개수: {variants_count}개")
        if image_paths:
            logger.info(f"이미지 경로: {image_paths}")
        logger.info("=" * 60)
        
        # 한 번만 생성
        job_id = create_and_trigger_job(
            tenant_id=tenant_id,
            image_paths=image_paths,
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
        logger.info("YE 파트 테스트: 백그라운드 Job 생성 시작")
        logger.info("=" * 60)
        logger.info(f"Tenant ID: {tenant_id}")
        if wait_for_completion:
            logger.info("모드: 이전 Job 완료 대기 후 생성")
        else:
            logger.info(f"생성 간격: {create_interval}초")
        logger.info(f"Variants 개수: {variants_count}개")
        if image_paths:
            logger.info(f"이미지 경로: {image_paths}")
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
                            
                            if job_completed:
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
                            image_paths=image_paths,
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
                            image_paths=image_paths,
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
        logger.info("YE 파트 테스트: 백그라운드 Job 생성 종료")
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
    
    parser = argparse.ArgumentParser(description="YE 파트 파이프라인 테스트용 Background Job Creator")
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="ye_pipeline_test_tenant",
        help="Tenant ID (기본: ye_pipeline_test_tenant)"
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
        "--image-paths",
        type=str,
        nargs="+",
        default=None,
        help="사용할 이미지 파일 경로들 (여러 개 지정 가능, 기본: pipeline_test 디렉토리에서 자동 선택)"
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
            image_paths=args.image_paths,
            variants_count=args.variants_count,
            once=args.once,
            wait_for_completion=args.wait_for_completion
        )
    except Exception as e:
        logger.error(f"프로그램 오류: {e}", exc_info=True)
        sys.exit(1)


#!/usr/bin/env python3
"""YE 파트 img_gen 완료 시뮬레이션 테스트 코드

이 스크립트는 YE 파트가 img_gen을 완료했을 때의 동작을 시뮬레이션합니다.
실제 YE 파트 코드에서 참고할 수 있는 스켈레톤 코드입니다.

사용 방법:
    python3 test/test_ye_img_gen_trigger.py --job-id <job_id>
    python3 test/test_ye_img_gen_trigger.py --tenant-id <tenant_id>  # 최신 job 자동 선택
"""
########################################################
# created_at: 2025-12-02
# author: LEEYH205
# description: YE 파트 img_gen 완료 시뮬레이션
# version: 1.1.0
########################################################

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_pending_variants(db, job_id: str = None, tenant_id: str = None):
    """user_img_input (done) 상태의 variants 조회"""
    if job_id:
        query = text("""
            SELECT 
                jv.job_variants_id,
                jv.job_id,
                jv.img_asset_id,
                jv.status,
                jv.current_step,
                j.job_id,
                j.tenant_id
            FROM jobs_variants jv
            INNER JOIN jobs j ON jv.job_id = j.job_id
            WHERE jv.job_id = :job_id
                AND jv.current_step = 'user_img_input'
                AND jv.status = 'done'
            ORDER BY jv.creation_order
        """)
        params = {"job_id": job_id}
    elif tenant_id:
        query = text("""
            SELECT 
                jv.job_variants_id,
                jv.job_id,
                jv.img_asset_id,
                jv.status,
                jv.current_step,
                j.job_id,
                j.tenant_id
            FROM jobs_variants jv
            INNER JOIN jobs j ON jv.job_id = j.job_id
            WHERE j.tenant_id = :tenant_id
                AND jv.current_step = 'user_img_input'
                AND jv.status = 'done'
            ORDER BY j.created_at DESC, jv.creation_order
            LIMIT 10
        """)
        params = {"tenant_id": tenant_id}
    else:
        raise ValueError("job_id 또는 tenant_id 중 하나는 필수입니다.")
    
    results = db.execute(query, params).fetchall()
    return results


def simulate_img_gen(db, job_variants_id: str, job_id: str):
    """img_gen 완료 시뮬레이션
    
    실제 YE 파트에서는:
    1. img_asset_id를 사용하여 이미지 생성
    2. 생성된 이미지를 저장
    3. 상태를 img_gen (done)으로 업데이트
    
    이 함수는 상태 업데이트만 수행합니다.
    """
    logger.info(f"[img_gen 시뮬레이션] job_variants_id={job_variants_id}")
    
    # 1. 현재 상태 확인
    current = db.execute(text("""
        SELECT status, current_step, img_asset_id
        FROM jobs_variants
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id}).first()
    
    if not current:
        logger.error(f"Variant를 찾을 수 없습니다: {job_variants_id}")
        return False
    
    current_status, current_step, img_asset_id = current
    logger.info(f"  현재 상태: status={current_status}, current_step={current_step}")
    logger.info(f"  img_asset_id: {img_asset_id}")
    
    if current_step != 'user_img_input' or current_status != 'done':
        logger.warning(
            f"예상하지 못한 상태: current_step={current_step}, status={current_status}. "
            f"user_img_input (done) 상태여야 합니다."
        )
        return False
    
    # 2. img_gen 실행 중 상태로 변경 (선택적)
    # 실제로는 img_gen이 실행되는 동안 running 상태로 변경할 수 있습니다.
    logger.info("  [1단계] img_gen 실행 중... (status=running)")
    db.execute(text("""
        UPDATE jobs_variants
        SET status = 'running',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id})
    db.commit()
    logger.info("  ✓ status=running, current_step=img_gen으로 업데이트 완료")
    
    # 3. 실제 img_gen 작업 수행 (시뮬레이션)
    # 실제 YE 파트에서는 여기서 이미지 생성 로직을 실행합니다.
    logger.info("  [2단계] 이미지 생성 중... (시뮬레이션)")
    # 예시: 실제 이미지 생성 코드
    # generated_image = your_image_generation_function(img_asset_id)
    # save_generated_image(generated_image)
    logger.info("  ✓ 이미지 생성 완료 (시뮬레이션)")
    
    # 4. img_gen 완료 상태로 변경 (이것이 트리거를 발동시킵니다!)
    logger.info("  [3단계] img_gen 완료 상태로 업데이트... (트리거 발동)")
    db.execute(text("""
        UPDATE jobs_variants
        SET status = 'done',
            current_step = 'img_gen',
            updated_at = CURRENT_TIMESTAMP
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id})
    db.commit()
    logger.info("  ✓ status=done, current_step=img_gen으로 업데이트 완료")
    logger.info("  ✓ PostgreSQL 트리거가 자동으로 발동됩니다!")
    logger.info("  ✓ YH 파트 파이프라인이 자동으로 시작됩니다!")
    
    # 5. 리스너 동작 확인 (5-10초 후)
    logger.info("\n  [4단계] 리스너 동작 확인 중... (10초 대기)")
    import time
    time.sleep(10)
    
    result = db.execute(text("""
        SELECT status, current_step, updated_at
        FROM jobs_variants
        WHERE job_variants_id = :job_variants_id
    """), {"job_variants_id": job_variants_id}).first()
    
    if result:
        status, current_step, updated_at = result
        logger.info(f"  현재 상태: {current_step} ({status})")
        
        if current_step == 'vlm_analyze':
            logger.info("  ✅ 리스너가 정상 작동했습니다! 다음 단계로 자동 진행되었습니다.")
        elif current_step == 'img_gen':
            logger.warning("  ⚠️ 아직 img_gen 상태입니다. 리스너가 이벤트를 감지하지 못했을 수 있습니다.")
            logger.info("     → YH 파트에 문의하여 리스너 상태를 확인하세요.")
        else:
            logger.info(f"  ℹ️ 현재 단계: {current_step}")
    
    return True


def process_job_variants(db, job_id: str, variants):
    """Job의 모든 variants 처리"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Job ID: {job_id}")
    logger.info(f"처리할 Variants: {len(variants)}개")
    logger.info(f"{'='*60}\n")
    
    for i, variant in enumerate(variants, 1):
        job_variants_id = variant[0]
        variant_job_id = variant[1]
        img_asset_id = variant[2]
        
        logger.info(f"\n[Variant {i}/{len(variants)}]")
        logger.info(f"  job_variants_id: {job_variants_id}")
        logger.info(f"  img_asset_id: {img_asset_id}")
        
        # img_gen 완료 시뮬레이션
        success = simulate_img_gen(db, job_variants_id, variant_job_id)
        
        if success:
            logger.info(f"  ✅ Variant {i} 처리 완료")
        else:
            logger.error(f"  ❌ Variant {i} 처리 실패")
    
    logger.info(f"\n{'='*60}")
    logger.info("✅ 모든 Variants 처리 완료")
    logger.info(f"{'='*60}\n")
    logger.info("다음 단계:")
    logger.info("  1. PostgreSQL 트리거가 자동으로 NOTIFY 이벤트 발행")
    logger.info("  2. FastAPI 리스너가 이벤트를 감지")
    logger.info("  3. pipeline_trigger.py가 다음 단계 (vlm_analyze) 자동 호출")
    logger.info("  4. 파이프라인이 자동으로 진행됩니다!")


def main():
    parser = argparse.ArgumentParser(description="YE 파트 img_gen 완료 시뮬레이션")
    parser.add_argument(
        "--job-id",
        type=str,
        help="처리할 Job ID (지정하지 않으면 tenant-id로 최신 job 선택)"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="ye_pipeline_test_tenant",
        help="Tenant ID (기본: ye_pipeline_test_tenant)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 업데이트 없이 조회만 수행"
    )
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        # 1. 처리할 variants 조회
        logger.info("="*60)
        logger.info("YE 파트 img_gen 완료 시뮬레이션")
        logger.info("="*60)
        
        if args.job_id:
            logger.info(f"Job ID: {args.job_id}")
            variants = get_pending_variants(db, job_id=args.job_id)
        else:
            logger.info(f"Tenant ID: {args.tenant_id} (최신 job 자동 선택)")
            variants = get_pending_variants(db, tenant_id=args.tenant_id)
        
        if not variants:
            logger.warning("처리할 variants가 없습니다.")
            logger.info("조건: current_step='user_img_input', status='done'")
            return
        
        # 첫 번째 variant의 job_id 추출
        job_id = variants[0][1]
        
        if args.dry_run:
            logger.info(f"\n[DRY RUN] 처리할 Variants: {len(variants)}개")
            for i, variant in enumerate(variants, 1):
                logger.info(f"  {i}. job_variants_id={variant[0]}, img_asset_id={variant[2]}")
            logger.info("\n실제 업데이트를 수행하려면 --dry-run 옵션을 제거하세요.")
            return
        
        # 2. variants 처리
        process_job_variants(db, job_id, variants)
        
    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()


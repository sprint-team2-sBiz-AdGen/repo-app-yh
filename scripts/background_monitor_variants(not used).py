"""백그라운드 Job Variants 모니터링 스크립트
백그라운드에서 계속 실행되면서 새로운 job_id를 감지하고
각 job의 variants 파이프라인 진행 상황을 모니터링하는 스크립트
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-11-28
# author: LEEYH205
# description: 백그라운드 Job Variants 모니터링 스크립트
# version: 2.0.0
########################################################

import sys
import os
import uuid
import time
import signal
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, Optional

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 전역 변수
running = True
monitored_jobs: Set[str] = set()  # 모니터링 중인 job_id들
job_start_times: Dict[str, float] = {}  # 각 job의 시작 시간

def signal_handler(sig, frame):
    """종료 신호 처리"""
    global running
    print("\n\n종료 신호 수신. 모니터링을 종료합니다...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def check_variant_status(db, job_variants_id: str) -> Optional[Dict]:
    """Job Variant 상태 확인"""
    result = db.execute(
        text("""
            SELECT status, current_step, updated_at
            FROM jobs_variants
            WHERE job_variants_id = :job_variants_id
        """),
        {"job_variants_id": job_variants_id}
    ).first()
    
    if result:
        return {
            "status": result[0],
            "current_step": result[1],
            "updated_at": result[2]
        }
    return None

def check_job_status(db, job_id: str) -> Optional[Dict]:
    """Job 상태 확인"""
    result = db.execute(
        text("""
            SELECT status, current_step, updated_at
            FROM jobs
            WHERE job_id = :job_id
        """),
        {"job_id": job_id}
    ).first()
    
    if result:
        return {
            "status": result[0],
            "current_step": result[1],
            "updated_at": result[2]
        }
    return None

def get_job_variants(db, job_id: str) -> list:
    """Job의 모든 Variants 조회"""
    variants = db.execute(
        text("""
            SELECT job_variants_id, creation_order, status, current_step
            FROM jobs_variants
            WHERE job_id = :job_id
            ORDER BY creation_order
        """),
        {"job_id": job_id}
    ).fetchall()
    
    return variants

def monitor_job_variants(job_id: str, check_interval: int = 30, max_wait_minutes: int = 20):
    """Job의 Variants 파이프라인 모니터링"""
    global monitored_jobs, job_start_times
    
    db = SessionLocal()
    try:
        start_time = time.time()
        job_start_times[job_id] = start_time
        max_wait_seconds = max_wait_minutes * 60
        last_check_time = 0
        last_job_step = None
        last_variant_steps = {}  # 각 variant의 마지막 단계
        
        logger.info(f"[Job {job_id[:8]}...] 모니터링 시작")
        
        while running:
            elapsed = time.time() - start_time
            
            # 타임아웃 확인
            if elapsed > max_wait_seconds:
                logger.warning(f"[Job {job_id[:8]}...] ⏱️ 타임아웃: {max_wait_minutes}분 내에 파이프라인이 완료되지 않았습니다.")
                monitored_jobs.discard(job_id)
                job_start_times.pop(job_id, None)
                return
            
            # 주기적으로 상태 확인
            if elapsed - last_check_time >= check_interval:
                # Job 상태 확인
                job_status = check_job_status(db, job_id)
                if not job_status:
                    logger.warning(f"[Job {job_id[:8]}...] Job을 찾을 수 없습니다.")
                    monitored_jobs.discard(job_id)
                    job_start_times.pop(job_id, None)
                    return
                
                # Job 단계 변경 로그
                if job_status['current_step'] != last_job_step:
                    logger.info(
                        f"[Job {job_id[:8]}...] [{int(elapsed):3d}초] "
                        f"Job 전체: {job_status['current_step']} ({job_status['status']})"
                    )
                    last_job_step = job_status['current_step']
                
                # Variants 조회
                variants = get_job_variants(db, job_id)
                
                if not variants:
                    logger.warning(f"[Job {job_id[:8]}...] Variants를 찾을 수 없습니다.")
                    monitored_jobs.discard(job_id)
                    job_start_times.pop(job_id, None)
                    return
                
                # Variants 상태 출력
                variant_statuses = []
                all_done = True
                any_failed = False
                
                for variant in variants:
                    job_variants_id = variant[0]
                    creation_order = variant[1]
                    variant_status = check_variant_status(db, job_variants_id)
                    
                    if variant_status:
                        step = variant_status['current_step']
                        status = variant_status['status']
                        
                        # 단계 변경 시 로그 출력
                        variant_key = f"V{creation_order}"
                        if variant_key not in last_variant_steps or last_variant_steps[variant_key] != step:
                            logger.info(
                                f"[Job {job_id[:8]}...] [{int(elapsed):3d}초] "
                                f"Variant {creation_order}: {step} ({status})"
                            )
                            last_variant_steps[variant_key] = step
                        
                        variant_statuses.append({
                            "order": creation_order,
                            "step": step,
                            "status": status
                        })
                        
                        # 완료 조건: current_step이 'iou_eval'이고 status가 'done'
                        if not (step == "iou_eval" and status == "done"):
                            all_done = False
                        if status == "failed":
                            any_failed = True
                    else:
                        all_done = False
                
                # 모든 variants 완료 확인
                if all_done:
                    logger.info(
                        f"[Job {job_id[:8]}...] ✅ 파이프라인 완료! "
                        f"(총 {int(elapsed)}초 소요, {len(variants)}개 variants)"
                    )
                    monitored_jobs.discard(job_id)
                    job_start_times.pop(job_id, None)
                    return
                
                # 실패 확인
                if any_failed:
                    logger.warning(
                        f"[Job {job_id[:8]}...] ⚠️ 일부 Variants 실패 "
                        f"(총 {int(elapsed)}초 소요)"
                    )
                    # 실패해도 계속 모니터링 (다른 variants가 완료될 수 있음)
                
                last_check_time = elapsed
            
            time.sleep(5)  # 5초마다 확인
            
    except Exception as e:
        logger.error(f"[Job {job_id[:8]}...] 모니터링 오류: {e}", exc_info=True)
        monitored_jobs.discard(job_id)
        job_start_times.pop(job_id, None)
    finally:
        db.close()

def find_new_jobs(
    tenant_id: Optional[str] = None,
    check_interval: int = 10,
    min_variants: int = 1
) -> list:
    """새로운 job_id 찾기 (jobs_variants가 있는 job)"""
    global monitored_jobs
    
    db = SessionLocal()
    try:
        # jobs_variants가 있는 job 찾기
        # img_gen 완료 상태이거나 vlm_analyze 이후 단계인 job
        query = """
            SELECT DISTINCT j.job_id, j.created_at, j.tenant_id
            FROM jobs j
            INNER JOIN jobs_variants jv ON j.job_id = jv.job_id
            WHERE j.created_at > NOW() - INTERVAL '1 hour'
              AND jv.status IN ('done', 'running')
              AND jv.current_step IN ('img_gen', 'vlm_analyze', 'yolo_detect', 'planner', 'overlay', 'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval')
        """
        
        params = {}
        if tenant_id:
            query += " AND j.tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id
        
        query += """
            GROUP BY j.job_id, j.created_at, j.tenant_id
            HAVING COUNT(jv.job_variants_id) >= :min_variants
            ORDER BY j.created_at DESC
            LIMIT 20
        """
        params["min_variants"] = min_variants
        
        result = db.execute(text(query), params)
        
        new_jobs = []
        for row in result:
            job_id = str(row[0])
            if job_id not in monitored_jobs:
                new_jobs.append({
                    "job_id": job_id,
                    "tenant_id": row[2],
                    "created_at": row[1]
                })
        
        return new_jobs
    finally:
        db.close()

def main_loop(
    tenant_id: Optional[str] = None,
    check_interval: int = 30,
    max_wait_minutes: int = 20,
    scan_interval: int = 10
):
    """메인 루프"""
    global running, monitored_jobs
    
    logger.info("=" * 60)
    logger.info("백그라운드 Job Variants 모니터링 시작")
    logger.info("=" * 60)
    if tenant_id:
        logger.info(f"Tenant ID 필터: {tenant_id}")
    logger.info(f"상태 확인 간격: {check_interval}초")
    logger.info(f"최대 대기 시간: {max_wait_minutes}분")
    logger.info(f"새 Job 스캔 간격: {scan_interval}초")
    logger.info("종료하려면 Ctrl+C를 누르세요")
    logger.info("=" * 60)
    
    last_scan_time = 0
    
    while running:
        try:
            # 주기적으로 새로운 job 스캔
            if time.time() - last_scan_time >= scan_interval:
                new_jobs = find_new_jobs(tenant_id=tenant_id)
                
                for job_info in new_jobs:
                    job_id = job_info["job_id"]
                    if job_id not in monitored_jobs:
                        logger.info(
                            f"새로운 job 발견: {job_id[:8]}... "
                            f"(tenant: {job_info['tenant_id']}, "
                            f"created: {job_info['created_at']})"
                        )
                        monitored_jobs.add(job_id)
                
                last_scan_time = time.time()
            
            # 모니터링 중인 job들 상태 확인
            for job_id in list(monitored_jobs):
                monitor_job_variants(
                    job_id,
                    check_interval=check_interval,
                    max_wait_minutes=max_wait_minutes
                )
            
            # 모니터링 중인 job이 없으면 잠시 대기
            if not monitored_jobs:
                time.sleep(scan_interval)
            else:
                time.sleep(2)
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"오류 발생: {e}", exc_info=True)
            time.sleep(5)
    
    logger.info("=" * 60)
    logger.info("백그라운드 모니터링 종료")
    logger.info(f"모니터링 중이던 Job 개수: {len(monitored_jobs)}")
    logger.info("=" * 60)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="백그라운드 Job Variants 모니터링 스크립트")
    parser.add_argument(
        "--tenant-id",
        type=str,
        default=None,
        help="모니터링할 Tenant ID (기본: 모든 tenant)"
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=30,
        help="상태 확인 간격 (초, 기본: 30)"
    )
    parser.add_argument(
        "--max-wait-minutes",
        type=int,
        default=20,
        help="최대 대기 시간 (분, 기본: 20)"
    )
    parser.add_argument(
        "--scan-interval",
        type=int,
        default=10,
        help="새 Job 스캔 간격 (초, 기본: 10)"
    )
    
    args = parser.parse_args()
    
    try:
        main_loop(
            tenant_id=args.tenant_id,
            check_interval=args.check_interval,
            max_wait_minutes=args.max_wait_minutes,
            scan_interval=args.scan_interval
        )
    except Exception as e:
        logger.error(f"프로그램 오류: {e}", exc_info=True)
        sys.exit(1)


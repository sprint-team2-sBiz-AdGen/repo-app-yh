"""Job Variants 기반 파이프라인 테스트
job_id 1개에 대해 job_variants 3개를 생성하고
각 variant별로 파이프라인이 독립적으로 실행되는지 테스트
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: Job Variants 기반 파이프라인 테스트
# version: 2.0.0
########################################################

import sys
import os
import uuid
import time
import argparse
from pathlib import Path
from PIL import Image

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, Job, JobInput, ImageAsset, JobVariant
from sqlalchemy import text
from utils import save_asset
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_job_with_variants(
    tenant_id: str = "job_variants_test_tenant",
    image_path: str = None,
    text_path: str = None,
    variants_count: int = 3
) -> dict:
    """job 1개와 job_variants N개 생성"""
    print("\n" + "=" * 60)
    print("Job 및 Job Variants 생성")
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
            "display_name": f"Job Variants Test Tenant ({tenant_id})"
        })
        print(f"✓ Tenant 생성/확인: {tenant_id}")
        
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
        print(f"✓ Job 생성: job_id={job_id}")
        print(f"  - status=running, current_step=vlm_analyze")
        
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
        print(f"✓ Job Input 생성: desc_eng={ad_copy_text[:50]}...")
        
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
            print(f"\n[Variant {i}/3] 생성 중...")
            
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
            print(f"✓ Variant {i} 생성 완료:")
            print(f"  - job_variants_id: {job_variants_id}")
            print(f"  - img_asset_id: {image_asset_id}")
            print(f"  - status=done, current_step=img_gen")
        
        print(f"\n✓ 총 {len(job_variants)}개 Variant 생성 완료")
        
        return {
            "job_id": str(job_id),
            "tenant_id": tenant_id,
            "job_variants": job_variants
        }
        
    finally:
        db.close()

def check_variant_status(db, job_variants_id: str):
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

def check_job_status(db, job_id: str):
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

def monitor_pipeline_progress(job_id: str, tenant_id: str, max_wait_minutes: int = 10):
    """파이프라인 진행 상황 모니터링"""
    print("\n" + "=" * 60)
    print("파이프라인 진행 상황 모니터링")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # Job Variants 조회
        variants = db.execute(
            text("""
                SELECT job_variants_id, creation_order, status, current_step
                FROM jobs_variants
                WHERE job_id = :job_id
                ORDER BY creation_order
            """),
            {"job_id": job_id}
        ).fetchall()
        
        if not variants:
            print(f"❌ Job Variants를 찾을 수 없습니다: job_id={job_id}")
            return
        
        print(f"\n총 {len(variants)}개 Variant 모니터링 시작...")
        print(f"최대 대기 시간: {max_wait_minutes}분")
        
        start_time = time.time()
        max_wait_seconds = max_wait_minutes * 60
        
        # 각 variant의 최종 단계
        final_step = "iou_eval"
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                print(f"\n⏱️  최대 대기 시간({max_wait_minutes}분) 초과")
                break
            
            print(f"\n[{int(elapsed)}초] 상태 확인...")
            
            all_done = True
            any_failed = False
            
            for variant in variants:
                job_variants_id = variant[0]
                creation_order = variant[1]
                status = check_variant_status(db, job_variants_id)
                
                if status:
                    step_icon = "✓" if status["status"] == "done" and status["current_step"] == "iou_eval" else "⏳" if status["status"] == "running" else "❌" if status["status"] == "failed" else "🔄"
                    print(f"  {step_icon} Variant {creation_order}: {status['current_step']} ({status['status']})")
                    
                    # 완료 조건: current_step이 'iou_eval'이고 status가 'done'
                    if not (status["current_step"] == "iou_eval" and status["status"] == "done"):
                        all_done = False
                    if status["status"] == "failed":
                        any_failed = True
                else:
                    print(f"  ❓ Variant {creation_order}: 상태 확인 불가")
                    all_done = False
            
            # Job 상태 확인
            job_status = check_job_status(db, job_id)
            if job_status:
                print(f"  📋 Job 전체: {job_status['current_step']} ({job_status['status']})")
            
            if all_done:
                print(f"\n✅ 모든 Variants 완료!")
                break
            
            if any_failed:
                print(f"\n⚠️  일부 Variants 실패")
                break
            
            time.sleep(5)  # 5초마다 확인
        
        # 최종 상태 출력
        print("\n" + "=" * 60)
        print("최종 상태")
        print("=" * 60)
        
        for variant in variants:
            job_variants_id = variant[0]
            creation_order = variant[1]
            status = check_variant_status(db, job_variants_id)
            
            if status:
                print(f"Variant {creation_order}: {status['current_step']} ({status['status']})")
        
        job_status = check_job_status(db, job_id)
        if job_status:
            print(f"Job 전체: {job_status['current_step']} ({job_status['status']})")
        
    finally:
        db.close()

def print_table_status(db, job_id: str, step_name: str = ""):
    """jobs와 jobs_variants 테이블 상태 출력"""
    print(f"\n{'=' * 60}")
    if step_name:
        print(f"[{step_name}] 테이블 상태")
    else:
        print("테이블 상태")
    print(f"{'=' * 60}")
    
    # jobs 테이블 상태
    job_status = check_job_status(db, job_id)
    if job_status:
        print(f"📋 jobs 테이블:")
        print(f"   - job_id: {job_id[:8]}...")
        print(f"   - status: {job_status['status']}")
        print(f"   - current_step: {job_status['current_step']}")
        print(f"   - updated_at: {job_status['updated_at']}")
    else:
        print(f"📋 jobs 테이블: Job을 찾을 수 없습니다")
    
    # jobs_variants 테이블 상태
    variants = db.execute(
        text("""
            SELECT job_variants_id, creation_order, status, current_step, updated_at
            FROM jobs_variants
            WHERE job_id = :job_id
            ORDER BY creation_order
        """),
        {"job_id": job_id}
    ).fetchall()
    
    print(f"\n📦 jobs_variants 테이블 (총 {len(variants)}개):")
    for variant in variants:
        print(f"   Variant {variant[1]}:")
        print(f"     - job_variants_id: {str(variant[0])[:8]}...")
        print(f"     - status: {variant[2]}")
        print(f"     - current_step: {variant[3]}")
        print(f"     - updated_at: {variant[4]}")
    
    print()

def main():
    """메인 함수"""
    # Argument parser 설정
    parser = argparse.ArgumentParser(description="Job Variants 기반 파이프라인 테스트")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="생성할 Job 개수 (기본값: 1)"
    )
    parser.add_argument(
        "--variants-per-job",
        type=int,
        default=3,
        help="각 Job당 생성할 Variant 개수 (기본값: 3)"
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="job_variants_test_tenant",
        help="테넌트 ID (기본값: job_variants_test_tenant)"
    )
    parser.add_argument(
        "--max-wait-minutes",
        type=int,
        default=15,
        help="최대 대기 시간 (분, 기본값: 15)"
    )
    
    args = parser.parse_args()
    
    num_jobs = args.jobs
    variants_per_job = args.variants_per_job
    tenant_id = args.tenant_id
    max_wait_minutes = args.max_wait_minutes
    
    print("=" * 60)
    print(f"Job Variants 기반 파이프라인 테스트")
    print(f"  - Job 개수: {num_jobs}개")
    print(f"  - Job당 Variant 개수: {variants_per_job}개")
    print(f"  - 총 Variant 개수: {num_jobs * variants_per_job}개")
    print("=" * 60)
    
    # 1. Job N개 및 각 Job에 Job Variants M개씩 생성
    all_jobs = []
    all_variants = []
    
    for job_num in range(1, num_jobs + 1):
        print(f"\n{'=' * 60}")
        print(f"Job {job_num}/{num_jobs} 생성 중...")
        print(f"{'=' * 60}")
        
        result = create_job_with_variants(
            tenant_id=tenant_id,
            variants_count=variants_per_job
        )
        job_id = result["job_id"]
        job_variants = result["job_variants"]
        
        all_jobs.append({
            "job_id": job_id,
            "job_num": job_num,
            "variants": job_variants
        })
        all_variants.extend(job_variants)
        
        print(f"\n✓ Job {job_num} 생성 완료:")
        print(f"  - Job ID: {job_id}")
        print(f"  - Variants: {len(job_variants)}개")
    
    print(f"\n{'=' * 60}")
    print(f"전체 테스트 데이터 생성 완료")
    print(f"{'=' * 60}")
    print(f"  - 총 Jobs: {len(all_jobs)}개")
    print(f"  - 총 Variants: {len(all_variants)}개")
    
    # 초기 상태 확인 (모든 Job)
    db = SessionLocal()
    try:
        for job_info in all_jobs:
            print_table_status(db, job_info["job_id"], f"초기 상태 - Job {job_info['job_num']} (생성 직후)")
    finally:
        db.close()
    
    # 2. 트리거 발동을 위해 모든 variant 상태를 업데이트
    print("\n" + "=" * 60)
    print("트리거 발동 (상태 업데이트)")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        for variant in all_variants:
            job_variants_id = variant["job_variants_id"]
            # 상태를 다시 업데이트하여 트리거 발동
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
            time.sleep(0.2)  # 트리거 발동 대기
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
        print(f"✓ 총 {len(all_variants)}개 Variants 트리거 발동 완료")
        
        # 트리거 발동 후 상태 확인
        for job_info in all_jobs:
            print_table_status(db, job_info["job_id"], f"트리거 발동 후 - Job {job_info['job_num']}")
    finally:
        db.close()
    
    # 3. 파이프라인 진행 상황 모니터링 (모든 Job에 대해)
    print("\n⏳ 파이프라인 실행 대기 중... (트리거가 감지되면 자동으로 시작됩니다)")
    time.sleep(5)  # 트리거가 감지될 시간 대기
    
    # 각 Job에 대해 모니터링
    for job_info in all_jobs:
        print(f"\n{'=' * 60}")
        print(f"Job {job_info['job_num']} 파이프라인 모니터링")
        print(f"{'=' * 60}")
        
        db = SessionLocal()
        try:
            start_time = time.time()
            max_wait_seconds = max_wait_minutes * 60
            check_interval = 30  # 30초마다 상태 확인
            
            print(f"최대 대기 시간: {max_wait_minutes}분")
            print(f"상태 확인 간격: {check_interval}초")
            
            last_check_time = 0
            while True:
                elapsed = time.time() - start_time
                if elapsed > max_wait_seconds:
                    print(f"\n⏱️  최대 대기 시간({max_wait_minutes}분) 초과")
                    break
                
                # 주기적으로 상태 확인
                if elapsed - last_check_time >= check_interval:
                    print_table_status(db, job_info["job_id"], f"진행 중 - Job {job_info['job_num']} ({int(elapsed)}초 경과)")
                    last_check_time = elapsed
                
                # 모든 variants 완료 확인
                variants = db.execute(
                    text("""
                        SELECT job_variants_id, creation_order, status, current_step
                        FROM jobs_variants
                        WHERE job_id = :job_id
                        ORDER BY creation_order
                    """),
                    {"job_id": job_info["job_id"]}
                ).fetchall()
                
                all_done = True
                any_failed = False
                
                for variant in variants:
                    if not (variant[3] == "iou_eval" and variant[2] == "done"):
                        all_done = False
                    if variant[2] == "failed":
                        any_failed = True
                
                if all_done:
                    print(f"\n✅ Job {job_info['job_num']}의 모든 Variants 완료!")
                    break
                
                if any_failed:
                    print(f"\n⚠️  Job {job_info['job_num']}의 일부 Variants 실패")
                    break
                
                time.sleep(5)  # 5초마다 확인
            
            # 최종 상태 확인
            print_table_status(db, job_info["job_id"], f"최종 상태 - Job {job_info['job_num']}")
        finally:
            db.close()
    
    print("\n" + "=" * 60)
    print("테스트 완료")
    print("=" * 60)

if __name__ == "__main__":
    main()


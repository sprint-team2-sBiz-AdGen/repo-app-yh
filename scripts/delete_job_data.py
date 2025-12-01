#!/usr/bin/env python3
"""Job 관련 데이터 삭제 스크립트"""
########################################################
# created_at: 2025-01-XX
# author: Auto-generated
# description: 특정 job_id에 관련된 모든 데이터를 삭제하는 스크립트
# version: 1.0.0
########################################################

import sys
import uuid
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import (
    SessionLocal,
    Job,
    JobInput,
    JobVariant,
    VLMTrace,
    Detection,
    YOLORun,
    Evaluation,
    LLMTrace,
    TxtAdCopyGeneration,
    InstagramFeed,
    OverlayLayout,
    PlannerProposal
)


def delete_job_data(job_ids):
    """특정 job_id에 관련된 모든 데이터를 삭제"""
    db = SessionLocal()
    deleted_counts = {}
    
    try:
        # UUID로 변환
        job_uuid_list = [uuid.UUID(job_id) for job_id in job_ids]
        
        print(f"\n{'='*60}")
        print(f"Job 데이터 삭제 시작: {job_ids}")
        print(f"{'='*60}\n")
        
        # 1. Instagram Feeds 삭제
        count = db.query(InstagramFeed).filter(InstagramFeed.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['instagram_feeds'] = count
        print(f"✓ instagram_feeds: {count}개 삭제")
        
        # 2. Text Ad Copy Generations 삭제
        count = db.query(TxtAdCopyGeneration).filter(TxtAdCopyGeneration.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['txt_ad_copy_generations'] = count
        print(f"✓ txt_ad_copy_generations: {count}개 삭제")
        
        # 3. LLM Traces 삭제
        count = db.query(LLMTrace).filter(LLMTrace.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['llm_traces'] = count
        print(f"✓ llm_traces: {count}개 삭제")
        
        # 4. Job Variants 조회 (overlay_layouts 삭제를 위해)
        job_variants = db.query(JobVariant).filter(JobVariant.job_id.in_(job_uuid_list)).all()
        job_variant_ids = [jv.job_variants_id for jv in job_variants]
        
        # 5. Evaluations 삭제 (job_id 또는 overlay를 통해)
        # overlay_id를 통한 삭제를 위해 overlay_layouts 먼저 확인
        overlay_ids = []
        if job_variant_ids:
            overlays = db.query(OverlayLayout).filter(OverlayLayout.job_variants_id.in_(job_variant_ids)).all()
            overlay_ids = [ol.overlay_id for ol in overlays]
        
        count = 0
        if job_uuid_list:
            count += db.query(Evaluation).filter(Evaluation.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        if overlay_ids:
            count += db.query(Evaluation).filter(Evaluation.overlay_id.in_(overlay_ids)).delete(synchronize_session=False)
        deleted_counts['evaluations'] = count
        print(f"✓ evaluations: {count}개 삭제")
        
        # 6. Overlay Layouts 삭제
        count = 0
        if job_variant_ids:
            count = db.query(OverlayLayout).filter(OverlayLayout.job_variants_id.in_(job_variant_ids)).delete(synchronize_session=False)
        deleted_counts['overlay_layouts'] = count
        print(f"✓ overlay_layouts: {count}개 삭제")
        
        # 7. Planner Proposals 삭제 (job_variants의 img_asset_id를 통해 연결 확인 필요)
        # job_variants의 img_asset_id를 추출
        img_asset_ids = [jv.img_asset_id for jv in job_variants] if job_variants else []
        count = 0
        if img_asset_ids:
            count = db.query(PlannerProposal).filter(PlannerProposal.image_asset_id.in_(img_asset_ids)).delete(synchronize_session=False)
        deleted_counts['planner_proposals'] = count
        print(f"✓ planner_proposals: {count}개 삭제")
        
        # 8. Detections 삭제
        count = db.query(Detection).filter(Detection.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['detections'] = count
        print(f"✓ detections: {count}개 삭제")
        
        # 9. YOLO Runs 삭제
        count = db.query(YOLORun).filter(YOLORun.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['yolo_runs'] = count
        print(f"✓ yolo_runs: {count}개 삭제")
        
        # 10. VLM Traces 삭제
        count = db.query(VLMTrace).filter(VLMTrace.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['vlm_traces'] = count
        print(f"✓ vlm_traces: {count}개 삭제")
        
        # 11. Job Variants 삭제
        count = db.query(JobVariant).filter(JobVariant.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['jobs_variants'] = count
        print(f"✓ jobs_variants: {count}개 삭제")
        
        # 12. Job Inputs 삭제
        count = db.query(JobInput).filter(JobInput.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['job_inputs'] = count
        print(f"✓ job_inputs: {count}개 삭제")
        
        # 13. Jobs 삭제 (마지막)
        count = db.query(Job).filter(Job.job_id.in_(job_uuid_list)).delete(synchronize_session=False)
        deleted_counts['jobs'] = count
        print(f"✓ jobs: {count}개 삭제")
        
        # 커밋
        db.commit()
        
        print(f"\n{'='*60}")
        print("삭제 완료!")
        print(f"{'='*60}")
        print("\n삭제된 데이터 통계:")
        total = 0
        for table, count in deleted_counts.items():
            if count > 0:
                print(f"  {table}: {count}개")
                total += count
        print(f"\n총 {total}개 레코드 삭제됨")
        
        return True
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    # 삭제할 job_ids
    job_ids = [
        "3bdd2048-bdad-4238-a9f6-f95abf56b6a7",
        "f6cd6b3d-0166-460e-94cb-9eb1b8581955"
    ]
    
    success = delete_job_data(job_ids)
    sys.exit(0 if success else 1)


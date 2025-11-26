"""LLaVA Stage 2 Judge 테스트 스크립트"""
import sys
import os
import uuid
import requests
import json

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from sqlalchemy.orm import Session
from database import SessionLocal, OverlayLayout, PlannerProposal, JobInput, Job, VLMTrace
from utils import abs_from_url
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def find_latest_overlay_job(db: Session) -> dict:
    """최신 overlay와 연결된 job 정보 찾기"""
    overlay = db.query(OverlayLayout).order_by(OverlayLayout.created_at.desc()).first()
    if not overlay:
        return None
    
    job_id = None
    tenant_id = None
    
    # overlay와 연결된 job 찾기 (proposal_id를 통해)
    if overlay.proposal_id:
        proposal = db.query(PlannerProposal).filter(
            PlannerProposal.proposal_id == overlay.proposal_id
        ).first()
        if proposal:
            job_input = db.query(JobInput).filter(
                JobInput.img_asset_id == proposal.image_asset_id
            ).first()
            if job_input:
                job_id = str(job_input.job_id)
                job = db.query(Job).filter(Job.job_id == job_input.job_id).first()
                if job:
                    tenant_id = job.tenant_id
    
    if not job_id:
        # 최신 job 찾기
        latest_job = db.query(Job).order_by(Job.created_at.desc()).first()
        if latest_job:
            job_id = str(latest_job.job_id)
            tenant_id = latest_job.tenant_id
    
    return {
        "job_id": job_id,
        "overlay_id": str(overlay.overlay_id),
        "tenant_id": tenant_id or "pipeline_test_tenant"
    }


def test_llava_stage2(job_id: str, tenant_id: str, overlay_id: str = None, api_url: str = "http://localhost:8011") -> dict:
    """LLaVA Stage 2 Judge API 테스트"""
    print("\n" + "=" * 60)
    print("LLaVA Stage 2 Judge API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/llava/stage2/judge"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id
    }
    
    if overlay_id:
        request_data["overlay_id"] = overlay_id
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(json.dumps(request_data, indent=2, ensure_ascii=False))
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        raise


def verify_db_records(db: Session, job_id: str):
    """DB 레코드 확인"""
    print("\n" + "=" * 60)
    print("DB 레코드 확인")
    print("=" * 60)
    
    try:
        # Job 상태 확인
        job = db.query(Job).filter(Job.job_id == uuid.UUID(job_id)).first()
        if job:
            print(f"\n✓ Job 상태:")
            print(f"  - Current Step: {job.current_step}")
            print(f"  - Status: {job.status}")
        else:
            print("⚠ Job을 찾을 수 없습니다.")
            return
        
        # VLM Traces 확인 (judge)
        vlm_traces = db.query(VLMTrace).filter(
            VLMTrace.job_id == uuid.UUID(job_id),
            VLMTrace.operation_type == 'judge'
        ).order_by(VLMTrace.created_at.desc()).all()
        
        if vlm_traces:
            print(f"\n✓ VLM Traces (judge): {len(vlm_traces)}개")
            latest_trace = vlm_traces[0]
            print(f"  - VLM Trace ID: {latest_trace.vlm_trace_id}")
            print(f"  - Operation Type: {latest_trace.operation_type}")
            print(f"  - Provider: {latest_trace.provider}")
            print(f"  - Latency: {latest_trace.latency_ms:.2f}ms" if latest_trace.latency_ms else "  - Latency: N/A")
            
            if latest_trace.response:
                response = latest_trace.response
                print(f"  - Response Keys: {list(response.keys())}")
                print(f"  - On Brief: {response.get('on_brief', 'N/A')}")
                print(f"  - Occlusion: {response.get('occlusion', 'N/A')}")
                print(f"  - Contrast OK: {response.get('contrast_ok', 'N/A')}")
                print(f"  - CTA Present: {response.get('cta_present', 'N/A')}")
                issues = response.get('issues', [])
                print(f"  - Issues: {len(issues)}개")
                if issues:
                    for i, issue in enumerate(issues[:3], 1):
                        print(f"    {i}. {issue[:80]}...")
        else:
            print("\n⚠ VLM Trace (judge)를 찾을 수 없습니다.")
        
        print(f"\n✓ DB 레코드 확인 완료!")
        
    except Exception as e:
        print(f"\n❌ DB 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 테스트 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLaVA Stage 2 Judge 테스트")
    parser.add_argument("--job-id", type=str, help="테스트할 job_id (없으면 최신 job 사용)")
    parser.add_argument("--overlay-id", type=str, help="테스트할 overlay_id (없으면 최신 overlay 사용)")
    parser.add_argument("--tenant-id", type=str, default="pipeline_test_tenant", help="테넌트 ID")
    parser.add_argument("--api-url", type=str, default="http://localhost:8011", help="API 서버 URL")
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        # Job 및 Overlay 정보 찾기
        if args.job_id:
            job_id = args.job_id
            tenant_id = args.tenant_id
            overlay_id = args.overlay_id
            
            # overlay_id가 없으면 최신 overlay 찾기
            if not overlay_id:
                overlay = db.query(OverlayLayout).order_by(OverlayLayout.created_at.desc()).first()
                if overlay:
                    overlay_id = str(overlay.overlay_id)
                    print(f"✓ 최신 Overlay ID 사용: {overlay_id}")
        else:
            # 최신 overlay와 job 찾기
            info = find_latest_overlay_job(db)
            if not info:
                print("❌ Overlay를 찾을 수 없습니다. 먼저 파이프라인을 실행하세요.")
                sys.exit(1)
            
            job_id = info["job_id"]
            overlay_id = info["overlay_id"]
            tenant_id = info["tenant_id"]
            
            print(f"\n✓ 최신 Job 및 Overlay 사용:")
            print(f"  - Job ID: {job_id}")
            print(f"  - Overlay ID: {overlay_id}")
            print(f"  - Tenant ID: {tenant_id}")
        
        # LLaVA Stage 2 테스트
        result = test_llava_stage2(job_id, tenant_id, overlay_id, args.api_url)
        
        # DB 확인
        verify_db_records(db, job_id)
        
        print("\n" + "=" * 60)
        print("✓ LLaVA Stage 2 테스트 완료!")
        print("=" * 60)
        print(f"\nJob ID: {job_id}")
        print(f"Overlay ID: {overlay_id}")
        print(f"Tenant ID: {tenant_id}")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()


"""정량 평가 API 테스트 스크립트"""
import sys
import os
import uuid
import requests
import json

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from sqlalchemy.orm import Session
from database import SessionLocal, OverlayLayout, PlannerProposal, JobInput, Job
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


def test_ocr_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """OCR 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("OCR 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/ocr/evaluate"
    data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"요청 URL: {url}")
    print(f"요청 데이터: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        print("✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        raise


def test_readability_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """가독성 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("가독성 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/readability/evaluate"
    data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"요청 URL: {url}")
    print(f"요청 데이터: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print("✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        raise


def test_iou_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """IoU 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("IoU 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/iou/evaluate"
    data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"요청 URL: {url}")
    print(f"요청 데이터: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print("✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        raise


def test_full_eval(tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """통합 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("통합 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/evaluations/full"
    data = {
        "tenant_id": tenant_id,
        "overlay_id": overlay_id,
        "evaluation_types": None  # None이면 모두 실행
    }
    
    print(f"요청 URL: {url}")
    print(f"요청 데이터: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(url, json=data, timeout=180)  # 모든 평가를 실행하므로 시간 여유
        response.raise_for_status()
        
        result = response.json()
        print("✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        return result
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        raise


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="정량 평가 API 테스트")
    parser.add_argument("--job-id", type=str, help="Job ID (지정하지 않으면 최신 job 사용)")
    parser.add_argument("--overlay-id", type=str, help="Overlay ID (지정하지 않으면 최신 overlay 사용)")
    parser.add_argument("--tenant-id", type=str, default="pipeline_test_tenant", help="Tenant ID")
    parser.add_argument("--api-url", type=str, default="http://localhost:8011", help="API URL")
    parser.add_argument("--eval-type", type=str, choices=["ocr", "readability", "iou", "full", "all"], 
                       default="all", help="실행할 평가 타입")
    
    args = parser.parse_args()
    
    db = SessionLocal()
    try:
        # Job 및 Overlay 정보 찾기
        if args.job_id and args.overlay_id:
            job_id = args.job_id
            overlay_id = args.overlay_id
            tenant_id = args.tenant_id
        else:
            job_info = find_latest_overlay_job(db)
            if not job_info:
                print("❌ 최신 overlay를 찾을 수 없습니다. 파이프라인을 먼저 실행하세요.")
                return
            
            job_id = job_info["job_id"]
            overlay_id = job_info["overlay_id"]
            tenant_id = job_info["tenant_id"]
        
        print("=" * 60)
        print("정량 평가 API 테스트")
        print("=" * 60)
        print(f"\n✓ 최신 Job 및 Overlay 사용:")
        print(f"  - Job ID: {job_id}")
        print(f"  - Overlay ID: {overlay_id}")
        print(f"  - Tenant ID: {tenant_id}")
        
        # 평가 타입에 따라 실행
        if args.eval_type == "ocr" or args.eval_type == "all":
            test_ocr_eval(job_id, tenant_id, overlay_id, args.api_url)
        
        if args.eval_type == "readability" or args.eval_type == "all":
            test_readability_eval(job_id, tenant_id, overlay_id, args.api_url)
        
        if args.eval_type == "iou" or args.eval_type == "all":
            test_iou_eval(job_id, tenant_id, overlay_id, args.api_url)
        
        if args.eval_type == "full" or args.eval_type == "all":
            test_full_eval(tenant_id, overlay_id, args.api_url)
        
        print("\n" + "=" * 60)
        print("✓ 정량 평가 테스트 완료!")
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == "__main__":
    main()


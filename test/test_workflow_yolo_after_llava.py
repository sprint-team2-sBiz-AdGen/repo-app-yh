"""LLaVA Stage 1 이후 YOLO 동작 확인 테스트"""
import sys
import os
import uuid
import requests
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, ImageAsset, Job, JobInput, Detection, YOLORun
from utils import save_asset, abs_from_url
from config import ASSETS_DIR
import logging

logger = logging.getLogger(__name__)


def setup_test_job(db: Session, tenant_id: str, image_path: str = None) -> dict:
    """테스트용 job 생성 (img_gen 완료 상태)"""
    print("\n" + "=" * 60)
    print("테스트 Job 생성 (img_gen 완료 상태)")
    print("=" * 60)
    
    # 1. 이미지 준비
    if image_path and os.path.exists(image_path):
        print(f"\n[1/4] 기존 이미지 사용: {image_path}")
        image = Image.open(image_path)
        if image_path.startswith(ASSETS_DIR):
            rel_path = image_path[len(ASSETS_DIR):].lstrip("/")
            asset_url = f"/assets/{rel_path}"
        else:
            asset_meta = save_asset(tenant_id, "test_workflow", image, ".png")
            asset_url = asset_meta["url"]
            image_path = abs_from_url(asset_url)
    else:
        print(f"\n[1/4] 테스트 이미지 생성 중...")
        image = Image.new("RGB", (512, 512), color=(255, 100, 50))
        asset_meta = save_asset(tenant_id, "test_workflow", image, ".png")
        asset_url = asset_meta["url"]
        image_path = abs_from_url(asset_url)
    
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # 2. tenant 확인/생성
    print(f"\n[2/4] tenant 확인/생성 중...")
    try:
        tenant_check = db.execute(
            text("SELECT tenant_id FROM tenants WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        ).first()
        
        if not tenant_check:
            db.execute(
                text("INSERT INTO tenants (tenant_id, display_name) VALUES (:tenant_id, :display_name)"),
                {"tenant_id": tenant_id, "display_name": f"Test Tenant - {tenant_id}"}
            )
            db.commit()
            print(f"✓ tenant '{tenant_id}' 생성 완료")
        else:
            print(f"✓ tenant '{tenant_id}' 확인 완료")
    except Exception as e:
        print(f"  ⚠ tenant 확인 중 오류: {e}")
        db.rollback()
        raise
    
    # 3. image_assets 확인/생성
    print(f"\n[3/4] image_assets 확인/생성 중...")
    existing = db.execute(
        text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
        {"url": asset_url, "tenant_id": tenant_id}
    ).first()
    
    if existing:
        image_asset_id = existing[0]
        print(f"✓ 기존 image_asset 레코드 발견: {image_asset_id}")
    else:
        image_asset_id = uuid.uuid4()
        image_asset_uid = uuid.uuid4().hex
        db.execute(
            text("""
                INSERT INTO image_assets (
                    image_asset_id, image_type, image_url, width, height,
                    tenant_id, uid, created_at, updated_at
                ) VALUES (
                    :image_asset_id, :image_type, :image_url, :width, :height,
                    :tenant_id, :uid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "image_asset_id": image_asset_id,
                "image_type": "test",
                "image_url": asset_url,
                "width": image.size[0],
                "height": image.size[1],
                "tenant_id": tenant_id,
                "uid": image_asset_uid
            }
        )
        db.commit()
        print(f"✓ image_asset 레코드 생성 완료: {image_asset_id}")
    
    # 4. jobs 및 job_inputs 생성 (img_gen 완료 상태)
    print(f"\n[4/4] jobs 및 job_inputs 생성 중...")
    job_uuid = uuid.uuid4()
    db.execute(
        text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step, created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, :status, :current_step, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "job_id": job_uuid,
            "tenant_id": tenant_id,
            "status": "done",
            "current_step": "img_gen"
        }
    )
    
    db.execute(
        text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, desc_eng, created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :desc_eng, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "job_id": job_uuid,
            "img_asset_id": image_asset_id,
            "desc_eng": "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
        }
    )
    db.commit()
    print(f"✓ job 및 job_inputs 레코드 생성 완료:")
    print(f"  - Job ID: {job_uuid}")
    print(f"  - Status: done")
    print(f"  - Current Step: img_gen")
    
    return {
        "tenant_id": tenant_id,
        "job_id": str(job_uuid),
        "image_asset_id": str(image_asset_id),
        "asset_url": asset_url
    }


def check_job_status(db: Session, job_id: str, expected_step: str = None, expected_status: str = None):
    """Job 상태 확인"""
    job = db.query(Job).filter(Job.job_id == uuid.UUID(job_id)).first()
    if job:
        print(f"\n  Job 상태:")
        print(f"    - Status: {job.status}")
        print(f"    - Current Step: {job.current_step}")
        if expected_status and job.status != expected_status:
            print(f"    ⚠ 경고: 예상 status={expected_status}, 실제={job.status}")
        if expected_step and job.current_step != expected_step:
            print(f"    ⚠ 경고: 예상 current_step={expected_step}, 실제={job.current_step}")
        return job
    else:
        print(f"  ❌ Job을 찾을 수 없습니다: {job_id}")
        return None


def test_llava_stage1(job_id: str, tenant_id: str, api_url: str = "http://localhost:8011") -> dict:
    """LLaVA Stage 1 API 테스트"""
    print("\n" + "=" * 60)
    print("LLaVA Stage 1 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/llava/stage1/validate"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Job ID: {result.get('job_id')}")
        print(f"  - VLM Trace ID: {result.get('vlm_trace_id')}")
        print(f"  - Is Valid: {result.get('is_valid')}")
        print(f"  - Relevance Score: {result.get('relevance_score')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_yolo(job_id: str, tenant_id: str, api_url: str = "http://localhost:8011") -> dict:
    """YOLO API 테스트"""
    print("\n" + "=" * 60)
    print("YOLO API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/yolo/detect"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Job ID: {result.get('job_id')}")
        print(f"  - Detection IDs: {len(result.get('detection_ids', []))}개")
        print(f"  - Model: {result.get('model')}")
        print(f"  - 감지된 박스 개수: {len(result.get('boxes', []))}")
        print(f"  - Forbidden Mask URL: {result.get('forbidden_mask_url', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def verify_db_records(db: Session, job_id: str):
    """DB 레코드 확인"""
    print("\n" + "=" * 60)
    print("DB 레코드 확인")
    print("=" * 60)
    
    try:
        # Job 상태 확인
        job = check_job_status(db, job_id)
        if not job:
            return False
        
        # job_inputs 확인
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if job_input:
            print(f"\n  Job Input:")
            print(f"    - Image Asset ID: {job_input.img_asset_id}")
        
        # vlm_traces 확인 (LLaVA Stage 1)
        from database import VLMTrace
        vlm_traces = db.query(VLMTrace).filter(VLMTrace.job_id == uuid.UUID(job_id)).all()
        if vlm_traces:
            print(f"\n  VLM Traces: {len(vlm_traces)}개")
            for trace in vlm_traces:
                print(f"    - Provider: {trace.provider}, Operation: {trace.operation_type}")
        
        # yolo_runs 확인
        yolo_run = db.query(YOLORun).filter(YOLORun.job_id == uuid.UUID(job_id)).first()
        if yolo_run:
            print(f"\n  YOLO Run:")
            print(f"    - YOLO Run ID: {yolo_run.yolo_run_id}")
            print(f"    - Image Asset ID: {yolo_run.image_asset_id}")
            print(f"    - Forbidden Mask URL: {yolo_run.forbidden_mask_url}")
            print(f"    - Model Name: {yolo_run.model_name}")
            print(f"    - Detection Count: {yolo_run.detection_count}")
        else:
            print(f"\n  ⚠ YOLO Run을 찾을 수 없습니다")
        
        # detections 확인
        detections = db.query(Detection).filter(Detection.job_id == uuid.UUID(job_id)).all()
        if detections:
            print(f"\n  Detections: {len(detections)}개")
            for i, det in enumerate(detections[:5]):  # 최대 5개만 출력
                print(f"    Detection {i+1}: {det.label} (score: {det.score:.2f})")
            if len(detections) > 5:
                print(f"    ... 외 {len(detections) - 5}개")
        else:
            print(f"\n  ⚠ Detections를 찾을 수 없습니다")
        
        print(f"\n✓ DB 레코드 확인 완료!")
        return True
        
    except Exception as e:
        print(f"\n❌ DB 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLaVA Stage 1 이후 YOLO 동작 확인 테스트")
    parser.add_argument("--job-id", type=str, default=None,
                       help="테스트할 job_id (없으면 새로 생성)")
    parser.add_argument("--tenant-id", default="test_workflow_tenant",
                       help="테스트용 tenant_id")
    parser.add_argument("--image-path", type=str, default=None,
                       help="사용할 이미지 경로")
    parser.add_argument("--api-url", default="http://localhost:8011",
                       help="API 서버 URL")
    parser.add_argument("--skip-llava", action="store_true",
                       help="LLaVA Stage 1 건너뛰기")
    parser.add_argument("--skip-yolo", action="store_true",
                       help="YOLO 건너뛰기")
    args = parser.parse_args()
    
    # DB 연결
    db = None
    try:
        db = SessionLocal()
        print("✓ DB 연결 성공")
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        sys.exit(1)
    
    try:
        # Job 준비
        if args.job_id:
            print(f"\n✓ 제공된 job_id 사용: {args.job_id}")
            job_id = args.job_id
            
            # tenant_id 가져오기
            job = db.execute(
                text("SELECT tenant_id FROM jobs WHERE job_id = :job_id"),
                {"job_id": uuid.UUID(job_id)}
            ).first()
            
            if not job:
                print(f"❌ Job을 찾을 수 없습니다: {job_id}")
                sys.exit(1)
            
            tenant_id = job[0]
        else:
            # 새 job 생성
            test_data = setup_test_job(db, args.tenant_id, args.image_path)
            job_id = test_data["job_id"]
            tenant_id = test_data["tenant_id"]
        
        # 초기 상태 확인
        print("\n" + "=" * 60)
        print("초기 Job 상태 확인")
        print("=" * 60)
        check_job_status(db, job_id, expected_step="img_gen", expected_status="done")
        
        # LLaVA Stage 1 테스트
        if not args.skip_llava:
            llava_result = test_llava_stage1(job_id, tenant_id, args.api_url)
            
            # LLaVA Stage 1 이후 상태 확인
            print("\n" + "=" * 60)
            print("LLaVA Stage 1 이후 Job 상태 확인")
            print("=" * 60)
            check_job_status(db, job_id, expected_step="vlm_analyze", expected_status="done")
        else:
            print("\n⚠ LLaVA Stage 1 건너뛰기")
        
        # YOLO 테스트
        if not args.skip_yolo:
            yolo_result = test_yolo(job_id, tenant_id, args.api_url)
            
            # YOLO 이후 상태 확인
            print("\n" + "=" * 60)
            print("YOLO 이후 Job 상태 확인")
            print("=" * 60)
            check_job_status(db, job_id, expected_step="yolo_detect", expected_status="done")
        else:
            print("\n⚠ YOLO 건너뛰기")
        
        # 최종 DB 레코드 확인
        verify_db_records(db, job_id)
        
        print("\n" + "=" * 60)
        print("✓ 테스트 완료!")
        print("=" * 60)
        print(f"\nJob ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        
    except Exception as e:
        print(f"\n❌ 테스트 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()


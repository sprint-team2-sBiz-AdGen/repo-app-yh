"""Planner API DB 연동 테스트"""
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
from database import SessionLocal, ImageAsset, Job, JobInput, Detection, YOLORun, PlannerProposal
from utils import save_asset, abs_from_url
from config import ASSETS_DIR
import logging

logger = logging.getLogger(__name__)


def setup_test_job_for_planner(db: Session, tenant_id: str, image_path: str = None) -> dict:
    """테스트용 job 생성 (yolo_detect 완료 상태)"""
    print("\n" + "=" * 60)
    print("테스트 Job 생성 (yolo_detect 완료 상태)")
    print("=" * 60)
    
    # 1. 이미지 준비 (기본 이미지 경로 사용)
    default_image_path = "/opt/feedlyai/assets/yh/tenants/test_workflow_tenant/test_workflow/2025/11/24/7e330c4b-5deb-484b-b7d4-1a1945ad0237.png"
    
    if image_path and os.path.exists(image_path):
        print(f"\n[1/5] 지정된 이미지 사용: {image_path}")
        actual_image_path = image_path
    elif os.path.exists(default_image_path):
        print(f"\n[1/5] 기본 이미지 사용: {default_image_path}")
        actual_image_path = default_image_path
    else:
        raise FileNotFoundError(
            f"이미지를 찾을 수 없습니다.\n"
            f"  - 지정된 경로: {image_path}\n"
            f"  - 기본 경로: {default_image_path}\n"
            f"Planner 테스트를 위해 실제 이미지가 필요합니다."
        )
    
    image = Image.open(actual_image_path)
    if actual_image_path.startswith(ASSETS_DIR):
        rel_path = actual_image_path[len(ASSETS_DIR):].lstrip("/")
        asset_url = f"/assets/{rel_path}"
    else:
        # ASSETS_DIR 밖에 있으면 복사
        asset_meta = save_asset(tenant_id, "test_planner", image, ".png")
        asset_url = asset_meta["url"]
        actual_image_path = abs_from_url(asset_url)
    
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Image Path: {actual_image_path}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # 2. tenant 확인/생성
    print(f"\n[2/5] tenant 확인/생성 중...")
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
    print(f"\n[3/5] image_assets 확인/생성 중...")
    existing = db.execute(
        text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
        {"url": asset_url, "tenant_id": tenant_id}
    ).first()
    
    if existing:
        image_asset_id = existing[0]
        print(f"✓ 기존 image_asset 레코드 발견: {image_asset_id}")
    else:
        image_asset_id = uuid.uuid4()
        db.execute(
            text("""
                INSERT INTO image_assets (
                    image_asset_id, image_type, image_url, width, height,
                    tenant_id, created_at, updated_at
                ) VALUES (
                    :image_asset_id, :image_type, :image_url, :width, :height,
                    :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "image_asset_id": image_asset_id,
                "image_type": "test",
                "image_url": asset_url,
                "width": image.size[0],
                "height": image.size[1],
                "tenant_id": tenant_id
            }
        )
        db.commit()
        print(f"✓ image_asset 레코드 생성 완료: {image_asset_id}")
    
    # 4. jobs 및 job_inputs 생성 (yolo_detect 완료 상태)
    print(f"\n[4/5] jobs 및 job_inputs 생성 중...")
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
            "current_step": "yolo_detect"
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
    print(f"  - Current Step: yolo_detect")
    
    # 5. YOLO 결과 시뮬레이션 (yolo_runs 및 detections 생성)
    print(f"\n[5/5] YOLO 결과 시뮬레이션 중...")
    try:
        # yolo_runs 생성
        yolo_run_id = uuid.uuid4()
        forbidden_mask_url = asset_url.replace(".png", "_forbidden_mask.png")  # 시뮬레이션용
        db.execute(
            text("""
                INSERT INTO yolo_runs (
                    yolo_run_id, job_id, image_asset_id, forbidden_mask_url, 
                    model_name, detection_count, created_at, updated_at
                ) VALUES (
                    :yolo_run_id, :job_id, :image_asset_id, :forbidden_mask_url,
                    :model_name, :detection_count, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "yolo_run_id": yolo_run_id,
                "job_id": job_uuid,
                "image_asset_id": image_asset_id,
                "forbidden_mask_url": forbidden_mask_url,
                "model_name": "yolov8x-seg.pt",
                "detection_count": 2
            }
        )
        
        # detections 생성 (시뮬레이션용 - 실제로는 YOLO가 생성)
        detection1_id = uuid.uuid4()
        detection2_id = uuid.uuid4()
        
        # 이미지 크기에 맞춰 정규화된 좌표 (예시)
        img_width, img_height = image.size
        box1 = [0.1 * img_width, 0.1 * img_height, 0.4 * img_width, 0.4 * img_height]  # [x1, y1, x2, y2]
        box2 = [0.5 * img_width, 0.5 * img_height, 0.9 * img_width, 0.9 * img_height]
        
        import json
        db.execute(
            text("""
                INSERT INTO detections (
                    detection_id, job_id, image_asset_id, box, label, score,
                    created_at, updated_at
                ) VALUES (
                    :detection_id, :job_id, :image_asset_id, CAST(:box AS jsonb), :label, :score,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "detection_id": detection1_id,
                "job_id": job_uuid,
                "image_asset_id": image_asset_id,
                "box": json.dumps(box1),
                "label": "person",
                "score": 0.95
            }
        )
        
        db.execute(
            text("""
                INSERT INTO detections (
                    detection_id, job_id, image_asset_id, box, label, score,
                    created_at, updated_at
                ) VALUES (
                    :detection_id, :job_id, :image_asset_id, CAST(:box AS jsonb), :label, :score,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "detection_id": detection2_id,
                "job_id": job_uuid,
                "image_asset_id": image_asset_id,
                "box": json.dumps(box2),
                "label": "food",
                "score": 0.88
            }
        )
        
        db.commit()
        print(f"✓ YOLO 결과 시뮬레이션 완료:")
        print(f"  - YOLO Run ID: {yolo_run_id}")
        print(f"  - Detection Count: 2")
        print(f"  - Forbidden Mask URL: {forbidden_mask_url}")
    except Exception as e:
        print(f"  ⚠ YOLO 결과 시뮬레이션 중 오류: {e}")
        db.rollback()
        raise
    
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


def test_planner(job_id: str, tenant_id: str, api_url: str = "http://localhost:8011") -> dict:
    """Planner API 테스트"""
    print("\n" + "=" * 60)
    print("Planner API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/planner"
    
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
        print(f"  - Proposals 개수: {len(result.get('proposals', []))}")
        print(f"  - Avoid 영역: {result.get('avoid', 'N/A')}")
        
        if result.get('proposals'):
            print(f"\n  첫 번째 Proposal:")
            first_prop = result['proposals'][0]
            print(f"    - Proposal ID: {first_prop.get('proposal_id')}")
            print(f"    - Source: {first_prop.get('source')}")
            print(f"    - XYWH: {first_prop.get('xywh')}")
            print(f"    - Score: {first_prop.get('score')}")
        
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
        job = check_job_status(db, job_id, expected_step="planner", expected_status="done")
        if not job:
            return False
        
        # job_inputs 확인
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if job_input:
            print(f"\n  Job Input:")
            print(f"    - Image Asset ID: {job_input.img_asset_id}")
        
        # yolo_runs 확인
        yolo_run = db.query(YOLORun).filter(YOLORun.job_id == uuid.UUID(job_id)).first()
        if yolo_run:
            print(f"\n  YOLO Run:")
            print(f"    - YOLO Run ID: {yolo_run.yolo_run_id}")
            print(f"    - Forbidden Mask URL: {yolo_run.forbidden_mask_url}")
            print(f"    - Detection Count: {yolo_run.detection_count}")
        
        # detections 확인
        detections = db.query(Detection).filter(Detection.job_id == uuid.UUID(job_id)).all()
        if detections:
            print(f"\n  Detections: {len(detections)}개")
            for i, det in enumerate(detections[:3]):  # 최대 3개만 출력
                print(f"    Detection {i+1}: {det.label} (score: {det.score:.2f})")
        
        # planner_proposals 확인
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if job_input:
            image_asset_id = job_input.img_asset_id
            planner_proposals = db.query(PlannerProposal).filter(
                PlannerProposal.image_asset_id == image_asset_id
            ).order_by(PlannerProposal.created_at.desc()).all()
            
            if planner_proposals:
                print(f"\n  Planner Proposals: {len(planner_proposals)}개")
                latest_proposal = planner_proposals[0]
                print(f"    - Proposal ID: {latest_proposal.proposal_id}")
                print(f"    - Image Asset ID: {latest_proposal.image_asset_id}")
                
                if latest_proposal.layout:
                    layout = latest_proposal.layout
                    if isinstance(layout, dict):
                        proposals_count = len(layout.get('proposals', []))
                        print(f"    - Layout에 저장된 Proposals 개수: {proposals_count}")
                        print(f"    - Avoid 영역: {layout.get('avoid', 'N/A')}")
            else:
                print(f"\n  ⚠ Planner Proposals를 찾을 수 없습니다")
        
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
    
    parser = argparse.ArgumentParser(description="Planner API DB 연동 테스트")
    parser.add_argument("--job-id", type=str, default=None,
                       help="테스트할 job_id (없으면 새로 생성)")
    parser.add_argument("--tenant-id", default="test_planner_tenant",
                       help="테스트용 tenant_id")
    parser.add_argument("--image-path", type=str, default=None,
                       help="사용할 이미지 경로")
    parser.add_argument("--api-url", default="http://localhost:8011",
                       help="API 서버 URL")
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
            # 새 job 생성 (yolo_detect 완료 상태)
            test_data = setup_test_job_for_planner(db, args.tenant_id, args.image_path)
            job_id = test_data["job_id"]
            tenant_id = test_data["tenant_id"]
        
        # 초기 상태 확인
        print("\n" + "=" * 60)
        print("초기 Job 상태 확인")
        print("=" * 60)
        check_job_status(db, job_id, expected_step="yolo_detect", expected_status="done")
        
        # Planner 테스트
        planner_result = test_planner(job_id, tenant_id, args.api_url)
        
        # Planner 이후 상태 확인
        print("\n" + "=" * 60)
        print("Planner 이후 Job 상태 확인")
        print("=" * 60)
        check_job_status(db, job_id, expected_step="planner", expected_status="done")
        
        # 최종 DB 레코드 확인
        verify_db_records(db, job_id)
        
        print("\n" + "=" * 60)
        print("✓ 테스트 완료!")
        print("=" * 60)
        print(f"\nJob ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        print(f"Proposals 개수: {len(planner_result.get('proposals', []))}")
        
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


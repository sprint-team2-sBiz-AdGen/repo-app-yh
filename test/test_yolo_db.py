"""YOLO DB 연동 테스트 스크립트"""
import sys
import os
import uuid
import requests
from datetime import datetime
from typing import List

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정 (모듈 import 전에 설정해야 함)
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

# 환경 변수 설정 후 모듈 import
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, ImageAsset, Job, JobInput, Detection, Base
from utils import save_asset, abs_from_url
from config import ASSETS_DIR, PART_NAME
import logging

logger = logging.getLogger(__name__)


def setup_test_data(db: Session, tenant_id: str, image_path: str = None, job_id: str = None) -> dict:
    """
    테스트에 필요한 DB 데이터 생성
    
    Args:
        db: DB 세션
        tenant_id: 테넌트 ID
        image_path: 이미지 경로 (None이면 기본 이미지 사용)
        job_id: 기존 job_id (None이면 새로 생성)
    
    Returns:
        dict: {
            "tenant_id": str,
            "job_id": str (UUID),
            "image_asset_id": str (UUID),
            "asset_url": str,
            "image_path": str
        }
    """
    print("\n" + "=" * 60)
    print("테스트 데이터 준비")
    print("=" * 60)
    
    # 1. 테스트 이미지 생성 또는 기존 이미지 사용
    if image_path and os.path.exists(image_path):
        print(f"\n[1/4] 기존 이미지 사용: {image_path}")
        image = Image.open(image_path)
        # asset_url 생성 (절대 경로에서 상대 경로로 변환)
        if image_path.startswith(ASSETS_DIR):
            rel_path = image_path[len(ASSETS_DIR):].lstrip("/")
            asset_url = f"/assets/{rel_path}"
        else:
            # 새로 저장
            asset_meta = save_asset(tenant_id, "test_yolo", image, ".png")
            asset_url = asset_meta["url"]
            image_path = abs_from_url(asset_url)
    else:
        print(f"\n[1/4] 테스트 이미지 생성 중...")
        # 간단한 테스트 이미지 생성
        image = Image.new("RGB", (512, 512), color=(255, 100, 50))
        asset_meta = save_asset(tenant_id, "test_yolo", image, ".png")
        asset_url = asset_meta["url"]
        image_path = abs_from_url(asset_url)
        print(f"✓ 이미지 생성 및 저장 완료: {asset_url}")
    
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Image Path: {image_path}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # 2. tenants 테이블 확인 및 생성
    print(f"\n[2/4] tenant 확인/생성 중...")
    try:
        tenant_check = db.execute(
            text("SELECT tenant_id FROM tenants WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        ).first()
        
        if not tenant_check:
            print(f"  tenant '{tenant_id}'가 없어서 생성 중...")
            try:
                db.execute(
                    text("INSERT INTO tenants (tenant_id, display_name) VALUES (:tenant_id, :display_name)"),
                    {"tenant_id": tenant_id, "display_name": f"Test Tenant - {tenant_id}"}
                )
                db.commit()
                print(f"✓ tenant '{tenant_id}' 생성 완료")
            except Exception as e:
                print(f"  ⚠ tenant 생성 실패: {e}")
                db.rollback()
                raise
        else:
            print(f"✓ tenant '{tenant_id}' 확인 완료")
    except Exception as e:
        print(f"  ⚠ tenant 확인 중 오류: {e}")
        raise
    
    # 3. image_assets 테이블에 레코드 확인 또는 생성
    print(f"\n[3/4] image_assets 레코드 확인/생성 중...")
    
    # 먼저 조회
    existing = db.execute(
        text("SELECT image_asset_id FROM image_assets WHERE image_url = :url AND tenant_id = :tenant_id"),
        {"url": asset_url, "tenant_id": tenant_id}
    ).first()
    
    if existing:
        image_asset_id = existing[0]
        print(f"✓ 기존 image_asset 레코드 발견:")
        print(f"  - Image Asset ID: {image_asset_id}")
    else:
        print(f"  새로운 image_asset 레코드 생성 중...")
        image_asset_id = uuid.uuid4()
        
        # Raw SQL로 직접 INSERT
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
        print(f"✓ image_asset 레코드 생성 완료:")
        print(f"  - Image Asset ID: {image_asset_id}")
    
    # 4. jobs 및 job_inputs 테이블에 레코드 생성
    print(f"\n[4/4] jobs 및 job_inputs 레코드 확인/생성 중...")
    
    if job_id:
        try:
            job_uuid = uuid.UUID(job_id)
            existing_job = db.execute(
                text("SELECT job_id FROM jobs WHERE job_id = :job_id"),
                {"job_id": job_uuid}
            ).first()
            
            if existing_job:
                print(f"✓ 기존 job 레코드 발견: {job_id}")
                # job_inputs 확인
                existing_job_input = db.execute(
                    text("SELECT job_id FROM job_inputs WHERE job_id = :job_id"),
                    {"job_id": job_uuid}
                ).first()
                
                if not existing_job_input:
                    # job_inputs 생성
                    db.execute(
                        text("""
                            INSERT INTO job_inputs (
                                job_id, img_asset_id, created_at, updated_at
                            ) VALUES (
                                :job_id, :img_asset_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                        """),
                        {
                            "job_id": job_uuid,
                            "img_asset_id": image_asset_id
                        }
                    )
                    db.commit()
                    print(f"✓ job_inputs 레코드 생성 완료")
                else:
                    print(f"✓ 기존 job_inputs 레코드 발견")
            else:
                print(f"❌ Job을 찾을 수 없습니다: {job_id}")
                raise ValueError(f"Job not found: {job_id}")
        except ValueError as e:
            if "not found" in str(e):
                raise
            # UUID 형식 오류
            print(f"❌ Invalid job_id format: {job_id}")
            raise
    else:
        # 새 job 생성
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
                "status": "queued",
                "current_step": None
            }
        )
        
        # job_inputs 생성
        db.execute(
            text("""
                INSERT INTO job_inputs (
                    job_id, img_asset_id, created_at, updated_at
                ) VALUES (
                    :job_id, :img_asset_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "job_id": job_uuid,
                "img_asset_id": image_asset_id
            }
        )
        db.commit()
        print(f"✓ job 및 job_inputs 레코드 생성 완료:")
        print(f"  - Job ID: {job_uuid}")
    
    return {
        "tenant_id": tenant_id,
        "job_id": str(job_uuid),
        "image_asset_id": str(image_asset_id),
        "asset_url": asset_url,
        "image_path": image_path
    }


def test_yolo_api(job_id: str, tenant_id: str, asset_url: str = None, api_url: str = "http://localhost:8011") -> dict:
    """
    YOLO API 테스트
    
    Args:
        job_id: Job ID
        tenant_id: Tenant ID
        asset_url: Asset URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
        api_url: API 서버 URL
    
    Returns:
        dict: API 응답 결과
    """
    print("\n" + "=" * 60)
    print("YOLO API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/yolo/detect"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id
    }
    
    if asset_url:
        request_data["asset_url"] = asset_url
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    if asset_url:
        print(f"  - Asset URL: {asset_url}")
    else:
        print(f"  - Asset URL: (job_inputs에서 가져옴)")
    
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
        print(f"  - Detections: {len(result.get('detections', []))}개")
        
        if result.get('boxes'):
            print(f"\n감지된 박스 정보:")
            for i, box in enumerate(result.get('boxes', [])[:5]):  # 최대 5개만 출력
                print(f"  박스 {i+1}: {box}")
            if len(result.get('boxes', [])) > 5:
                print(f"  ... 외 {len(result.get('boxes', [])) - 5}개")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        print(f"\n❌ 요청 오류: {e}")
        raise
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        raise


def verify_db_records(db: Session, job_id: str, detection_ids: List[str]) -> bool:
    """
    DB 레코드 확인
    
    Args:
        db: DB 세션
        job_id: Job ID
        detection_ids: Detection ID 리스트
    
    Returns:
        bool: 확인 성공 여부
    """
    print("\n" + "=" * 60)
    print("DB 레코드 확인")
    print("=" * 60)
    
    try:
        # jobs 확인
        job = db.query(Job).filter(Job.job_id == uuid.UUID(job_id)).first()
        
        if job:
            print(f"\n✓ jobs 레코드 발견:")
            print(f"  - Job ID: {job.job_id}")
            print(f"  - Tenant ID: {job.tenant_id}")
            print(f"  - Status: {job.status}")
            print(f"  - Current Step: {job.current_step}")
            print(f"  - Created At: {job.created_at}")
        else:
            print(f"\n❌ jobs 레코드를 찾을 수 없습니다: {job_id}")
            return False
        
        # job_inputs 확인
        job_input = db.query(JobInput).filter(
            JobInput.job_id == uuid.UUID(job_id)
        ).first()
        
        if job_input:
            print(f"\n✓ job_inputs 레코드 발견:")
            print(f"  - Job ID: {job_input.job_id}")
            print(f"  - Image Asset ID: {job_input.img_asset_id}")
            print(f"  - Created At: {job_input.created_at}")
        else:
            print(f"\n⚠ job_inputs 레코드를 찾을 수 없습니다: {job_id}")
        
        # detections 확인
        if detection_ids:
            print(f"\n✓ detections 레코드 확인:")
            print(f"  - Detection IDs 개수: {len(detection_ids)}")
            
            for i, detection_id_str in enumerate(detection_ids[:5]):  # 최대 5개만 출력
                try:
                    detection_id = uuid.UUID(detection_id_str)
                    detection = db.query(Detection).filter(
                        Detection.detection_id == detection_id
                    ).first()
                    
                    if detection:
                        print(f"\n  Detection {i+1}:")
                        print(f"    - Detection ID: {detection.detection_id}")
                        print(f"    - Image Asset ID: {detection.image_asset_id}")
                        print(f"    - Label: {detection.label}")
                        print(f"    - Score: {detection.score}")
                        print(f"    - Box: {detection.box}")
                        print(f"    - Created At: {detection.created_at}")
                    else:
                        print(f"\n  ⚠ Detection {i+1}을 찾을 수 없습니다: {detection_id_str}")
                except ValueError:
                    print(f"\n  ⚠ Invalid detection_id format: {detection_id_str}")
            
            if len(detection_ids) > 5:
                print(f"\n  ... 외 {len(detection_ids) - 5}개 detection")
        else:
            print(f"\n⚠ detection_ids가 비어있습니다")
        
        print(f"\n✓ 모든 DB 레코드 확인 완료!")
        return True
        
    except Exception as e:
        print(f"\n❌ DB 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 테스트 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="YOLO DB 연동 테스트")
    parser.add_argument("--job-id", type=str, default=None,
                       help="테스트할 job_id (없으면 setup_previous_stage.py를 먼저 실행하세요)")
    parser.add_argument("--tenant-id", default="test_yolo_tenant",
                       help="테스트용 tenant_id (기본: test_yolo_tenant, job_id가 있으면 생략 가능)")
    parser.add_argument("--image-path", type=str, default=None,
                       help="사용할 이미지 경로 (없으면 기본 이미지 사용, job_id가 있으면 무시됨)")
    parser.add_argument("--skip-api", action="store_true",
                       help="API 호출 건너뛰기 (DB 데이터만 준비)")
    parser.add_argument("--api-url", default="http://localhost:8011",
                       help="API 서버 URL (기본: http://localhost:8011)")
    args = parser.parse_args()
    
    # DB 연결
    db = None
    try:
        db = SessionLocal()
        print("✓ DB 연결 성공")
    except Exception as e:
        print(f"❌ DB 연결 실패: {e}")
        print("  DB 연결 정보를 확인하세요.")
        sys.exit(1)
    
    try:
        # job_id가 제공된 경우 (준비단계.py에서 생성된 job 사용)
        if args.job_id:
            print(f"\n✓ 제공된 job_id 사용: {args.job_id}")
            print(f"  (job_inputs에서 이미지를 자동으로 가져옵니다)")
            
            # job에서 tenant_id 가져오기
            job = db.execute(
                text("SELECT tenant_id FROM jobs WHERE job_id = :job_id"),
                {"job_id": uuid.UUID(args.job_id)}
            ).first()
            
            if not job:
                print(f"❌ Job을 찾을 수 없습니다: {args.job_id}")
                sys.exit(1)
            
            tenant_id = job[0]
            print(f"  - Tenant ID: {tenant_id}")
            
            # 2. API 테스트 (건너뛰기 옵션이 없으면)
            if not args.skip_api:
                result = test_yolo_api(
                    job_id=args.job_id,
                    tenant_id=tenant_id
                )
                
                # 3. DB 레코드 확인
                if result:
                    verify_db_records(
                        db,
                        result.get("job_id"),
                        result.get("detection_ids", [])
                    )
            else:
                print("\n" + "=" * 60)
                print("API 호출 건너뛰기 (job_id만 확인됨)")
                print("=" * 60)
                print(f"\nJob ID: {args.job_id}")
                print(f"Tenant ID: {tenant_id}")
                print(f"\n다음 명령으로 API를 테스트할 수 있습니다:")
                print(f"  python3 test/test_yolo_db.py --job-id {args.job_id} --tenant-id {tenant_id}")
        else:
            # job_id가 없는 경우: 기존 방식 (테스트 데이터 생성)
            print(f"\n⚠ job_id가 제공되지 않았습니다. 기존 방식으로 테스트 데이터를 생성합니다.")
            print(f"  (setup_previous_stage.py를 먼저 실행하여 job을 생성하는 것을 권장합니다)")
            
            # 1. 테스트 데이터 준비
            test_data = setup_test_data(db, args.tenant_id, args.image_path)
            
            # 2. API 테스트 (건너뛰기 옵션이 없으면)
            if not args.skip_api:
                result = test_yolo_api(
                    job_id=test_data["job_id"],
                    tenant_id=test_data["tenant_id"],
                    asset_url=test_data["asset_url"]  # Optional, job_inputs에서 가져올 수 있음
                )
                
                # 3. DB 레코드 확인
                if result:
                    verify_db_records(
                        db,
                        result.get("job_id"),
                        result.get("detection_ids", [])
                    )
            else:
                print("\n" + "=" * 60)
                print("API 호출 건너뛰기 (DB 데이터만 준비됨)")
                print("=" * 60)
                print(f"\n다음 명령으로 API를 테스트할 수 있습니다:")
                print(f"  curl -X POST {args.api_url}/api/yh/yolo/detect \\")
                print(f"    -H 'Content-Type: application/json' \\")
                print(f"    -d '{{")
                print(f"      \"job_id\": \"{test_data['job_id']}\",")
                print(f"      \"tenant_id\": \"{test_data['tenant_id']}\"")
                print(f"    }}'")
        
        print("\n" + "=" * 60)
        print("✓ 테스트 완료!")
        print("=" * 60)
        
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


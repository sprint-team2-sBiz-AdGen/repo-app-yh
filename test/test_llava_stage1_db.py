"""LLaVa Stage 1 DB 연동 테스트 스크립트"""
import sys
import os
import uuid
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정 (모듈 import 전에 설정해야 함)
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

# 환경 변수 설정 후 모듈 import
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import and_
from database import SessionLocal, ImageAsset, Job, JobInput, VLMTrace, Base
from utils import save_asset, abs_from_url
from config import ASSETS_DIR, PART_NAME
import logging

logger = logging.getLogger(__name__)


def setup_test_data(db: Session, tenant_id: str, image_path: str = None) -> dict:
    """
    테스트에 필요한 DB 데이터 생성
    
    Args:
        db: DB 세션
        tenant_id: 테넌트 ID
        image_path: 이미지 경로 (None이면 기본 이미지 사용)
    
    Returns:
        dict: {
            "tenant_id": str,
            "image_asset_id": str (UUID),
            "asset_url": str,
            "image_path": str
        }
    """
    # 기본 이미지 경로 설정
    if image_path is None:
        default_image_path = "/opt/feedlyai/assets/yh/tenants/test_llava_tenant/test_llava/2025/11/24/7e330c4b-5deb-484b-b7d4-1a1945ad0237.png"
        if os.path.exists(default_image_path):
            image_path = default_image_path
    """
    테스트에 필요한 DB 데이터 생성
    
    Returns:
        dict: {
            "tenant_id": str,
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
        print(f"\n[1/3] 기존 이미지 사용: {image_path}")
        image = Image.open(image_path)
        # asset_url 생성 (절대 경로에서 상대 경로로 변환)
        if image_path.startswith(ASSETS_DIR):
            rel_path = image_path[len(ASSETS_DIR):].lstrip("/")
            asset_url = f"/assets/{rel_path}"
        else:
            # 새로 저장
            asset_meta = save_asset(tenant_id, "test_llava", image, ".png")
            asset_url = asset_meta["url"]
            image_path = abs_from_url(asset_url)
    else:
        print(f"\n[1/3] 테스트 이미지 생성 중...")
        # 간단한 테스트 이미지 생성
        image = Image.new("RGB", (512, 512), color=(255, 100, 50))
        asset_meta = save_asset(tenant_id, "test_llava", image, ".png")
        asset_url = asset_meta["url"]
        image_path = abs_from_url(asset_url)
        print(f"✓ 이미지 생성 및 저장 완료: {asset_url}")
    
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Image Path: {image_path}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # 2. tenants 테이블 확인 및 생성 (FK 제약이 있을 수 있음)
    print(f"\n[2/3] tenant 확인/생성 중...")
    from sqlalchemy import text
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
    
    # 3. image_assets 테이블에 레코드 확인 또는 생성 (raw SQL 사용 - FK 제약 회피)
    print(f"\n[2/3] image_assets 레코드 확인/생성 중...")
    from sqlalchemy import text
    
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
        image_asset_uid = uuid.uuid4().hex
        
        # Raw SQL로 직접 INSERT (FK 제약 회피)
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
        print(f"✓ image_asset 레코드 생성 완료:")
        print(f"  - Image Asset ID: {image_asset_id}")
    
    # 4. jobs 테이블에 테스트용 job 생성
    print(f"\n[3/3] job 확인/생성 중...")
    from sqlalchemy import text
    
    # 기존 job이 있는지 확인 (같은 tenant_id로)
    existing_job = db.execute(
        text("SELECT job_id FROM jobs WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT 1"),
        {"tenant_id": tenant_id}
    ).first()
    
    if existing_job:
        job_id = existing_job[0]
        print(f"✓ 기존 job 레코드 사용:")
        print(f"  - Job ID: {job_id}")
    else:
        print(f"  새로운 job 레코드 생성 중...")
        job_id = uuid.uuid4()
        db.execute(
            text("""
                INSERT INTO jobs (job_id, tenant_id, status, current_step, created_at, updated_at)
                VALUES (:job_id, :tenant_id, 'queued', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "job_id": job_id,
                "tenant_id": tenant_id
            }
        )
        db.commit()
        print(f"✓ job 레코드 생성 완료:")
        print(f"  - Job ID: {job_id}")
    
    return {
        "tenant_id": tenant_id,
        "image_asset_id": str(image_asset_id),
        "asset_url": asset_url,
        "image_path": image_path,
        "job_id": str(job_id)
    }


def test_llava_stage1_api(job_id: str, tenant_id: str, asset_url: str, ad_copy_text: str = None):
    """
    LLaVa Stage 1 API 테스트 (실제 API 호출)
    """
    print("\n" + "=" * 60)
    print("LLaVa Stage 1 API 테스트")
    print("=" * 60)
    
    import requests
    
    # API 엔드포인트
    api_url = "http://localhost:8011/api/yh/llava/stage1/validate"
    
    # 요청 데이터
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "asset_url": asset_url,
        "ad_copy_text": ad_copy_text
    }
    
    print(f"\n요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Ad Copy Text: {ad_copy_text or '(없음)'}")
    
    print(f"\nAPI 호출 중: {api_url}")
    try:
        response = requests.post(api_url, json=request_data, timeout=300)  # 5분 타임아웃
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 결과:")
        print(f"  - Job ID: {result.get('job_id')}")
        print(f"  - VLM Trace ID: {result.get('vlm_trace_id')}")
        print(f"  - Is Valid: {result.get('is_valid')}")
        print(f"  - Image Quality OK: {result.get('image_quality_ok')}")
        print(f"  - Relevance Score: {result.get('relevance_score')}")
        print(f"  - Issues: {result.get('issues')}")
        print(f"  - Recommendations: {result.get('recommendations')}")
        
        print(f"\n분석 결과 (일부):")
        analysis = result.get('analysis', '')
        if analysis:
            preview = analysis[:200] + "..." if len(analysis) > 200 else analysis
            print(f"  {preview}")
        
        return result
        
    except requests.exceptions.ConnectionError:
        print(f"\n❌ 오류: API 서버에 연결할 수 없습니다.")
        print(f"  서버가 실행 중인지 확인하세요: uvicorn main:app --host 0.0.0.0 --port 8011")
        return None
    except requests.exceptions.Timeout:
        print(f"\n❌ 오류: API 호출 시간 초과 (5분)")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        print(f"  응답: {response.text if 'response' in locals() else 'N/A'}")
        return None
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


def verify_db_records(db: Session, job_id: str, vlm_trace_id: str):
    """
    DB에 저장된 레코드 확인
    """
    print("\n" + "=" * 60)
    print("DB 레코드 확인")
    print("=" * 60)
    
    try:
        # jobs 확인
        job = db.query(Job).filter(
            Job.job_id == uuid.UUID(job_id)
        ).first()
        
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
            print(f"  - Desc Eng: {job_input.desc_eng[:100] if job_input.desc_eng else '(없음)'}...")
            print(f"  - Created At: {job_input.created_at}")
        else:
            print(f"\n⚠ job_inputs 레코드를 찾을 수 없습니다: {job_id}")
        
        # vlm_traces 확인
        vlm_trace = db.query(VLMTrace).filter(
            VLMTrace.vlm_trace_id == uuid.UUID(vlm_trace_id)
        ).first()
        
        if vlm_trace:
            print(f"\n✓ vlm_traces 레코드 발견:")
            print(f"  - VLM Trace ID: {vlm_trace.vlm_trace_id}")
            print(f"  - Job ID: {vlm_trace.job_id}")
            print(f"  - Provider: {vlm_trace.provider}")
            print(f"  - Operation Type: {vlm_trace.operation_type}")
            print(f"  - Response (JSONB):")
            if vlm_trace.response:
                response = vlm_trace.response
                print(f"    - is_valid: {response.get('is_valid')}")
                print(f"    - relevance_score: {response.get('relevance_score')}")
                print(f"    - issues: {response.get('issues')}")
            print(f"  - Created At: {vlm_trace.created_at}")
        else:
            print(f"\n❌ vlm_traces 레코드를 찾을 수 없습니다: {vlm_trace_id}")
            return False
        
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
    
    parser = argparse.ArgumentParser(description="LLaVa Stage 1 DB 연동 테스트")
    parser.add_argument("--tenant-id", default="test_llava_tenant",
                       help="테스트용 tenant_id (기본: test_llava_tenant)")
    parser.add_argument("--image-path", type=str, default=None,
                       help="사용할 이미지 경로 (없으면 기본 이미지 사용: /opt/feedlyai/assets/yh/tenants/test_llava_tenant/test_llava/2025/11/24/7e330c4b-5deb-484b-b7d4-1a1945ad0237.png)")
    parser.add_argument("--ad-copy", type=str, default="Spicy Pork Kimchi Stew – one spoon and you'll forget everything else.",
                       help="광고 문구 텍스트")
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
        # 1. 테스트 데이터 준비
        test_data = setup_test_data(db, args.tenant_id, args.image_path)
        
        # 2. API 테스트 (건너뛰기 옵션이 없으면)
        if not args.skip_api:
            result = test_llava_stage1_api(
                job_id=test_data["job_id"],
                tenant_id=test_data["tenant_id"],
                asset_url=test_data["asset_url"],
                ad_copy_text=args.ad_copy
            )
            
            # 3. DB 레코드 확인
            if result:
                verify_db_records(
                    db,
                    result.get("job_id"),
                    result.get("vlm_trace_id")
                )
        else:
            print("\n" + "=" * 60)
            print("API 호출 건너뛰기 (DB 데이터만 준비됨)")
            print("=" * 60)
            print(f"\n다음 명령으로 API를 테스트할 수 있습니다:")
            print(f"  curl -X POST {args.api_url}/api/yh/llava/stage1/validate \\")
            print(f"    -H 'Content-Type: application/json' \\")
            print(f"    -d '{{")
            print(f"      \"job_id\": \"{test_data['job_id']}\",")
            print(f"      \"tenant_id\": \"{test_data['tenant_id']}\",")
            print(f"      \"asset_url\": \"{test_data['asset_url']}\",")
            print(f"      \"ad_copy_text\": \"{args.ad_copy}\"")
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


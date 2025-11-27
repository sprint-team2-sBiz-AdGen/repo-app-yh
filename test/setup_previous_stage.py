"""LLaVa Stage 1 테스트를 위한 이전 단계 완료 상태 DB 데이터 생성 스크립트"""
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
from sqlalchemy import text
from database import SessionLocal, ImageAsset, Job, JobInput, Tenant
from utils import save_asset, abs_from_url
from config import ASSETS_DIR
import logging

logger = logging.getLogger(__name__)


def setup_previous_stage_data(
    db: Session,
    tenant_id: str = "test_llava_tenant",
    image_path: str = None,
    ad_copy_text: str = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
) -> dict:
    """
    이전 단계(img_gen)가 완료된 상태의 DB 데이터 생성
    
    Args:
        db: DB 세션
        tenant_id: 테넌트 ID
        image_path: 이미지 경로 (None이면 기본 이미지 사용)
        ad_copy_text: 광고 문구 텍스트
    
    Returns:
        dict: {
            "job_id": str (UUID),
            "tenant_id": str,
            "image_asset_id": str (UUID),
            "asset_url": str,
            "ad_copy_text": str
        }
    """
    print("\n" + "=" * 60)
    print("이전 단계(img_gen) 완료 상태 DB 데이터 생성")
    print("=" * 60)
    
    # 1. tenants 테이블 확인/생성
    print(f"\n[1/4] tenant 확인/생성 중...")
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
    
    # 2. 이미지 준비 및 image_assets 테이블에 레코드 생성
    print(f"\n[2/4] 이미지 및 image_assets 레코드 준비 중...")
    
    # 기본 이미지 경로 설정
    if image_path is None:
        default_image_path = "/opt/feedlyai/assets/yh/tenants/test_llava_tenant/test_llava/2025/11/24/7e330c4b-5deb-484b-b7d4-1a1945ad0237.png"
        if os.path.exists(default_image_path):
            image_path = default_image_path
    
    if image_path and os.path.exists(image_path):
        print(f"  기존 이미지 사용: {image_path}")
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
        print(f"  테스트 이미지 생성 중...")
        # 간단한 테스트 이미지 생성
        image = Image.new("RGB", (512, 512), color=(255, 100, 50))
        asset_meta = save_asset(tenant_id, "test_llava", image, ".png")
        asset_url = asset_meta["url"]
        image_path = abs_from_url(asset_url)
        print(f"✓ 이미지 생성 및 저장 완료: {asset_url}")
    
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Image Path: {image_path}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # image_assets 테이블에 레코드 확인/생성
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
                "image_type": "generated",  # img_gen 단계에서 생성된 이미지
                "image_url": asset_url,
                "width": image.size[0],
                "height": image.size[1],
                "tenant_id": tenant_id
            }
        )
        db.commit()
        print(f"✓ image_asset 레코드 생성 완료:")
        print(f"  - Image Asset ID: {image_asset_id}")
    
    # 3. jobs 테이블에 이전 단계 완료 상태의 job 생성
    print(f"\n[3/4] jobs 레코드 생성 중 (current_step='img_gen', status='done')...")
    job_id = uuid.uuid4()
    
    db.execute(
        text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step, version, created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, 'done', 'img_gen', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "job_id": job_id,
            "tenant_id": tenant_id
        }
    )
    db.commit()
    print(f"✓ job 레코드 생성 완료:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Status: done")
    print(f"  - Current Step: img_gen")
    
    # 4. job_inputs 테이블에 입력 데이터 생성
    print(f"\n[4/4] job_inputs 레코드 생성 중...")
    
    db.execute(
        text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, desc_eng, created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :desc_eng, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """),
        {
            "job_id": job_id,
            "img_asset_id": image_asset_id,
            "desc_eng": ad_copy_text
        }
    )
    db.commit()
    print(f"✓ job_inputs 레코드 생성 완료:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Image Asset ID: {image_asset_id}")
    print(f"  - Ad Copy Text: {ad_copy_text[:50]}..." if len(ad_copy_text) > 50 else f"  - Ad Copy Text: {ad_copy_text}")
    
    print("\n" + "=" * 60)
    print("✓ 이전 단계 완료 상태 DB 데이터 생성 완료!")
    print("=" * 60)
    print(f"\n생성된 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Image Asset ID: {image_asset_id}")
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Ad Copy Text: {ad_copy_text}")
    print(f"\n다음 단계: LLaVa Stage 1 API를 호출하세요:")
    print(f"  python3 test/test_llava_stage1_db.py --job-id {job_id} --tenant-id {tenant_id}")
    
    return {
        "job_id": str(job_id),
        "tenant_id": tenant_id,
        "image_asset_id": str(image_asset_id),
        "asset_url": asset_url,
        "ad_copy_text": ad_copy_text
    }


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="이전 단계(img_gen) 완료 상태 DB 데이터 생성")
    parser.add_argument("--tenant-id", default="test_llava_tenant",
                       help="테스트용 tenant_id (기본: test_llava_tenant)")
    parser.add_argument("--image-path", type=str, default=None,
                       help="사용할 이미지 경로 (없으면 기본 이미지 사용)")
    parser.add_argument("--ad-copy", type=str, 
                       default="Spicy Pork Kimchi Stew – one spoon and you'll forget everything else.",
                       help="광고 문구 텍스트")
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
        result = setup_previous_stage_data(
            db=db,
            tenant_id=args.tenant_id,
            image_path=args.image_path,
            ad_copy_text=args.ad_copy
        )
        
        print("\n" + "=" * 60)
        print("✓ 준비 완료!")
        print("=" * 60)
        print(f"\n생성된 Job ID: {result['job_id']}")
        print(f"\n이제 LLaVa Stage 1 API를 테스트할 수 있습니다:")
        print(f"  python3 test/test_llava_stage1_db.py --job-id {result['job_id']}")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    main()


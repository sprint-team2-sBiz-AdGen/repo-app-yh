"""Asset 저장 및 DB 작업 테스트 스크립트"""
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
from utils import save_asset, abs_from_url
from database import SessionLocal, TestAsset, Base
from config import ASSETS_DIR, PART_NAME
import logging

logger = logging.getLogger(__name__)


def test_save_asset_and_db():
    """Asset 저장 및 DB insert/delete 테스트"""
    
    print("=" * 60)
    print("Asset 저장 및 DB 작업 테스트")
    print("=" * 60)
    
    # 테스트 데이터
    tenant_id = "test_tenant_db"
    kind = "test_image"
    
    # 테스트용 이미지 생성
    print("\n[1/5] 테스트 이미지 생성 중...")
    test_image = Image.new("RGB", (512, 512), color="red")
    print(f"✓ 이미지 생성 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # Asset 저장
    print("\n[2/5] Asset 폴더에 이미지 저장 중...")
    try:
        asset_meta = save_asset(tenant_id, kind, test_image, ".png")
        asset_id = asset_meta["asset_id"]
        asset_url = asset_meta["url"]
        asset_path = abs_from_url(asset_url)
        
        print(f"✓ Asset 저장 완료:")
        print(f"  - Asset ID: {asset_id}")
        print(f"  - Asset URL: {asset_url}")
        print(f"  - Asset Path: {asset_path}")
        print(f"  - Width: {asset_meta['width']}, Height: {asset_meta['height']}")
        
        # 파일 존재 확인
        if os.path.exists(asset_path):
            file_size = os.path.getsize(asset_path) / 1024  # KB
            print(f"  - 파일 크기: {file_size:.2f} KB")
            print(f"  ✓ 파일이 정상적으로 저장되었습니다.")
        else:
            print(f"  ❌ 오류: 파일이 저장되지 않았습니다!")
            return False
            
    except Exception as e:
        print(f"❌ Asset 저장 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # DB 연결 확인
    print("\n[3/5] DB 연결 및 테이블 확인 중...")
    db = None
    try:
        db = SessionLocal()
        
        # 테이블 존재 확인
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        print(f"✓ DB 연결 성공")
        print(f"  - 사용 가능한 테이블: {', '.join(tables)}")
        
        # TestAsset 테이블이 있는지 확인
        if "test_assets" in tables:
            print(f"  ✓ test_assets 테이블 존재 확인")
        else:
            print(f"  ⚠ 경고: test_assets 테이블이 없습니다. 테이블을 생성합니다...")
            Base.metadata.create_all(db.bind)
            print(f"  ✓ 테이블 생성 완료")
        
    except Exception as e:
        print(f"⚠ DB 연결 실패 (DB 테스트는 건너뜁니다): {e}")
        print(f"  Asset 저장 테스트는 계속 진행합니다...")
        db = None
    
    # DB Insert 테스트 (DB 연결이 있는 경우만)
    overlay_id = None
    if db is None:
        print("\n[4/5] DB Insert 테스트 건너뜀 (DB 연결 없음)")
        print("\n[5/5] DB Delete 테스트 건너뜀 (DB 연결 없음)")
    else:
        print("\n[4/5] DB에 레코드 Insert 중...")
        try:
            asset_id = uuid.uuid4()
            now = datetime.utcnow()
            
            new_asset = TestAsset(
                asset_id=asset_id,
                tenant_id=tenant_id,
                asset_url=asset_url,
                asset_kind=kind,
                width=asset_meta["width"],
                height=asset_meta["height"],
                created_at=now,
                updated_at=now
            )
            
            db.add(new_asset)
            db.commit()
            print(f"✓ DB Insert 완료:")
            print(f"  - Asset ID: {asset_id}")
            print(f"  - Tenant ID: {tenant_id}")
            print(f"  - Asset URL: {asset_url}")
            print(f"  - Kind: {kind}")
            print(f"  - Size: {asset_meta['width']}x{asset_meta['height']}")
            
            # 조회 확인
            retrieved = db.query(TestAsset).filter(TestAsset.asset_id == asset_id).first()
            if retrieved:
                print(f"  ✓ 레코드 조회 성공")
                print(f"    - Asset URL: {retrieved.asset_url}")
                print(f"    - Created At: {retrieved.created_at}")
            else:
                print(f"  ❌ 오류: 레코드를 조회할 수 없습니다!")
                return False
                
        except Exception as e:
            print(f"❌ DB Insert 실패: {e}")
            db.rollback()
            import traceback
            traceback.print_exc()
            return False
        
        # # DB Delete 테스트
        # print("\n[5/5] DB에서 레코드 Delete 중...")
        # try:
        #     deleted_count = db.query(TestAsset).filter(TestAsset.asset_id == asset_id).delete()
        #     db.commit()
            
        #     if deleted_count > 0:
        #         print(f"✓ DB Delete 완료: {deleted_count}개 레코드 삭제")
                
        #         # 삭제 확인
        #         deleted_check = db.query(TestAsset).filter(TestAsset.asset_id == asset_id).first()
        #         if deleted_check is None:
        #             print(f"  ✓ 레코드 삭제 확인 완료")
        #         else:
        #             print(f"  ❌ 오류: 레코드가 삭제되지 않았습니다!")
        #             return False
        #     else:
        #         print(f"  ❌ 오류: 삭제된 레코드가 없습니다!")
        #         return False
                
        # except Exception as e:
        #     print(f"❌ DB Delete 실패: {e}")
        #     db.rollback()
        #     import traceback
        #     traceback.print_exc()
        #     return False
        finally:
            if db:
                db.close()
    
    # # 파일 삭제
    # print("\n" + "-" * 60)
    # print("정리 작업")
    # print("-" * 60)
    # try:
    #     if os.path.exists(asset_path):
    #         os.remove(asset_path)
    #         print(f"✓ 테스트 파일 삭제: {asset_path}")
            
    #         # 디렉토리도 비어있으면 삭제 (선택사항)
    #         asset_dir = os.path.dirname(asset_path)
    #         if os.path.exists(asset_dir) and not os.listdir(asset_dir):
    #             os.rmdir(asset_dir)
    #             print(f"✓ 빈 디렉토리 삭제: {asset_dir}")
    # except Exception as e:
    #     print(f"⚠ 파일 삭제 실패 (무시 가능): {e}")
    
    # print("\n" + "=" * 60)
    # print("✓ 모든 테스트 완료!")
    # print("=" * 60)
    
    return True


def test_multiple_assets():
    """여러 Asset 저장 및 DB 작업 테스트"""
    
    print("=" * 60)
    print("여러 Asset 저장 및 DB 작업 테스트")
    print("=" * 60)
    
    tenant_id = "test_tenant_multi"
    kind = "test_batch"
    count = 3
    
    # DB 연결 시도
    db = None
    try:
        db = SessionLocal()
        # 테이블 생성 확인
        Base.metadata.create_all(db.bind)
    except Exception as e:
        print(f"⚠ DB 연결 실패 (DB 테스트는 건너뜁니다): {e}")
        print(f"  Asset 저장 테스트는 계속 진행합니다...")
        db = None
    
    overlay_ids = []
    asset_paths = []
    
    try:
        for i in range(count):
            print(f"\n[{i+1}/{count}] Asset {i+1} 저장 및 DB Insert...")
            
            # 이미지 생성
            test_image = Image.new("RGB", (256, 256), color=(i*80, 100, 150))
            
            # Asset 저장
            asset_meta = save_asset(tenant_id, kind, test_image, ".png")
            asset_url = asset_meta["url"]
            asset_path = abs_from_url(asset_url)
            asset_paths.append(asset_path)
            
            # DB Insert (DB 연결이 있는 경우만)
            if db is not None:
                asset_id = uuid.uuid4()
                now = datetime.utcnow()
                
                new_asset = TestAsset(
                    asset_id=asset_id,
                    tenant_id=tenant_id,
                    asset_url=asset_url,
                    asset_kind=kind,
                    width=asset_meta["width"],
                    height=asset_meta["height"],
                    created_at=now,
                    updated_at=now
                )
                
                db.add(new_asset)
                overlay_ids.append(asset_id)
                print(f"  ✓ Asset {i+1} 저장 및 DB Insert 완료")
            else:
                print(f"  ✓ Asset {i+1} 저장 완료 (DB Insert 건너뜀)")
        
        if db is not None:
            db.commit()
            print(f"\n✓ 총 {count}개 레코드 Insert 완료")
            
            # 조회 확인
            retrieved_count = db.query(TestAsset).filter(
                TestAsset.asset_id.in_(overlay_ids)
            ).count()
            print(f"✓ 조회된 레코드 수: {retrieved_count}")
            
            # 일괄 삭제
            print(f"\n일괄 Delete 중...")
            deleted_count = db.query(TestAsset).filter(
                TestAsset.asset_id.in_(overlay_ids)
            ).delete(synchronize_session=False)
            db.commit()
            print(f"✓ {deleted_count}개 레코드 삭제 완료")
        else:
            print(f"\n✓ 총 {count}개 Asset 저장 완료 (DB 작업 건너뜀)")
        
        # 파일 삭제
        for asset_path in asset_paths:
            if os.path.exists(asset_path):
                os.remove(asset_path)
        
        print("\n" + "=" * 60)
        print("✓ 일괄 테스트 완료!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        if db:
            db.rollback()
        import traceback
        traceback.print_exc()
        return False
    finally:
        if db:
            db.close()
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Asset 저장 및 DB 작업 테스트")
    parser.add_argument("--mode", choices=["single", "multiple"], default="single",
                       help="테스트 모드: single (기본), multiple (일괄 테스트)")
    args = parser.parse_args()
    
    try:
        if args.mode == "single":
            success = test_save_asset_and_db()
        else:
            success = test_multiple_assets()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


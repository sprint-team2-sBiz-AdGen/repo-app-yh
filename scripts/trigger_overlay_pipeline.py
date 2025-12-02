#!/usr/bin/env python3
"""
트리거 기반 오버레이 파이프라인 스크립트
Job과 Variants를 생성하고 트리거를 발동시켜 자동으로 파이프라인 진행
"""

import sys
import os
import uuid
import time
from pathlib import Path
from PIL import Image
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from utils import save_asset
from config import HOST, PORT


def create_job_with_variants(
    image_paths: list,
    text: str,
    tenant_id: str = "overlay_test_tenant"
) -> dict:
    """Job 1개와 Variants 3개 생성 (각각 다른 이미지)"""
    db: Session = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print("Job 및 Job Variants 생성")
        print(f"{'='*60}")
        
        # Tenant 생성/확인
        db.execute(sql_text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"Overlay Test Tenant ({tenant_id})"
        })
        print(f"✓ Tenant 확인: {tenant_id}")
        
        # Job 생성 (img_gen 완료 상태로 시작 - YH 파트 시작)
        job_id = uuid.uuid4()
        db.execute(sql_text("""
            INSERT INTO jobs (
                job_id, tenant_id, status, current_step, created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, 'done', 'img_gen', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id
        })
        db.commit()
        print(f"✓ Job 생성: {job_id}")
        print(f"  - status=done, current_step=img_gen")
        
        # tone_style_id 조회 (기본값 사용)
        tone_style_row = db.execute(sql_text("""
            SELECT tone_style_id
            FROM tone_styles
            LIMIT 1
        """)).first()
        tone_style_id = tone_style_row[0] if tone_style_row else None
        
        # store_id 조회 (선택적)
        store_row = db.execute(sql_text("""
            SELECT store_id
            FROM stores
            LIMIT 1
        """)).first()
        store_id = store_row[0] if store_row else None
        
        # Variants 생성 (각각 다른 이미지 사용) - 먼저 생성하여 image_asset_id 확보
        job_variants = []
        first_image_asset_id = None
        for i, image_path in enumerate(image_paths, 1):
            if not os.path.exists(image_path):
                print(f"⚠ 이미지 파일을 찾을 수 없습니다: {image_path}, 스킵")
                continue
            
            print(f"\n[Variant {i}/{len(image_paths)}] 생성 중...")
            print(f"  이미지: {image_path}")
            
            # 이미지 로드 및 저장
            image = Image.open(image_path)
            asset_meta = save_asset(tenant_id, "generated", image, ".png")
            asset_url = asset_meta["url"]
            image_asset_id = uuid.UUID(asset_meta["asset_id"])
            
            # image_assets 확인/생성
            existing = db.execute(
                sql_text("""
                    SELECT image_asset_id FROM image_assets
                    WHERE image_asset_id = :image_asset_id
                """),
                {"image_asset_id": image_asset_id}
            ).first()
            
            if not existing:
                db.execute(sql_text("""
                    INSERT INTO image_assets (
                        image_asset_id, image_type, image_url, width, height,
                        tenant_id, created_at, updated_at
                    ) VALUES (
                        :image_asset_id, 'generated', :image_url, :width, :height,
                        :tenant_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """), {
                    "image_asset_id": image_asset_id,
                    "image_url": asset_url,
                    "width": image.size[0],
                    "height": image.size[1],
                    "tenant_id": tenant_id
                })
                db.commit()
                print(f"  ✓ image_assets 저장: {image_asset_id}")
            
            # Job Variant 생성 (img_gen 완료 상태)
            job_variants_id = uuid.uuid4()
            db.execute(sql_text("""
                INSERT INTO jobs_variants (
                    job_variants_id, job_id, img_asset_id, creation_order,
                    status, current_step, created_at, updated_at
                ) VALUES (
                    :job_variants_id, :job_id, :img_asset_id, :creation_order,
                    'done', 'img_gen', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "job_variants_id": job_variants_id,
                "job_id": job_id,
                "img_asset_id": image_asset_id,
                "creation_order": i
            })
            db.commit()
            
            job_variants.append({
                "job_variants_id": str(job_variants_id),
                "img_asset_id": str(image_asset_id),
                "asset_url": asset_url,
                "creation_order": i
            })
            print(f"  ✓ Variant {i} 생성 완료: {job_variants_id}")
            print(f"    - status=done, current_step=img_gen")
            
            # 첫 번째 variant의 image_asset_id 저장 (job_inputs용)
            if i == 1:
                first_image_asset_id = image_asset_id
        
        print(f"\n✓ 총 {len(job_variants)}개 Variant 생성 완료")
        
        # Job Input 생성 (텍스트 정보 저장)
        db.execute(sql_text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, tone_style_id, desc_kor, created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :tone_style_id, :desc_kor, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (job_id) DO UPDATE
            SET desc_kor = :desc_kor, updated_at = CURRENT_TIMESTAMP
        """), {
            "job_id": job_id,
            "img_asset_id": first_image_asset_id,
            "tone_style_id": tone_style_id,
            "desc_kor": text
        })
        print(f"✓ Job Input 생성: desc_kor={text[:50]}...")
        
        # JS 파트 데이터 생성 (kor_to_eng, ad_copy_eng, ad_copy_kor)
        print(f"\n[JS 파트 데이터 생성]")
        
        # kor_to_eng: 한국어 → 영어 변환 (임의)
        desc_eng = "A bowl of light broth, making today gentle."
        kor_to_eng_gen_id = uuid.uuid4()
        db.execute(sql_text("""
            INSERT INTO txt_ad_copy_generations (
                ad_copy_gen_id, job_id, generation_stage,
                ad_copy_eng, status,
                created_at, updated_at
            ) VALUES (
                :ad_copy_gen_id, :job_id, 'kor_to_eng',
                :ad_copy_eng, 'done',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "ad_copy_gen_id": kor_to_eng_gen_id,
            "job_id": job_id,
            "ad_copy_eng": desc_eng
        })
        print(f"✓ kor_to_eng 생성: {desc_eng[:50]}...")
        
        # ad_copy_eng: 영어 광고문구 생성 (임의)
        ad_copy_eng = "A bowl of light broth, making today gentle. Experience the comfort and warmth in every sip."
        ad_copy_eng_gen_id = uuid.uuid4()
        db.execute(sql_text("""
            INSERT INTO txt_ad_copy_generations (
                ad_copy_gen_id, job_id, generation_stage,
                ad_copy_eng, status,
                created_at, updated_at
            ) VALUES (
                :ad_copy_gen_id, :job_id, 'ad_copy_eng',
                :ad_copy_eng, 'done',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "ad_copy_gen_id": ad_copy_eng_gen_id,
            "job_id": job_id,
            "ad_copy_eng": ad_copy_eng
        })
        print(f"✓ ad_copy_eng 생성: {ad_copy_eng[:50]}...")
        
        # ad_copy_kor: 한글 광고문구 생성 (오버레이에 사용할 텍스트)
        ad_copy_kor = text  # 사용자가 제공한 텍스트 사용
        ad_copy_kor_gen_id = uuid.uuid4()
        db.execute(sql_text("""
            INSERT INTO txt_ad_copy_generations (
                ad_copy_gen_id, job_id, generation_stage,
                ad_copy_kor, status,
                created_at, updated_at
            ) VALUES (
                :ad_copy_gen_id, :job_id, 'ad_copy_kor',
                :ad_copy_kor, 'done',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "ad_copy_gen_id": ad_copy_kor_gen_id,
            "job_id": job_id,
            "ad_copy_kor": ad_copy_kor
        })
        print(f"✓ ad_copy_kor 생성: {ad_copy_kor[:50]}...")
        db.commit()
        
        return {
            "job_id": str(job_id),
            "tenant_id": tenant_id,
            "job_variants": job_variants,
            "text": text
        }
        
    except Exception as e:
        db.rollback()
        print(f"❌ Job 생성 오류: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


def trigger_pipeline(job_variants: list):
    """트리거 발동: 상태를 업데이트하여 자동 파이프라인 시작"""
    db: Session = SessionLocal()
    try:
        print(f"\n{'='*60}")
        print("트리거 발동")
        print(f"{'='*60}")
        print("각 Variant의 상태를 업데이트하여 자동 파이프라인 시작...")
        
        for variant in job_variants:
            job_variants_id = variant["job_variants_id"]
            creation_order = variant["creation_order"]
            
            # 상태를 running으로 변경 (트리거 발동)
            db.execute(
                sql_text("""
                    UPDATE jobs_variants 
                    SET status = 'running',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": uuid.UUID(job_variants_id)}
            )
            db.commit()
            time.sleep(0.1)  # 트리거 발동 대기
            
            # 상태를 done으로 변경 (트리거 발동)
            db.execute(
                sql_text("""
                    UPDATE jobs_variants 
                    SET status = 'done',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": uuid.UUID(job_variants_id)}
            )
            db.commit()
            
            print(f"✓ Variant {creation_order} 트리거 발동: {job_variants_id}")
            time.sleep(0.2)  # 각 variant 간 간격
        
        print(f"\n✓ 모든 Variant 트리거 발동 완료")
        print(f"  파이프라인이 자동으로 진행됩니다:")
        print(f"    img_gen (done) → vlm_analyze → yolo_detect → planner → overlay → ...")
        
    except Exception as e:
        db.rollback()
        print(f"❌ 트리거 발동 오류: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="트리거 기반 오버레이 파이프라인 실행")
    parser.add_argument("image_paths", nargs="+", help="입력 이미지 경로들 (여러 개 가능)")
    parser.add_argument("--text", required=True, help="오버레이할 텍스트")
    parser.add_argument("--tenant-id", default="overlay_test_tenant", help="Tenant ID")
    
    args = parser.parse_args()
    
    # 이미지 파일 존재 확인
    valid_image_paths = []
    for img_path in args.image_paths:
        if os.path.exists(img_path):
            valid_image_paths.append(img_path)
        else:
            print(f"⚠ 이미지 파일을 찾을 수 없습니다: {img_path}")
    
    if not valid_image_paths:
        print("❌ 유효한 이미지 파일이 없습니다.")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print("트리거 기반 오버레이 파이프라인")
    print(f"{'='*60}")
    print(f"이미지 개수: {len(valid_image_paths)}개")
    for i, img_path in enumerate(valid_image_paths, 1):
        print(f"  {i}. {img_path}")
    print(f"텍스트: {args.text}")
    print(f"Tenant ID: {args.tenant_id}")
    print(f"{'='*60}\n")
    
    try:
        # Step 1: Job과 Variants 생성
        job_data = create_job_with_variants(
            valid_image_paths,
            args.text,
            args.tenant_id
        )
        
        # Step 2: 트리거 발동
        trigger_pipeline(job_data["job_variants"])
        
        # 결과 출력
        print(f"\n{'='*60}")
        print("✓ 파이프라인 시작 완료!")
        print(f"{'='*60}")
        print(f"Job ID: {job_data['job_id']}")
        print(f"Variants: {len(job_data['job_variants'])}개")
        print(f"\n파이프라인 진행 상황은 데이터베이스에서 확인하세요:")
        print(f"  SELECT job_variants_id, current_step, status FROM jobs_variants WHERE job_id = '{job_data['job_id']}';")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ 파이프라인 시작 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


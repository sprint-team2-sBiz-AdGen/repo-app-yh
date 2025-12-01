#!/usr/bin/env python3
"""YH 파트 전체 파이프라인 테스트 (텍스트 생성 포함)
- JS 파트 데이터 임의 생성 (kor_to_eng, ad_copy_eng, ad_copy_kor)
  * kor_to_eng: 사용자 입력 한글 description → 영어 번역
  * ad_copy_eng: 영어 광고문구 생성
  * ad_copy_kor: 한글 광고문구 생성 (오버레이에 사용)
- YH 파트 파이프라인 테스트 (vlm_analyze → ... → iou_eval → eng_to_kor → instagram_feed)
  * 오버레이에는 한글 광고문구(ad_copy_kor) 사용
  * 피드글 생성에는 한글 광고문구를 이용하여 GPT로 한글 피드글 생성
"""
import sys
import os
import uuid
import time
import requests
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ASSETS_DIR 환경 변수를 먼저 설정
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, ImageAsset, Job, JobInput, JobVariant
from utils import save_asset
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8011")


def create_test_job_with_js_data(
    tenant_id: str = "yh_pipeline_test_tenant",
    image_path: str = None,
    desc_kor: str = "맛있는 부대찌개를 만나보세요",
    variants_count: int = 3
) -> dict:
    """테스트용 Job 생성 및 JS 파트 데이터 임의 생성"""
    print("\n" + "=" * 60)
    print("YH 파트 파이프라인 테스트 Job 생성")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        # 1. Tenant 생성/확인
        print(f"\n[1/8] Tenant 확인/생성 중...")
        db.execute(text("""
            INSERT INTO tenants (tenant_id, display_name, created_at, updated_at)
            VALUES (:tenant_id, :display_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (tenant_id) DO NOTHING
        """), {
            "tenant_id": tenant_id,
            "display_name": f"YH Pipeline Test Tenant ({tenant_id})"
        })
        db.commit()
        print(f"✓ Tenant 확인/생성 완료: {tenant_id}")
        
        # 2. 이미지 생성 또는 로드 (background_job_creator.py 방식 참고)
        print(f"\n[2/8] 이미지 준비 중...")
        if image_path and os.path.exists(image_path):
            image = Image.open(image_path)
            print(f"  - Image Path: {image_path}")
        else:
            # 기본 이미지 경로들 시도 (background_job_creator.py와 동일)
            default_image_paths = [
                project_root / "pipeline_test" / "pipeline_test_image9.jpg",
                project_root / "pipeline_test" / "pipeline_test_image1.png",
                project_root / "pipeline_test" / "ppipeline_test_image16.jpg",
            ]
            image = None
            for img_path in default_image_paths:
                if img_path.exists():
                    image = Image.open(str(img_path))
                    print(f"  - 실제 이미지 사용: {img_path}")
                    break
            
            if image is None:
                # 더미 이미지 생성 (fallback)
                image = Image.new('RGB', (1024, 1024), color='lightblue')
                draw = ImageDraw.Draw(image)
                draw.rectangle([100, 100, 924, 924], fill='white', outline='black', width=5)
                draw.text((400, 500), "Test Image", fill='black')
                print(f"  - 더미 이미지 생성: 1024x1024 (실제 이미지 파일을 찾을 수 없음)")
        
        # ASSETS_DIR에 저장
        asset_meta = save_asset(tenant_id, "yh_pipeline_test", image, ".png")
        asset_url = asset_meta["url"]
        print(f"  - Asset URL: {asset_url}")
        
        # 3. image_assets 레코드 생성
        image_asset_id = uuid.uuid4()
        db.execute(text("""
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
        print(f"✓ image_assets 레코드 생성: {image_asset_id}")
        
        # 4. tone_style_id 조회 (기본값 사용)
        print(f"\n[3/8] Tone Style 확인 중...")
        tone_style_row = db.execute(text("""
            SELECT tone_style_id, kor_name
            FROM tone_styles
            LIMIT 1
        """)).first()
        
        tone_style_id = None
        if tone_style_row:
            tone_style_id = tone_style_row.tone_style_id
            print(f"✓ Tone Style 사용: {tone_style_row.kor_name}")
        else:
            print(f"⚠ Tone Style 없음 (NULL 사용)")
        
        # 5. store_id 조회 또는 생성 (선택적)
        print(f"\n[4/8] Store 확인 중...")
        store_row = db.execute(text("""
            SELECT store_id
            FROM stores
            LIMIT 1
        """)).first()
        
        store_id = None
        if store_row:
            store_id = store_row.store_id
            print(f"✓ Store 사용: {store_id}")
        else:
            print(f"⚠ Store 없음 (NULL 사용)")
        
        # 6. Job 생성
        print(f"\n[5/8] Job 생성 중...")
        job_id = uuid.uuid4()
        db.execute(text("""
            INSERT INTO jobs (
                job_id, tenant_id, store_id, status, current_step,
                created_at, updated_at
            ) VALUES (
                :job_id, :tenant_id, :store_id, 'done', 'img_gen',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "store_id": store_id
        })
        print(f"✓ Job 생성: {job_id}")
        print(f"  - status=done, current_step=img_gen")
        
        # 7. job_inputs 생성
        print(f"\n[6/8] Job Inputs 생성 중...")
        db.execute(text("""
            INSERT INTO job_inputs (
                job_id, img_asset_id, tone_style_id, desc_kor,
                created_at, updated_at
            ) VALUES (
                :job_id, :img_asset_id, :tone_style_id, :desc_kor,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "job_id": job_id,
            "img_asset_id": image_asset_id,
            "tone_style_id": tone_style_id,
            "desc_kor": desc_kor
        })
        print(f"✓ Job Inputs 생성")
        print(f"  - desc_kor: {desc_kor}")
        
        # 8. JS 파트 데이터 임의 생성 (kor_to_eng, ad_copy_eng, ad_copy_kor)
        print(f"\n[7/8] JS 파트 데이터 임의 생성 중...")
        
        # kor_to_eng: 한국어 → 영어 변환 (임의)
        desc_eng = "Delicious Korean Army Stew - A perfect blend of spicy, savory, and comforting flavors."
        kor_to_eng_gen_id = uuid.uuid4()
        db.execute(text("""
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
        ad_copy_eng = "Experience the perfect harmony of spicy, savory, and comforting flavors with our Korean Army Stew. Made with premium ingredients and authentic recipes, this dish will warm your heart and satisfy your cravings. Visit us today!"
        ad_copy_eng_gen_id = uuid.uuid4()
        db.execute(text("""
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
        
        # ad_copy_kor: 한글 광고문구 생성 (JS 파트에서 GPT로 생성, 오버레이에 사용)
        # 사용자 입력 한글 description → 영어 번역 → GPT로 한글 광고문구 생성
        # ⚠️ 테스트용으로 짧게 생성 (실제 오버레이에 적합한 길이)
        ad_copy_kor = "맛있는 부대찌개를 만나보세요!"
        ad_copy_kor_gen_id = uuid.uuid4()
        db.execute(text("""
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
        
        # 9. jobs_variants 생성 (이미지 처리용)
        print(f"\n[8/8] Job Variants 생성 중...")
        variant_ids = []
        for i in range(variants_count):
            variant_id = uuid.uuid4()
            variant_ids.append(variant_id)
            db.execute(text("""
                INSERT INTO jobs_variants (
                    job_variants_id, job_id, img_asset_id, creation_order,
                    status, current_step,
                    created_at, updated_at
                ) VALUES (
                    :job_variants_id, :job_id, :img_asset_id, :creation_order,
                    'done', 'img_gen',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """), {
                "job_variants_id": variant_id,
                "job_id": job_id,
                "img_asset_id": image_asset_id,
                "creation_order": i + 1
            })
            print(f"✓ Variant {i+1} 생성: {variant_id}")
        
        db.commit()
        
        # 전 단계 완료 조건 검증
        print("\n" + "=" * 60)
        print("전 단계 완료 조건 검증")
        print("=" * 60)
        if not verify_pre_stage_completion(db, job_id):
            raise ValueError("전 단계 완료 조건을 만족하지 않습니다. JS 파트 또는 YE 파트 데이터가 부족합니다.")
        
        print("\n" + "=" * 60)
        print("✅ Job 생성 완료")
        print("=" * 60)
        print(f"Job ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        print(f"Variants: {len(variant_ids)}개")
        print(f"JS 파트 데이터: kor_to_eng, ad_copy_eng, ad_copy_kor 생성 완료")
        print(f"  - 오버레이 텍스트: 한글 광고문구(ad_copy_kor) 사용")
        print("=" * 60)
        
        logger.info(f"Job 생성 완료: job_id={job_id}, variants={len(variant_ids)}개")
        
        return {
            "job_id": str(job_id),
            "tenant_id": tenant_id,
            "variant_ids": [str(vid) for vid in variant_ids],
            "image_asset_id": str(image_asset_id),
            "asset_url": asset_url,
            "desc_kor": desc_kor,
            "desc_eng": desc_eng,
            "ad_copy_eng": ad_copy_eng,
            "ad_copy_kor": ad_copy_kor
        }
        
    except ValueError as e:
        # 전 단계 완료 조건 불만족
        db.rollback()
        logger.error(f"전 단계 완료 조건 검증 실패: {e}", exc_info=True)
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Job 생성 중 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()


def verify_pre_stage_completion(db: Session, job_id: str) -> bool:
    """전 단계 완료 조건 검증 (JS 파트 + YE 파트)"""
    logger.info(f"전 단계 완료 조건 검증 시작: job_id={job_id}")
    
    # 1. JS 파트 검증 (kor_to_eng, ad_copy_eng, ad_copy_kor)
    js_count = db.execute(text("""
        SELECT COUNT(*) 
        FROM txt_ad_copy_generations
        WHERE job_id = :job_id
          AND generation_stage IN ('kor_to_eng', 'ad_copy_eng', 'ad_copy_kor')
          AND status = 'done'
    """), {"job_id": job_id}).scalar()
    
    js_part_complete = js_count >= 3  # kor_to_eng, ad_copy_eng, ad_copy_kor
    
    # 2. YE 파트 검증
    ye_count = db.execute(text("""
        SELECT COUNT(*)
        FROM jobs_variants
        WHERE job_id = :job_id
          AND status = 'done'
          AND current_step = 'img_gen'
          AND img_asset_id IS NOT NULL
    """), {"job_id": job_id}).scalar()
    
    ye_part_complete = ye_count > 0
    
    # 검증 결과 출력
    if not js_part_complete:
        logger.warning(f"⚠️ JS 파트 데이터 부족: {js_count}/3 (필요: kor_to_eng, ad_copy_eng, ad_copy_kor)")
        print(f"⚠️ JS 파트 데이터 부족: {js_count}/3 (필요: kor_to_eng, ad_copy_eng, ad_copy_kor)")
    else:
        logger.info(f"✓ JS 파트 완료: {js_count}/3")
        print(f"✓ JS 파트 완료: {js_count}/3")
    
    if not ye_part_complete:
        logger.warning(f"⚠️ YE 파트 데이터 없음: {ye_count}개 variants")
        print(f"⚠️ YE 파트 데이터 없음: {ye_count}개 variants")
    else:
        logger.info(f"✓ YE 파트 완료: {ye_count}개 variants")
        print(f"✓ YE 파트 완료: {ye_count}개 variants")
    
    if js_part_complete and ye_part_complete:
        logger.info(f"✅ 전 단계 완료 조건 모두 만족: JS 파트 ✓, YE 파트 ✓")
        print(f"✅ 전 단계 완료 조건 모두 만족: JS 파트 ✓, YE 파트 ✓")
        return True
    else:
        logger.error(f"❌ 전 단계 완료 조건 불만족: JS 파트={js_part_complete}, YE 파트={ye_part_complete}")
        print(f"❌ 전 단계 완료 조건 불만족: JS 파트={js_part_complete}, YE 파트={ye_part_complete}")
        return False


def check_job_status(db: Session, job_id: str):
    """Job 상태 확인"""
    row = db.execute(text("""
        SELECT status, current_step, retry_count
        FROM jobs
        WHERE job_id = :job_id
    """), {"job_id": job_id}).first()
    
    if row:
        print(f"  Job Status: {row.status}")
        print(f"  Current Step: {row.current_step}")
        print(f"  Retry Count: {row.retry_count}")
        return {
            "status": row.status,
            "current_step": row.current_step,
            "retry_count": row.retry_count
        }
    return None


def check_variants_status(db: Session, job_id: str):
    """Job Variants 상태 확인"""
    rows = db.execute(text("""
        SELECT job_variants_id, creation_order, status, current_step, retry_count
        FROM jobs_variants
        WHERE job_id = :job_id
        ORDER BY creation_order
    """), {"job_id": job_id}).fetchall()
    
    print(f"\n  Variants ({len(rows)}개):")
    for row in rows:
        print(f"    Variant {row.creation_order}: {row.current_step} ({row.status}), retry={row.retry_count}")
    
    return rows


def check_txt_ad_copy_generations(db: Session, job_id: str):
    """txt_ad_copy_generations 상태 확인"""
    rows = db.execute(text("""
        SELECT generation_stage, status, 
               CASE 
                   WHEN generation_stage = 'eng_to_kor' THEN ad_copy_kor
                   WHEN generation_stage = 'refined_ad_copy' THEN refined_ad_copy_eng
                   ELSE ad_copy_eng
               END AS content
        FROM txt_ad_copy_generations
        WHERE job_id = :job_id
        ORDER BY 
            CASE generation_stage
                WHEN 'kor_to_eng' THEN 1
                WHEN 'ad_copy_eng' THEN 2
                WHEN 'refined_ad_copy' THEN 3
                WHEN 'eng_to_kor' THEN 4
            END
    """), {"job_id": job_id}).fetchall()
    
    print(f"\n  Text Ad Copy Generations ({len(rows)}개):")
    for row in rows:
        content_preview = row.content[:50] + "..." if row.content and len(row.content) > 50 else (row.content or "")
        print(f"    {row.generation_stage}: {row.status} - {content_preview}")
    
    return rows


def check_instagram_feeds(db: Session, job_id: str):
    """instagram_feeds 상태 확인"""
    rows = db.execute(text("""
        SELECT instagram_feed_id, llm_trace_id, ad_copy_kor,
               instagram_ad_copy, hashtags
        FROM instagram_feeds
        WHERE job_id = :job_id
    """), {"job_id": job_id}).fetchall()
    
    if rows:
        print(f"\n  Instagram Feeds ({len(rows)}개):")
        for row in rows:
            print(f"    Feed ID: {row.instagram_feed_id}")
            print(f"    LLM Trace ID: {row.llm_trace_id}")
            print(f"    Ad Copy Kor: {row.ad_copy_kor[:50] if row.ad_copy_kor else 'N/A'}...")
            print(f"    Instagram Ad Copy: {row.instagram_ad_copy[:50] if row.instagram_ad_copy else 'N/A'}...")
            print(f"    Hashtags: {row.hashtags}")
    else:
        print(f"\n  Instagram Feeds: 없음")
    
    return rows


def print_detailed_results(db: Session, job_id: str):
    """Job의 각 단계별 결과물을 상세하게 출력"""
    print("\n" + "=" * 80)
    print("📊 파이프라인 결과물 상세 정보")
    print("=" * 80)
    
    try:
        # Job 정보
        job = db.execute(text("""
            SELECT job_id, tenant_id, status, current_step, created_at
            FROM jobs
            WHERE job_id = :job_id
        """), {"job_id": job_id}).first()
        
        if not job:
            print("❌ Job을 찾을 수 없습니다.")
            return
        
        print(f"\n📋 Job 정보:")
        print(f"   - Job ID: {job[0]}")
        print(f"   - Tenant ID: {job[1]}")
        print(f"   - Status: {job[2]}")
        print(f"   - Current Step: {job[3]}")
        print(f"   - Created At: {job[4]}")
        
        # 1. 원본 이미지 경로
        print(f"\n{'─' * 80}")
        print("🖼️  원본 이미지")
        print(f"{'─' * 80}")
        job_input = db.execute(text("""
            SELECT ji.img_asset_id, ia.image_url
            FROM job_inputs ji
            INNER JOIN image_assets ia ON ji.img_asset_id = ia.image_asset_id
            WHERE ji.job_id = :job_id
        """), {"job_id": job_id}).first()
        
        if job_input:
            # 절대 경로 변환
            if job_input[1] and job_input[1].startswith("/assets/"):
                # 호스트 경로로 변환 (/assets/ -> /opt/feedlyai/assets/) - 표시용
                original_path_host = job_input[1].replace("/assets/", "/opt/feedlyai/assets/")
                # 컨테이너 내부 경로 - 파일 존재 확인용
                original_path_container = os.path.join(ASSETS_DIR, job_input[1][len("/assets/"):])
                print(f"   - Image Asset ID: {job_input[0]}")
                print(f"   - Image URL: {job_input[1]}")
                print(f"   - 절대 경로: {original_path_host}")
                print(f"   - 파일 존재: {'✅' if os.path.exists(original_path_container) else '❌'}")
            else:
                print(f"   - Image Asset ID: {job_input[0]}")
                print(f"   - Image URL: {job_input[1]}")
                print(f"   - 절대 경로: (URL 형식 오류)")
        else:
            print("   - 원본 이미지를 찾을 수 없습니다.")
        
        # 2. Variants별 각 단계 결과물
        print(f"\n{'─' * 80}")
        print("📦 Variants별 단계별 결과물")
        print(f"{'─' * 80}")
        
        variants = db.execute(text("""
            SELECT job_variants_id, creation_order, status, current_step, overlaid_img_asset_id
            FROM jobs_variants
            WHERE job_id = :job_id
            ORDER BY creation_order
        """), {"job_id": job_id}).fetchall()
        
        for variant in variants:
            variant_id = variant[0]
            order = variant[1]
            status = variant[2]
            current_step = variant[3]
            overlaid_img_asset_id = variant[4]
            
            print(f"\n   Variant {order} (ID: {str(variant_id)[:8]}...):")
            print(f"      - Status: {status}, Current Step: {current_step}")
            
            # 최종 오버레이 이미지 경로
            if overlaid_img_asset_id:
                overlay_asset = db.execute(text("""
                    SELECT image_url
                    FROM image_assets
                    WHERE image_asset_id = :asset_id
                """), {"asset_id": overlaid_img_asset_id}).first()
                
                if overlay_asset and overlay_asset[0]:
                    # 절대 경로 변환
                    if overlay_asset[0].startswith("/assets/"):
                        # 호스트 경로로 변환 (/assets/ -> /opt/feedlyai/assets/) - 표시용
                        overlay_path_host = overlay_asset[0].replace("/assets/", "/opt/feedlyai/assets/")
                        # 컨테이너 내부 경로 - 파일 존재 확인용
                        overlay_path_container = os.path.join(ASSETS_DIR, overlay_asset[0][len("/assets/"):])
                        print(f"      - 최종 오버레이 이미지:")
                        print(f"        * URL: {overlay_asset[0]}")
                        print(f"        * 절대 경로: {overlay_path_host}")
                        print(f"        * 파일 존재: {'✅' if os.path.exists(overlay_path_container) else '❌'}")
                    else:
                        print(f"      - 최종 오버레이 이미지:")
                        print(f"        * URL: {overlay_asset[0]}")
                        print(f"        * 절대 경로: (URL 형식 오류)")
            
            # overlay_layouts에서 render URL 확인 (fallback)
            if not overlaid_img_asset_id:
                overlay_layout = db.execute(text("""
                    SELECT layout->'render'->>'url' as render_url
                    FROM overlay_layouts
                    WHERE job_variants_id = :variant_id
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"variant_id": variant_id}).first()
                
                if overlay_layout and overlay_layout[0]:
                    # 절대 경로 변환
                    if overlay_layout[0].startswith("/assets/"):
                        # 호스트 경로로 변환 (/assets/ -> /opt/feedlyai/assets/) - 표시용
                        render_path_host = overlay_layout[0].replace("/assets/", "/opt/feedlyai/assets/")
                        # 컨테이너 내부 경로 - 파일 존재 확인용
                        render_path_container = os.path.join(ASSETS_DIR, overlay_layout[0][len("/assets/"):])
                        print(f"      - 오버레이 렌더 이미지:")
                        print(f"        * URL: {overlay_layout[0]}")
                        print(f"        * 절대 경로: {render_path_host}")
                        print(f"        * 파일 존재: {'✅' if os.path.exists(render_path_container) else '❌'}")
                    else:
                        print(f"      - 오버레이 렌더 이미지:")
                        print(f"        * URL: {overlay_layout[0]}")
                        print(f"        * 절대 경로: (URL 형식 오류)")
            
            # 각 단계별 평가 결과
            # OCR 평가
            ocr_eval = db.execute(text("""
                SELECT e.metrics->>'ocr_accuracy' as ocr_accuracy,
                       e.metrics->>'similarity' as similarity,
                       e.metrics->>'ocr_confidence' as ocr_confidence
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'ocr'
                ORDER BY e.created_at DESC
                LIMIT 1
            """), {"variant_id": variant_id}).first()
            
            if ocr_eval:
                ocr_accuracy = ocr_eval[0] if ocr_eval[0] else None
                similarity = ocr_eval[1] if ocr_eval[1] else None
                ocr_confidence = ocr_eval[2] if ocr_eval[2] else None
                if ocr_accuracy is not None:
                    print(f"      - OCR 평가:")
                    print(f"        * OCR 정확도: {float(ocr_accuracy):.4f}" if ocr_accuracy else "        * OCR 정확도: N/A")
                    if similarity is not None:
                        print(f"        * 유사도: {float(similarity):.4f}")
                    if ocr_confidence is not None:
                        print(f"        * OCR 신뢰도: {float(ocr_confidence):.4f}")
                else:
                    print(f"      - OCR 평가: N/A")
            
            # Readability 평가
            readability_eval = db.execute(text("""
                SELECT e.metrics->>'readability_score' as readability_score
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'readability'
                ORDER BY e.created_at DESC
                LIMIT 1
            """), {"variant_id": variant_id}).first()
            
            if readability_eval:
                print(f"      - Readability 평가 점수: {readability_eval[0] if readability_eval[0] else 'N/A'}")
            
            # IoU 평가
            iou_eval = db.execute(text("""
                SELECT e.metrics->>'iou_with_food' as iou_score, e.metrics->>'overlap_detected' as overlap
                FROM evaluations e
                INNER JOIN overlay_layouts ol ON e.overlay_id = ol.overlay_id
                WHERE ol.job_variants_id = :variant_id
                  AND e.evaluation_type = 'iou'
                ORDER BY e.created_at DESC
                LIMIT 1
            """), {"variant_id": variant_id}).first()
            
            if iou_eval:
                print(f"      - IoU 평가:")
                print(f"        * IoU 점수: {iou_eval[0] if iou_eval[0] else 'N/A'}")
                print(f"        * 겹침 감지: {iou_eval[1] if iou_eval[1] else 'N/A'}")
        
        # 3. 광고 카피 문구
        print(f"\n{'─' * 80}")
        print("📝 광고 카피 문구")
        print(f"{'─' * 80}")
        
        ad_copy_gens = db.execute(text("""
            SELECT generation_stage, ad_copy_kor, ad_copy_eng, refined_ad_copy_eng, status
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
            ORDER BY 
                CASE generation_stage
                    WHEN 'kor_to_eng' THEN 1
                    WHEN 'ad_copy_eng' THEN 2
                    WHEN 'refined_ad_copy' THEN 3
                    WHEN 'eng_to_kor' THEN 4
                END
        """), {"job_id": job_id}).fetchall()
        
        for gen in ad_copy_gens:
            stage = gen[0]
            kor = gen[1]
            eng = gen[2]
            refined = gen[3]
            status = gen[4]
            
            print(f"\n   [{stage}] (Status: {status}):")
            if kor:
                kor_preview = kor[:100] + "..." if len(kor) > 100 else kor
                print(f"      - 한글: {kor_preview}")
            if eng:
                eng_preview = eng[:100] + "..." if len(eng) > 100 else eng
                print(f"      - 영어: {eng_preview}")
            if refined:
                refined_preview = refined[:100] + "..." if len(refined) > 100 else refined
                print(f"      - 조정된 영어: {refined_preview}")
        
        # 4. 인스타그램 피드
        print(f"\n{'─' * 80}")
        print("📱 인스타그램 피드")
        print(f"{'─' * 80}")
        
        feeds = db.execute(text("""
            SELECT instagram_feed_id, instagram_ad_copy, hashtags, ad_copy_kor, created_at
            FROM instagram_feeds
            WHERE job_id = :job_id
            ORDER BY created_at DESC
        """), {"job_id": job_id}).fetchall()
        
        if feeds:
            for feed in feeds:
                feed_id = feed[0]
                ad_copy = feed[1]
                hashtags = feed[2]
                ad_copy_kor = feed[3]
                created_at = feed[4]
                
                print(f"\n   Feed ID: {feed_id}")
                print(f"   Created At: {created_at}")
                
                if ad_copy_kor:
                    kor_preview = ad_copy_kor[:150] + "..." if len(ad_copy_kor) > 150 else ad_copy_kor
                    print(f"   한글 광고문구: {kor_preview}")
                
                if ad_copy:
                    ad_copy_preview = ad_copy[:200] + "..." if len(ad_copy) > 200 else ad_copy
                    print(f"   피드글:")
                    print(f"   {ad_copy_preview}")
                
                if hashtags:
                    print(f"   해시태그: {hashtags}")
        else:
            print("   인스타그램 피드가 생성되지 않았습니다.")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        logger.error(f"상세 결과 출력 중 오류: {e}", exc_info=True)
        print(f"❌ 오류 발생: {e}")


def print_table_status(db: Session, job_id: str, step_name: str = ""):
    """jobs와 jobs_variants 테이블 상태 출력 (test_job_variants_pipeline.py 구조 참고)"""
    print(f"\n{'=' * 60}")
    if step_name:
        print(f"[{step_name}] 테이블 상태")
    else:
        print("테이블 상태")
    print(f"{'=' * 60}")
    
    # jobs 테이블 상태
    job_status = check_job_status(db, job_id)
    if job_status:
        print(f"📋 jobs 테이블:")
        print(f"   - job_id: {job_id[:8]}...")
        print(f"   - status: {job_status['status']}")
        print(f"   - current_step: {job_status['current_step']}")
        print(f"   - retry_count: {job_status.get('retry_count', 0)}")
    else:
        print(f"📋 jobs 테이블: Job을 찾을 수 없습니다")
    
    # jobs_variants 테이블 상태
    variants = db.execute(text("""
        SELECT job_variants_id, creation_order, status, current_step, updated_at
        FROM jobs_variants
        WHERE job_id = :job_id
        ORDER BY creation_order
    """), {"job_id": job_id}).fetchall()
    
    print(f"\n📦 jobs_variants 테이블 (총 {len(variants)}개):")
    for variant in variants:
        print(f"   Variant {variant[1]}:")
        print(f"     - job_variants_id: {str(variant[0])[:8]}...")
        print(f"     - status: {variant[2]}")
        print(f"     - current_step: {variant[3]}")
        print(f"     - updated_at: {variant[4]}")
    
    # txt_ad_copy_generations 상태
    check_txt_ad_copy_generations(db, job_id)
    
    # instagram_feeds 상태
    check_instagram_feeds(db, job_id)
    
    print()


def monitor_pipeline_progress(job_id: str, tenant_id: str, max_wait_minutes: int = 30):
    """파이프라인 진행 상황 모니터링 (test_job_variants_pipeline.py 구조 참고)"""
    print("\n" + "=" * 60)
    print("파이프라인 진행 상황 모니터링")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"최대 대기 시간: {max_wait_minutes}분")
    print("=" * 60)
    
    logger.info(f"파이프라인 모니터링 시작: job_id={job_id}, max_wait={max_wait_minutes}분")
    
    db = SessionLocal()
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    check_interval = 30  # 30초마다 상태 확인
    
    try:
        # 트리거가 감지될 시간 대기 (LLaVA 모델 로딩 시간 고려)
        print("\n⏳ 파이프라인 실행 대기 중... (트리거가 감지되면 자동으로 시작됩니다)")
        print("   💡 LLaVA 모델을 GPU에 로드하는 데 시간이 걸릴 수 있습니다...")
        logger.info("트리거 감지 대기 중 (5초)...")
        time.sleep(5)
        
        last_check_time = 0
        
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                print(f"\n⏰ 최대 대기 시간 초과 ({max_wait_minutes}분)")
                break
            
            # 주기적으로 상태 확인
            if elapsed - last_check_time >= check_interval:
                print_table_status(db, job_id, f"진행 중 ({int(elapsed)}초 경과)")
                last_check_time = elapsed
            
            # 완료 조건 확인
            job_status = check_job_status(db, job_id)
            if not job_status:
                print("❌ Job을 찾을 수 없습니다")
                break
            
            current_step = job_status["current_step"]
            status = job_status["status"]
            
            # 완료 확인: instagram_feed_gen 단계 완료
            if status == 'done' and current_step == 'instagram_feed_gen':
                elapsed_total = int(time.time() - start_time)
                print("\n✅ 파이프라인 완료!")
                print("=" * 60)
                logger.info(f"파이프라인 완료: job_id={job_id}, 소요 시간={elapsed_total}초")
                print_table_status(db, job_id, "최종 상태")
                # 상세 결과물 출력
                print_detailed_results(db, job_id)
                break
            
            # 실패 확인
            if status == 'failed':
                elapsed_total = int(time.time() - start_time)
                print("\n❌ 파이프라인 실패!")
                print("=" * 60)
                logger.error(f"파이프라인 실패: job_id={job_id}, current_step={current_step}, 소요 시간={elapsed_total}초")
                print_table_status(db, job_id, "실패 상태")
                break
            
            # Variants 완료 확인 (iou_eval 단계까지)
            variants = db.execute(text("""
                SELECT job_variants_id, creation_order, status, current_step
                FROM jobs_variants
                WHERE job_id = :job_id
                ORDER BY creation_order
            """), {"job_id": job_id}).fetchall()
            
            all_variants_done = True
            any_failed = False
            
            for variant in variants:
                if not (variant[3] == "iou_eval" and variant[2] == "done"):
                    all_variants_done = False
                if variant[2] == "failed":
                    any_failed = True
            
            # 모든 variants가 iou_eval 완료되었는지 확인
            if all_variants_done and current_step != "instagram_feed_gen":
                # iou_eval 완료 후 텍스트 생성 단계로 진행 중
                if current_step in ["ad_copy_gen_kor", "instagram_feed_gen"]:
                    # 텍스트 생성 단계 진행 중
                    pass
                elif current_step == "iou_eval":
                    # 아직 텍스트 생성 단계로 넘어가지 않음 (트리거 대기 중)
                    pass
            
            if any_failed:
                print(f"\n⚠️  일부 Variants 실패")
                logger.warning(f"일부 Variants 실패: job_id={job_id}")
                break
            
            time.sleep(5)  # 5초마다 확인
        
        # 최종 상태 출력
        elapsed_total = int(time.time() - start_time)
        print("\n" + "=" * 60)
        print("최종 상태")
        print("=" * 60)
        logger.info(f"파이프라인 모니터링 종료: job_id={job_id}, 총 소요 시간={elapsed_total}초")
        print_table_status(db, job_id, "최종 상태")
        # 상세 결과물 출력
        print_detailed_results(db, job_id)
        
    except Exception as e:
        logger.error(f"파이프라인 모니터링 중 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()


def trigger_pipeline_start(job_id: str, tenant_id: str, variant_ids: list):
    """파이프라인 시작 트리거 (test_job_variants_pipeline.py 구조 참고)"""
    print("\n" + "=" * 60)
    print("트리거 발동 (상태 업데이트)")
    print("=" * 60)
    
    logger.info(f"파이프라인 트리거 시작: job_id={job_id}, variants={len(variant_ids)}개")
    
    db = SessionLocal()
    try:
        # 전 단계 완료 조건 재검증 (안전장치)
        if not verify_pre_stage_completion(db, job_id):
            raise ValueError("전 단계 완료 조건을 만족하지 않습니다. 트리거를 발동할 수 없습니다.")
        
        for idx, variant_id in enumerate(variant_ids, 1):
            try:
                # 상태를 다시 업데이트하여 트리거 발동
                db.execute(text("""
                    UPDATE jobs_variants 
                    SET status = 'running',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :variant_id
                """), {"variant_id": variant_id})
                db.commit()
                logger.debug(f"Variant {idx}/{len(variant_ids)}: running 상태로 변경")
                
                time.sleep(0.2)  # 트리거 발동 대기
                
                db.execute(text("""
                    UPDATE jobs_variants 
                    SET status = 'done',
                        current_step = 'img_gen',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :variant_id
                """), {"variant_id": variant_id})
                db.commit()
                logger.debug(f"Variant {idx}/{len(variant_ids)}: done 상태로 변경 (트리거 발동)")
                
            except Exception as e:
                logger.error(f"Variant {idx}/{len(variant_ids)} 트리거 발동 실패: {e}", exc_info=True)
                db.rollback()
                raise
        
        print(f"✓ 총 {len(variant_ids)}개 Variants 트리거 발동 완료")
        logger.info(f"파이프라인 트리거 완료: {len(variant_ids)}개 variants")
        
        # 트리거 발동 후 상태 확인
        print_table_status(db, job_id, "트리거 발동 후")
        
    except ValueError as e:
        # 전 단계 완료 조건 불만족
        db.rollback()
        logger.error(f"전 단계 완료 조건 검증 실패: {e}", exc_info=True)
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"파이프라인 트리거 중 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()


def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="YH 파트 파이프라인 테스트")
    parser.add_argument("--tenant-id", type=str, default="yh_pipeline_test_tenant", help="Tenant ID")
    parser.add_argument("--image-path", type=str, default=None, help="이미지 파일 경로")
    parser.add_argument("--desc-kor", type=str, default="맛있는 부대찌개를 만나보세요", help="한국어 설명")
    parser.add_argument("--variants", type=int, default=3, help="Variants 개수")
    parser.add_argument("--wait", action="store_true", help="파이프라인 완료까지 대기")
    parser.add_argument("--max-wait", type=int, default=30, help="최대 대기 시간 (분)")
    
    args = parser.parse_args()
    
    try:
        logger.info("=" * 60)
        logger.info("YH 파트 파이프라인 테스트 시작")
        logger.info(f"  - Tenant ID: {args.tenant_id}")
        logger.info(f"  - Variants: {args.variants}개")
        logger.info(f"  - Max Wait: {args.max_wait}분")
        logger.info("=" * 60)
        
        # 1. Job 생성 및 JS 파트 데이터 생성
        logger.info("Step 1: Job 생성 및 전 단계 데이터 준비 시작")
        job_data = create_test_job_with_js_data(
            tenant_id=args.tenant_id,
            image_path=args.image_path,
            desc_kor=args.desc_kor,
            variants_count=args.variants
        )
        
        job_id = job_data["job_id"]
        tenant_id = job_data["tenant_id"]
        variant_ids = job_data["variant_ids"]
        
        # 2. 트리거 발동을 위해 모든 variant 상태를 업데이트
        logger.info("Step 2: 파이프라인 트리거 발동 시작")
        trigger_pipeline_start(job_id, tenant_id, variant_ids)
        
        # 3. 파이프라인 진행 상황 모니터링 (옵션)
        if args.wait:
            logger.info("Step 3: 파이프라인 모니터링 시작")
            print("\n⏳ 파이프라인 실행 대기 중... (트리거가 감지되면 자동으로 시작됩니다)")
            print("   💡 LLaVA 모델을 GPU에 로드하는 데 시간이 걸릴 수 있습니다...")
            time.sleep(5)  # 트리거가 감지될 시간 대기
            
            monitor_pipeline_progress(job_id, tenant_id, max_wait_minutes=args.max_wait)
        else:
            logger.info("Step 3: 파이프라인 모니터링 스킵 (--wait 옵션 없음)")
            print("\n💡 파이프라인 모니터링을 시작하려면 --wait 옵션을 사용하세요")
            print(f"   python {__file__} --wait --job-id {job_id}")
        
        print("\n" + "=" * 60)
        print("✅ 테스트 Job 생성 완료")
        print("=" * 60)
        print(f"Job ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        print(f"API Base URL: {API_BASE_URL}")
        print("=" * 60)
        
        logger.info("=" * 60)
        logger.info("YH 파트 파이프라인 테스트 완료")
        logger.info(f"  - Job ID: {job_id}")
        logger.info("=" * 60)
        
    except ValueError as e:
        # 전 단계 완료 조건 불만족 등 명시적 오류
        logger.error(f"테스트 실행 중 검증 실패: {e}", exc_info=True)
        print(f"\n❌ 검증 실패: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"테스트 실행 중 오류: {e}", exc_info=True)
        print(f"\n❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


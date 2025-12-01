#!/usr/bin/env python3
"""YH 파트 전체 파이프라인 테스트 (텍스트 생성 포함)
- JS 파트 데이터 임의 생성 (kor_to_eng, ad_copy_eng)
- YH 파트 파이프라인 테스트 (vlm_analyze → ... → iou_eval → eng_to_kor → instagram_feed)
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
from utils import save_asset, abs_from_url
from config import ASSETS_DIR
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
        
        # 2. 이미지 생성 또는 로드
        print(f"\n[2/8] 이미지 준비 중...")
        if image_path and os.path.exists(image_path):
            image = Image.open(image_path)
            print(f"  - Image Path: {image_path}")
        else:
            # 더미 이미지 생성
            image = Image.new('RGB', (1024, 1024), color='lightblue')
            draw = ImageDraw.Draw(image)
            draw.rectangle([100, 100, 924, 924], fill='white', outline='black', width=5)
            draw.text((400, 500), "Test Image", fill='black')
            print(f"  - 더미 이미지 생성: 1024x1024")
        
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
        
        # 8. JS 파트 데이터 임의 생성 (kor_to_eng, ad_copy_eng)
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
        
        print("\n" + "=" * 60)
        print("✅ Job 생성 완료")
        print("=" * 60)
        print(f"Job ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        print(f"Variants: {len(variant_ids)}개")
        print(f"JS 파트 데이터: kor_to_eng, ad_copy_eng 생성 완료")
        print("=" * 60)
        
        return {
            "job_id": str(job_id),
            "tenant_id": tenant_id,
            "variant_ids": [str(vid) for vid in variant_ids],
            "image_asset_id": str(image_asset_id),
            "asset_url": asset_url,
            "desc_kor": desc_kor,
            "desc_eng": desc_eng,
            "ad_copy_eng": ad_copy_eng
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Job 생성 중 오류: {e}", exc_info=True)
        raise
    finally:
        db.close()


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


def monitor_pipeline_progress(job_id: str, tenant_id: str, max_wait_minutes: int = 30):
    """파이프라인 진행 상황 모니터링"""
    print("\n" + "=" * 60)
    print("파이프라인 진행 상황 모니터링")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"최대 대기 시간: {max_wait_minutes}분")
    print("=" * 60)
    
    db = SessionLocal()
    start_time = time.time()
    max_wait_seconds = max_wait_minutes * 60
    check_interval = 10  # 10초마다 확인
    
    last_step = None
    last_status = None
    
    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > max_wait_seconds:
                print(f"\n⏰ 최대 대기 시간 초과 ({max_wait_minutes}분)")
                break
            
            # Job 상태 확인
            job_status = check_job_status(db, job_id)
            if not job_status:
                print("❌ Job을 찾을 수 없습니다")
                break
            
            current_step = job_status["current_step"]
            status = job_status["status"]
            
            # 상태 변화 감지
            if current_step != last_step or status != last_status:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 상태 변화 감지:")
                print(f"  Step: {last_step} → {current_step}")
                print(f"  Status: {last_status} → {status}")
                last_step = current_step
                last_status = status
            
            # 완료 확인
            if status == 'done' and current_step == 'instagram_feed_gen':
                print("\n✅ 파이프라인 완료!")
                print("=" * 60)
                check_variants_status(db, job_id)
                check_txt_ad_copy_generations(db, job_id)
                check_instagram_feeds(db, job_id)
                break
            
            # 실패 확인
            if status == 'failed':
                print("\n❌ 파이프라인 실패!")
                print("=" * 60)
                check_variants_status(db, job_id)
                check_txt_ad_copy_generations(db, job_id)
                break
            
            # 진행 중
            elapsed_min = int(elapsed / 60)
            elapsed_sec = int(elapsed % 60)
            print(f"\r[{elapsed_min:02d}:{elapsed_sec:02d}] 진행 중... {current_step} ({status})", end="", flush=True)
            
            time.sleep(check_interval)
        
        print("\n")
        
    finally:
        db.close()


def trigger_pipeline_start(job_id: str, tenant_id: str, variant_ids: list):
    """파이프라인 시작 트리거 (vlm_analyze부터 시작)"""
    print("\n" + "=" * 60)
    print("파이프라인 시작 트리거")
    print("=" * 60)
    
    # Job 상태를 img_gen에서 vlm_analyze로 변경하여 트리거
    db = SessionLocal()
    try:
        # Job 상태 업데이트 (트리거 발동)
        db.execute(text("""
            UPDATE jobs
            SET status = 'running',
                current_step = 'img_gen',
                updated_at = CURRENT_TIMESTAMP
            WHERE job_id = :job_id
        """), {"job_id": job_id})
        
        # Variants 상태 업데이트
        for variant_id in variant_ids:
            db.execute(text("""
                UPDATE jobs_variants
                SET status = 'queued',
                    current_step = 'vlm_analyze',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :variant_id
            """), {"variant_id": variant_id})
        
        db.commit()
        print(f"✓ Job 및 Variants 상태 업데이트 완료")
        print(f"  - Job: img_gen → vlm_analyze 트리거 준비")
        print(f"  - Variants: {len(variant_ids)}개 queued 상태로 변경")
        
        # NOTIFY 직접 발행 (트리거 강제 실행)
        print(f"\n🔔 NOTIFY 발행 중...")
        db.execute(text("""
            SELECT pg_notify(
                'job_state_changed',
                json_build_object(
                    'job_id', :job_id::text,
                    'current_step', 'img_gen',
                    'status', 'done',
                    'tenant_id', :tenant_id,
                    'updated_at', NOW()
                )::text
            )
        """), {
            "job_id": job_id,
            "tenant_id": tenant_id
        })
        db.commit()
        print(f"✓ NOTIFY 발행 완료")
        
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
        # 1. Job 생성 및 JS 파트 데이터 생성
        job_data = create_test_job_with_js_data(
            tenant_id=args.tenant_id,
            image_path=args.image_path,
            desc_kor=args.desc_kor,
            variants_count=args.variants
        )
        
        job_id = job_data["job_id"]
        tenant_id = job_data["tenant_id"]
        variant_ids = job_data["variant_ids"]
        
        # 2. 파이프라인 시작 트리거
        trigger_pipeline_start(job_id, tenant_id, variant_ids)
        
        # 3. 진행 상황 모니터링 (옵션)
        if args.wait:
            monitor_pipeline_progress(job_id, tenant_id, max_wait_minutes=args.max_wait)
        else:
            print("\n💡 파이프라인 모니터링을 시작하려면 --wait 옵션을 사용하세요")
            print(f"   python {__file__} --wait --job-id {job_id}")
        
        print("\n" + "=" * 60)
        print("✅ 테스트 Job 생성 완료")
        print("=" * 60)
        print(f"Job ID: {job_id}")
        print(f"Tenant ID: {tenant_id}")
        print(f"API Base URL: {API_BASE_URL}")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"테스트 실행 중 오류: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


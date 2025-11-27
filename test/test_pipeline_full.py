"""전체 Pipeline 테스트: llava stage1 -> yolo -> planner -> overlay"""
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

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import SessionLocal, ImageAsset, Job, JobInput, Detection, YOLORun, PlannerProposal, OverlayLayout
from utils import save_asset, abs_from_url
from config import ASSETS_DIR
import logging

logger = logging.getLogger(__name__)


def setup_pipeline_job(db: Session, tenant_id: str, image_path: str, text_path: str) -> dict:
    """Pipeline 테스트용 job 생성 (img_gen 완료 상태)"""
    print("\n" + "=" * 60)
    print("Pipeline 테스트 Job 생성 (img_gen 완료 상태)")
    print("=" * 60)
    
    # 1. 이미지 로드 및 저장
    print(f"\n[1/5] 이미지 로드 및 저장 중...")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"이미지를 찾을 수 없습니다: {image_path}")
    
    image = Image.open(image_path)
    print(f"  - Image Path: {image_path}")
    print(f"  - Image Size: {image.size[0]}x{image.size[1]}")
    
    # ASSETS_DIR에 저장
    asset_meta = save_asset(tenant_id, "pipeline_test", image, ".png")
    asset_url = asset_meta["url"]
    actual_image_path = abs_from_url(asset_url)
    print(f"  - Asset URL: {asset_url}")
    print(f"  - Saved Path: {actual_image_path}")
    
    # 2. 텍스트 파일 읽기
    print(f"\n[2/5] 텍스트 파일 읽기 중...")
    if not os.path.exists(text_path):
        raise FileNotFoundError(f"텍스트 파일을 찾을 수 없습니다: {text_path}")
    
    with open(text_path, 'r', encoding='utf-8') as f:
        ad_copy_text = f.read().strip().strip('"').strip("'")
    print(f"  - Text Path: {text_path}")
    print(f"  - Ad Copy Text: {ad_copy_text[:50]}...")
    
    # 3. tenant 확인/생성
    print(f"\n[3/5] tenant 확인/생성 중...")
    try:
        tenant_check = db.execute(
            text("SELECT tenant_id FROM tenants WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id}
        ).first()
        
        if not tenant_check:
            db.execute(
                text("INSERT INTO tenants (tenant_id, display_name) VALUES (:tenant_id, :display_name)"),
                {"tenant_id": tenant_id, "display_name": f"Pipeline Test Tenant - {tenant_id}"}
            )
            db.commit()
            print(f"✓ tenant '{tenant_id}' 생성 완료")
        else:
            print(f"✓ tenant '{tenant_id}' 확인 완료")
    except Exception as e:
        print(f"  ⚠ tenant 확인 중 오류: {e}")
        db.rollback()
        raise
    
    # 4. image_assets 확인/생성
    print(f"\n[4/5] image_assets 확인/생성 중...")
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
                "image_type": "generated",  # img_gen 단계에서 생성된 이미지
                "image_url": asset_url,
                "width": image.size[0],
                "height": image.size[1],
                "tenant_id": tenant_id,
                "uid": image_asset_uid
            }
        )
        db.commit()
        print(f"✓ image_asset 레코드 생성 완료: {image_asset_id}")
    
    # 5. jobs 및 job_inputs 생성 (img_gen 완료 상태)
    print(f"\n[5/5] jobs 및 job_inputs 생성 중...")
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
            "desc_eng": ad_copy_text
        }
    )
    db.commit()
    print(f"✓ job 및 job_inputs 레코드 생성 완료:")
    print(f"  - Job ID: {job_uuid}")
    print(f"  - Status: done")
    print(f"  - Current Step: img_gen")
    print(f"  - Ad Copy: {ad_copy_text[:50]}...")
    
    return {
        "tenant_id": tenant_id,
        "job_id": str(job_uuid),
        "image_asset_id": str(image_asset_id),
        "asset_url": asset_url,
        "ad_copy_text": ad_copy_text
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
        
        # 폰트 추천 확인
        font_rec = result.get('font_recommendation')
        if font_rec:
            print(f"\n  폰트 추천:")
            print(f"    - Font Style: {font_rec.get('font_style', 'N/A')}")
            print(f"    - Font Size Category: {font_rec.get('font_size_category', 'N/A')}")
            print(f"    - Font Color Hex: {font_rec.get('font_color_hex', 'N/A')}")
            if font_rec.get('reasoning'):
                print(f"    - Reasoning: {font_rec.get('reasoning')[:100]}...")
        else:
            print(f"\n  ⚠ 폰트 추천이 없습니다.")
        
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
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_llava_stage2(job_id: str, tenant_id: str, overlay_id: str = None, api_url: str = "http://localhost:8011") -> dict:
    """LLaVA Stage 2 Judge API 테스트"""
    print("\n" + "=" * 60)
    print("LLaVA Stage 2 Judge API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/llava/stage2/judge"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id
    }
    
    if overlay_id:
        request_data["overlay_id"] = overlay_id
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Overlay ID: {overlay_id or 'None (자동 조회)'}")
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Job ID: {result.get('job_id')}")
        print(f"  - VLM Trace ID: {result.get('vlm_trace_id')}")
        print(f"  - On Brief: {result.get('on_brief')}")
        print(f"  - Occlusion: {result.get('occlusion')}")
        print(f"  - Contrast OK: {result.get('contrast_ok')}")
        print(f"  - CTA Present: {result.get('cta_present')}")
        print(f"  - Issues: {result.get('issues', [])}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_ocr_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """OCR 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("OCR 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/ocr/evaluate"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Overlay ID: {overlay_id}")
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Evaluation ID: {result.get('evaluation_id')}")
        print(f"  - OCR Confidence: {result.get('ocr_confidence', 0):.3f}")
        print(f"  - OCR Accuracy: {result.get('ocr_accuracy', 0):.3f}")
        print(f"  - Character Match Rate: {result.get('character_match_rate', 0):.3f}")
        print(f"  - Word Match Rate: {result.get('word_match_rate', 0):.3f}")
        print(f"  - Recognized Text: {result.get('recognized_text', '')[:50]}...")
        print(f"  - Original Text: {result.get('original_text', '')[:50]}...")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_readability_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """가독성 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("가독성 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/readability/evaluate"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Overlay ID: {overlay_id}")
    
    try:
        response = requests.post(url, json=request_data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Evaluation ID: {result.get('evaluation_id')}")
        print(f"  - Contrast Ratio: {result.get('contrast_ratio', 0):.2f}:1")
        print(f"  - Readability Score: {result.get('readability_score', 0):.3f}")
        print(f"  - WCAG AA Compliant: {result.get('wcag_aa_compliant', False)}")
        print(f"  - WCAG AAA Compliant: {result.get('wcag_aaa_compliant', False)}")
        print(f"  - Text Color: {result.get('text_color', 'N/A')}")
        print(f"  - Background Color: {result.get('background_color', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_iou_eval(job_id: str, tenant_id: str, overlay_id: str, api_url: str = "http://localhost:8011") -> dict:
    """IoU 평가 API 테스트"""
    print("\n" + "=" * 60)
    print("IoU 평가 API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/iou/evaluate"
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "overlay_id": overlay_id
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Overlay ID: {overlay_id}")
    
    try:
        response = requests.post(url, json=request_data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Evaluation ID: {result.get('evaluation_id')}")
        print(f"  - IoU with Food: {result.get('iou_with_food', 0):.4f}")
        print(f"  - Overlap Detected: {result.get('overlap_detected', False)}")
        print(f"  - Max IoU Detection ID: {result.get('max_iou_detection_id', 'N/A')}")
        
        return result
        
    except requests.exceptions.HTTPError as e:
        print(f"\n❌ HTTP 오류: {e}")
        if hasattr(e.response, 'text'):
            print(f"  응답 내용: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise


def test_overlay(job_id: str, tenant_id: str, proposal_id: str = None, api_url: str = "http://localhost:8011") -> dict:
    """Overlay API 테스트"""
    print("\n" + "=" * 60)
    print("Overlay API 테스트")
    print("=" * 60)
    
    url = f"{api_url}/api/yh/overlay"
    
    # job_inputs에서 텍스트 가져오기
    db = SessionLocal()
    try:
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if job_input:
            ad_copy_text = job_input.desc_eng or "Test Text"
        else:
            ad_copy_text = "Test Text"
    finally:
        db.close()
    
    request_data = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "proposal_id": proposal_id,
        "text": ad_copy_text,
        "x_align": "center",
        "y_align": "top"
        # text_size 제거: 동적 폰트 크기 조정을 위해 제거
    }
    
    print(f"\n요청 URL: {url}")
    print(f"요청 데이터:")
    print(f"  - Job ID: {job_id}")
    print(f"  - Tenant ID: {tenant_id}")
    print(f"  - Proposal ID: {proposal_id or 'None'}")
    print(f"  - Text: {ad_copy_text[:50]}...")
    
    try:
        response = requests.post(url, json=request_data, timeout=300)
        response.raise_for_status()
        
        result = response.json()
        
        # Render URL에서 이미지 파일명 추출
        render_url = result.get('render', {}).get('url', '')
        image_filename = render_url.split('/')[-1] if render_url else 'N/A'
        
        print(f"\n✓ API 호출 성공!")
        print(f"\n응답 데이터:")
        print(f"  - Job ID: {result.get('job_id')}")
        print(f"  - Overlay ID: {result.get('overlay_id', 'N/A')}")
        print(f"  - Render URL: {render_url}")
        print(f"  - 저장된 이미지 파일명: {image_filename}")
        
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
        job = check_job_status(db, job_id, expected_step="overlay", expected_status="done")
        if not job:
            return False
        
        # job_inputs 확인
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if job_input:
            print(f"\n  Job Input:")
            print(f"    - Image Asset ID: {job_input.img_asset_id}")
            print(f"    - Ad Copy: {job_input.desc_eng[:50] if job_input.desc_eng else 'N/A'}...")
        
        # vlm_traces 확인 (LLaVA Stage 1)
        from database import VLMTrace
        vlm_traces = db.query(VLMTrace).filter(VLMTrace.job_id == uuid.UUID(job_id)).all()
        if vlm_traces:
            print(f"\n  VLM Traces: {len(vlm_traces)}개")
            for trace in vlm_traces:
                print(f"    - Provider: {trace.provider}, Operation: {trace.operation_type}")
                # 폰트 추천 확인
                if trace.response and trace.operation_type == 'analyze':
                    font_rec = trace.response.get('font_recommendation')
                    if font_rec:
                        print(f"      폰트 추천:")
                        print(f"        - Font Style: {font_rec.get('font_style', 'N/A')}")
                        print(f"        - Font Size Category: {font_rec.get('font_size_category', 'N/A')}")
                        print(f"        - Font Color Hex: {font_rec.get('font_color_hex', 'N/A')}")
                    else:
                        print(f"      ⚠ 폰트 추천이 없습니다.")
        
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
                if latest_proposal.layout and isinstance(latest_proposal.layout, dict):
                    proposals_count = len(latest_proposal.layout.get('proposals', []))
                    print(f"    - Layout에 저장된 Proposals 개수: {proposals_count}")
        
        # overlay_layouts 확인
        overlay_layouts = db.query(OverlayLayout).filter(
            OverlayLayout.proposal_id.in_(
                [p.proposal_id for p in planner_proposals] if planner_proposals else []
            )
        ).all()
        
        if overlay_layouts:
            print(f"\n  Overlay Layouts: {len(overlay_layouts)}개")
            for i, layout in enumerate(overlay_layouts[:3]):  # 최대 3개만 출력
                print(f"    Overlay {i+1}: {layout.overlay_id}")
        
        print(f"\n✓ DB 레코드 확인 완료!")
        return True
        
    except Exception as e:
        print(f"\n❌ DB 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_file_paths(db: Session, job_id: str):
    """파일 경로 정보 출력 및 제안 영역 시각화"""
    print("\n" + "=" * 60)
    print("파일 경로 정보")
    print("=" * 60)
    
    try:
        job = db.query(Job).filter(Job.job_id == uuid.UUID(job_id)).first()
        if not job:
            print("⚠ Job을 찾을 수 없습니다.")
            return
        
        tenant_id = job.tenant_id
        
        job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
        if not job_input:
            print("⚠ Job input을 찾을 수 없습니다.")
            return
        
        # 1. 원본 이미지 경로
        image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == job_input.img_asset_id).first()
        if image_asset:
            original_image_path = abs_from_url(image_asset.image_url)
            print(f"\n[원본 이미지]")
            print(f"  - URL: {image_asset.image_url}")
            print(f"  - 절대 경로: {original_image_path}")
        
        # 2. Forbidden mask 경로
        yolo_run = db.query(YOLORun).filter(YOLORun.job_id == uuid.UUID(job_id)).first()
        if yolo_run and yolo_run.forbidden_mask_url:
            forbidden_mask_path = abs_from_url(yolo_run.forbidden_mask_url)
            print(f"\n[Forbidden Mask]")
            print(f"  - URL: {yolo_run.forbidden_mask_url}")
            print(f"  - 절대 경로: {forbidden_mask_path}")
        
        # 3. 제안 영역 시각화 이미지 생성
        planner_proposals = db.query(PlannerProposal).filter(
            PlannerProposal.image_asset_id == job_input.img_asset_id
        ).order_by(PlannerProposal.created_at.desc()).all()
        
        if planner_proposals and image_asset:
            latest_proposal = planner_proposals[0]
            if latest_proposal.layout and isinstance(latest_proposal.layout, dict):
                proposals_list = latest_proposal.layout.get('proposals', [])
                if proposals_list and os.path.exists(original_image_path):
                    # 원본 이미지 로드
                    img = Image.open(original_image_path).convert("RGBA")
                    w, h = img.size
                    draw = ImageDraw.Draw(img)
                    
                    # 각 proposal 영역 그리기
                    for i, prop in enumerate(proposals_list):
                        xywh = prop.get("xywh", [])
                        if len(xywh) == 4:
                            x, y, width, height = xywh
                            # 정규화된 좌표를 픽셀 좌표로 변환
                            px1 = int(x * w)
                            py1 = int(y * h)
                            px2 = int((x + width) * w)
                            py2 = int((y + height) * h)
                            
                            # 박스 그리기 (색상: 빨강, 초록, 파랑 순서)
                            colors = [(255, 0, 0, 200), (0, 255, 0, 200), (0, 0, 255, 200), 
                                     (255, 255, 0, 200), (255, 0, 255, 200), (0, 255, 255, 200)]
                            color = colors[i % len(colors)]
                            
                            # 박스 그리기
                            draw.rectangle([px1, py1, px2, py2], outline=color, width=3)
                            
                            # source 라벨 추가
                            source = prop.get("source", f"proposal_{i+1}")
                            score = prop.get("score", 0)
                            label = f"{source}\nscore:{score:.2f}"
                            draw.text((px1 + 5, py1 + 5), label, fill=color)
                    
                    # 제안 영역 시각화 이미지 저장
                    output_dir = os.path.join(ASSETS_DIR, "yh", "tenants", tenant_id, "proposals")
                    os.makedirs(output_dir, exist_ok=True)
                    proposal_viz_filename = f"proposals_{job_id[:8]}.png"
                    proposal_viz_path = os.path.join(output_dir, proposal_viz_filename)
                    img.save(proposal_viz_path)
                    
                    proposal_viz_url = f"/assets/yh/tenants/{tenant_id}/proposals/{proposal_viz_filename}"
                    print(f"\n[제안 영역 시각화]")
                    print(f"  - URL: {proposal_viz_url}")
                    print(f"  - 절대 경로: {proposal_viz_path}")
                    print(f"  - 제안 개수: {len(proposals_list)}")
        
        # 4. 최종 Overlay 이미지 경로
        # proposal_id로 조회 시도
        proposal_ids = [p.proposal_id for p in planner_proposals] if planner_proposals else []
        overlay_layouts = []
        
        if proposal_ids:
            overlay_layouts = db.query(OverlayLayout).filter(
                OverlayLayout.proposal_id.in_(proposal_ids)
            ).order_by(OverlayLayout.created_at.desc()).all()
        
        # proposal_id가 없거나 찾지 못한 경우, 최신 overlay_layouts 조회 (proposal_id가 None인 경우도 포함)
        if not overlay_layouts:
            overlay_layouts = db.query(OverlayLayout).order_by(
                OverlayLayout.created_at.desc()
            ).limit(5).all()
            # 같은 image_asset_id를 가진 proposal과 연관된 overlay 찾기
            if planner_proposals and image_asset:
                for overlay in overlay_layouts:
                    if overlay.proposal_id and overlay.proposal_id in proposal_ids:
                        overlay_layouts = [overlay]
                        break
        
        if overlay_layouts:
            latest_overlay = overlay_layouts[0]
            if latest_overlay.layout and isinstance(latest_overlay.layout, dict):
                render = latest_overlay.layout.get('render', {})
                overlay_url = render.get('url', '')
                if overlay_url:
                    overlay_path = abs_from_url(overlay_url)
                    print(f"\n[최종 Overlay 이미지]")
                    print(f"  - URL: {overlay_url}")
                    print(f"  - 절대 경로: {overlay_path}")
                    print(f"  - Overlay ID: {latest_overlay.overlay_id}")
                    print(f"  - 파일명: {os.path.basename(overlay_path)}")
                else:
                    print(f"\n[최종 Overlay 이미지]")
                    print(f"  - ⚠ render 정보에 URL이 없습니다.")
        else:
            print(f"\n[최종 Overlay 이미지]")
            print(f"  - ⚠ Overlay layout을 찾을 수 없습니다.")
        
    except Exception as e:
        print(f"\n❌ 파일 경로 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 테스트 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="전체 Pipeline 테스트: llava stage1 -> yolo -> planner -> overlay")
    parser.add_argument("--job-id", type=str, default=None,
                       help="테스트할 job_id (없으면 새로 생성)")
    parser.add_argument("--tenant-id", default="pipeline_test_tenant",
                       help="테스트용 tenant_id")
    parser.add_argument("--image-path", type=str, 
                       default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipeline_test", "pipeline_test_image9.png"),
                       help="사용할 이미지 경로")
    parser.add_argument("--text-path", type=str,
                       default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipeline_test", "pipeline_test_txt_kor1.txt"),
                       help="사용할 텍스트 파일 경로")
    parser.add_argument("--api-url", default="http://localhost:8011",
                       help="API 서버 URL")
    parser.add_argument("--skip-llava", action="store_true",
                       help="LLaVA Stage 1 건너뛰기")
    parser.add_argument("--skip-yolo", action="store_true",
                       help="YOLO 건너뛰기")
    parser.add_argument("--skip-planner", action="store_true",
                       help="Planner 건너뛰기")
    parser.add_argument("--skip-overlay", action="store_true",
                       help="Overlay 건너뛰기")
    parser.add_argument("--skip-llava-stage2", action="store_true",
                       help="LLaVA Stage 2 건너뛰기")
    parser.add_argument("--skip-ocr", action="store_true",
                       help="OCR 평가 건너뛰기")
    parser.add_argument("--skip-readability", action="store_true",
                       help="가독성 평가 건너뛰기")
    parser.add_argument("--skip-iou", action="store_true",
                       help="IoU 평가 건너뛰기")
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
            # 새 job 생성 (img_gen 완료 상태)
            test_data = setup_pipeline_job(db, args.tenant_id, args.image_path, args.text_path)
            job_id = test_data["job_id"]
            tenant_id = test_data["tenant_id"]
        
        # 초기 상태 확인
        print("\n" + "=" * 60)
        print("초기 Job 상태 확인")
        print("=" * 60)
        check_job_status(db, job_id, expected_step="img_gen", expected_status="done")
        
        # LLaVA Stage 1 테스트
        proposal_id = None
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
        
        # Planner 테스트
        if not args.skip_planner:
            planner_result = test_planner(job_id, tenant_id, args.api_url)
            
            # Planner 이후 상태 확인
            print("\n" + "=" * 60)
            print("Planner 이후 Job 상태 확인")
            print("=" * 60)
            check_job_status(db, job_id, expected_step="planner", expected_status="done")
            
            # proposal_id 가져오기: DB에 저장된 planner_proposals.proposal_id 사용
            # (API 응답의 proposal_id는 각 proposal 내부 ID이므로, DB의 proposal_id를 사용해야 함)
            proposal_id = None
            if planner_result.get('proposals'):
                # DB에서 최신 planner_proposal 찾기
                job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
                if job_input and job_input.img_asset_id:
                    latest_proposal = db.query(PlannerProposal).filter(
                        PlannerProposal.image_asset_id == job_input.img_asset_id
                    ).order_by(PlannerProposal.created_at.desc()).first()
                    if latest_proposal:
                        proposal_id = str(latest_proposal.proposal_id)
                        print(f"  - DB에서 찾은 Proposal ID: {proposal_id}")
        else:
            print("\n⚠ Planner 건너뛰기")
        
        # Overlay 테스트
        overlay_id = None
        if not args.skip_overlay:
            overlay_result = test_overlay(job_id, tenant_id, proposal_id, args.api_url)
            overlay_id = overlay_result.get('overlay_id')
            
            # Overlay 이후 상태 확인
            print("\n" + "=" * 60)
            print("Overlay 이후 Job 상태 확인")
            print("=" * 60)
            check_job_status(db, job_id, expected_step="overlay", expected_status="done")
        else:
            print("\n⚠ Overlay 건너뛰기")
            # overlay_id를 DB에서 찾기
            if not overlay_id:
                job_input = db.query(JobInput).filter(JobInput.job_id == uuid.UUID(job_id)).first()
                if job_input:
                    planner_proposals = db.query(PlannerProposal).filter(
                        PlannerProposal.image_asset_id == job_input.img_asset_id
                    ).order_by(PlannerProposal.created_at.desc()).all()
                    if planner_proposals:
                        overlay_layout = db.query(OverlayLayout).filter(
                            OverlayLayout.proposal_id == planner_proposals[0].proposal_id
                        ).order_by(OverlayLayout.created_at.desc()).first()
                        if overlay_layout:
                            overlay_id = str(overlay_layout.overlay_id)
        
        # LLaVA Stage 2 테스트
        if not args.skip_llava_stage2:
            if overlay_id:
                llava_stage2_result = test_llava_stage2(job_id, tenant_id, overlay_id, args.api_url)
                
                # LLaVA Stage 2 이후 상태 확인
                print("\n" + "=" * 60)
                print("LLaVA Stage 2 이후 Job 상태 확인")
                print("=" * 60)
                check_job_status(db, job_id, expected_step="vlm_judge", expected_status="done")
            else:
                print("\n⚠ Overlay ID가 없어 LLaVA Stage 2를 건너뜁니다")
        else:
            print("\n⚠ LLaVA Stage 2 건너뛰기")
        
        # 정량 평가 테스트
        if overlay_id:
            # OCR 평가
            if not args.skip_ocr:
                ocr_result = test_ocr_eval(job_id, tenant_id, overlay_id, args.api_url)
            else:
                print("\n⚠ OCR 평가 건너뛰기")
            
            # 가독성 평가
            if not args.skip_readability:
                readability_result = test_readability_eval(job_id, tenant_id, overlay_id, args.api_url)
            else:
                print("\n⚠ 가독성 평가 건너뛰기")
            
            # IoU 평가
            if not args.skip_iou:
                iou_result = test_iou_eval(job_id, tenant_id, overlay_id, args.api_url)
            else:
                print("\n⚠ IoU 평가 건너뛰기")
        else:
            print("\n⚠ Overlay ID가 없어 정량 평가를 건너뜁니다")
        
        # 최종 DB 레코드 확인
        verify_db_records(db, job_id)
        
        # 파일 경로 정보 출력
        print_file_paths(db, job_id)
        
        print("\n" + "=" * 60)
        print("✓ Pipeline 테스트 완료!")
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



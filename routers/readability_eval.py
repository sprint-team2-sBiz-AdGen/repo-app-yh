
"""가독성 평가 라우터"""
########################################################
# 가독성 평가 API
# - 텍스트와 배경 색상 대비 확인
# - WCAG 2.1 기준 검증
# - evaluations 테이블에 결과 저장
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-26
# author: LEEYH205
# description: Readability evaluation API
# version: 1.0.0
# status: production
# tags: readability, evaluation
# dependencies: fastapi, pydantic, PIL, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
import time
from models import ReadabilityEvalIn, ReadabilityEvalOut
from utils import abs_from_url
from services.readability_service import evaluate_readability
from database import get_db, Job, OverlayLayout
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/readability", tags=["readability-eval"])


@router.post("/evaluate", response_model=ReadabilityEvalOut)
def evaluate_readability_api(body: ReadabilityEvalIn, db: Session = Depends(get_db)):
    """
    가독성 평가: 텍스트와 배경 색상 대비 확인
    
    Args:
        body: ReadabilityEvalIn 모델
            - job_id: 기존 job의 ID - 필수
            - tenant_id: 테넌트 ID - 필수
            - overlay_id: Overlay ID - 필수 (overlay_layouts에서 색상 정보 조회)
    
    Returns:
        ReadabilityEvalOut:
            - job_id: str
            - evaluation_id: str
            - overlay_id: str
            - contrast_ratio: float
            - wcag_aa_compliant: bool
            - wcag_aaa_compliant: bool
            - readability_score: float
    """
    try:
        # Step 0: job_id 검증
        try:
            job_id = uuid.UUID(body.job_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid job_id format: {body.job_id}"
            )
        
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: job_id={body.job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {body.job_id}"
            )
        
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # Step 1: overlay_id 검증 및 데이터 조회
        try:
            overlay_id_uuid = uuid.UUID(body.overlay_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid overlay_id format: {body.overlay_id}"
            )
        
        overlay = db.query(OverlayLayout).filter(OverlayLayout.overlay_id == overlay_id_uuid).first()
        if not overlay:
            logger.error(f"Overlay layout not found: overlay_id={body.overlay_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Overlay layout not found: {body.overlay_id}"
            )
        
        # overlay.layout에서 색상 정보 가져오기
        layout = overlay.layout if isinstance(overlay.layout, dict) else json.loads(overlay.layout) if isinstance(overlay.layout, str) else {}
        text_color = layout.get('text_color', 'FFFFFF')
        overlay_color = layout.get('overlay_color')
        text_size = layout.get('text_size')
        render = layout.get('render', {})
        render_asset_url = render.get('url')
        
        if not render_asset_url:
            logger.error(f"Render URL not found in overlay layout: overlay_id={body.overlay_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Render URL not found in overlay layout"
            )
        
        # Step 2: 이미지 로드
        try:
            image = Image.open(abs_from_url(render_asset_url)).convert("RGB")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        # Step 3: 텍스트 영역 좌표 계산
        img_w, img_h = image.size
        text_region = None
        if overlay.x_ratio is not None and overlay.y_ratio is not None and overlay.width_ratio is not None and overlay.height_ratio is not None:
            x_px = int(overlay.x_ratio * img_w)
            y_px = int(overlay.y_ratio * img_h)
            width_px = int(overlay.width_ratio * img_w)
            height_px = int(overlay.height_ratio * img_h)
            text_region = (x_px, y_px, width_px, height_px)
            logger.info(f"텍스트 영역: ({x_px}, {y_px}, {width_px}, {height_px})")
        
        # Step 4: 가독성 평가 실행
        start_time = time.time()
        try:
            readability_result = evaluate_readability(
                text_color=text_color,
                background_color=overlay_color,
                image=image,
                text_region=text_region,
                text_size=text_size
            )
        except Exception as e:
            logger.error(f"가독성 평가 실패: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"가독성 평가 중 오류가 발생했습니다: {str(e)}")
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Step 5: evaluations 테이블에 저장
        evaluation_id = uuid.uuid4()
        metrics = {
            "contrast_ratio": readability_result.get("contrast_ratio", 0.0),
            "wcag_aa_compliant": readability_result.get("wcag_aa_compliant", False),
            "wcag_aaa_compliant": readability_result.get("wcag_aaa_compliant", False),
            "readability_score": readability_result.get("readability_score", 0.0),
            "text_color": text_color,
            "overlay_color": overlay_color,
            "text_color_rgb": readability_result.get("text_color_rgb"),
            "background_color_rgb": readability_result.get("background_color_rgb"),
            "is_large_text": readability_result.get("is_large_text", False),
            "text_size": text_size,
            "latency_ms": latency_ms
        }
        
        try:
            db.execute(
                text("""
                    INSERT INTO evaluations (
                        evaluation_id, job_id, overlay_id, evaluation_type,
                        metrics, created_at, updated_at
                    )
                    VALUES (
                        :evaluation_id, :job_id, :overlay_id, :evaluation_type,
                        CAST(:metrics AS jsonb),
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "evaluation_id": evaluation_id,
                    "job_id": job_id,
                    "overlay_id": overlay_id_uuid,
                    "evaluation_type": "readability",
                    "metrics": json.dumps(metrics)
                }
            )
            db.commit()
            logger.info(f"가독성 평가 결과 저장 완료: evaluation_id={evaluation_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"가독성 평가 결과 저장 실패: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"가독성 평가 결과 저장 중 오류가 발생했습니다: {str(e)}"
            )
        
        # Step 6: 응답 반환
        return ReadabilityEvalOut(
            job_id=body.job_id,
            evaluation_id=str(evaluation_id),
            overlay_id=body.overlay_id,
            contrast_ratio=readability_result.get("contrast_ratio", 0.0),
            wcag_aa_compliant=readability_result.get("wcag_aa_compliant", False),
            wcag_aaa_compliant=readability_result.get("wcag_aaa_compliant", False),
            readability_score=readability_result.get("readability_score", 0.0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"가독성 평가 API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


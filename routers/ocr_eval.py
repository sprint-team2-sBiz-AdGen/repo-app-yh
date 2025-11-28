
"""OCR 평가 라우터"""
########################################################
# OCR 평가 API
# - 텍스트 인식률 확인
# - 원본 텍스트와 OCR 인식 텍스트 비교
# - evaluations 테이블에 결과 저장
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-28
# author: LEEYH205
# description: OCR evaluation API
# version: 1.1.0
# status: production
# tags: ocr, evaluation
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
from models import OCREvalIn, OCREvalOut
from utils import abs_from_url
from services.ocr_service import extract_text_from_image, calculate_ocr_accuracy
from database import get_db, Job, OverlayLayout, JobVariant
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/ocr", tags=["ocr-eval"])


@router.post("/evaluate", response_model=OCREvalOut)
def evaluate_ocr(body: OCREvalIn, db: Session = Depends(get_db)):
    """
    OCR 평가: 텍스트 인식률 확인
    
    Args:
        body: OCREvalIn 모델
            - job_id: 기존 job의 ID - 필수
            - tenant_id: 테넌트 ID - 필수
            - overlay_id: Overlay ID - 필수 (overlay_layouts에서 텍스트와 이미지 URL 조회)
    
    Returns:
        OCREvalOut:
            - job_id: str
            - evaluation_id: str
            - overlay_id: str
            - ocr_confidence: float
            - ocr_accuracy: float
            - character_match_rate: float
            - recognized_text: str
            - original_text: str
    """
    try:
        # Step 0: job_variants_id 및 job_id 검증
        try:
            job_variants_id = uuid.UUID(body.job_variants_id)
            job_id = uuid.UUID(body.job_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format: {str(e)}"
            )
        
        # job_variants 조회
        job_variant = db.query(JobVariant).filter(JobVariant.job_variants_id == job_variants_id).first()
        if not job_variant:
            logger.error(f"Job variant not found: job_variants_id={body.job_variants_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job variant not found: {body.job_variants_id}"
            )
        
        # job 조회 및 검증
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: job_id={body.job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {body.job_id}"
            )
        
        # job_variant와 job의 job_id 일치 확인
        if job_variant.job_id != job_id:
            logger.error(f"Job variant job_id mismatch: job_variant.job_id={job_variant.job_id}, request.job_id={job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant job_id mismatch"
            )
        
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # Step 0.5: OCR 시작 - job_variants 상태 업데이트 (current_step='ocr_eval', status='running')
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'ocr_eval',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=ocr_eval")
        
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
        
        # overlay.layout에서 텍스트와 이미지 URL 가져오기
        layout = overlay.layout if isinstance(overlay.layout, dict) else json.loads(overlay.layout) if isinstance(overlay.layout, str) else {}
        original_text = layout.get('text', '')
        render = layout.get('render', {})
        render_asset_url = render.get('url')
        
        if not render_asset_url:
            logger.error(f"Render URL not found in overlay layout: overlay_id={body.overlay_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Render URL not found in overlay layout"
            )
        
        if not original_text:
            logger.warning(f"Original text is empty in overlay layout: overlay_id={body.overlay_id}")
        
        # Step 2: 이미지 로드
        try:
            image = Image.open(abs_from_url(render_asset_url)).convert("RGB")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        # Step 3: 텍스트 영역 좌표 계산 (정규화된 좌표를 픽셀 좌표로 변환)
        img_w, img_h = image.size
        text_region = None
        if overlay.x_ratio is not None and overlay.y_ratio is not None and overlay.width_ratio is not None and overlay.height_ratio is not None:
            x_px = int(overlay.x_ratio * img_w)
            y_px = int(overlay.y_ratio * img_h)
            width_px = int(overlay.width_ratio * img_w)
            height_px = int(overlay.height_ratio * img_h)
            text_region = (x_px, y_px, width_px, height_px)
            logger.info(f"텍스트 영역: ({x_px}, {y_px}, {width_px}, {height_px})")
        
        # Step 4: OCR 실행
        start_time = time.time()
        try:
            ocr_result = extract_text_from_image(image, text_region)
            recognized_text = ocr_result.get("recognized_text", "")
            ocr_confidence = ocr_result.get("confidence", 0.0)
        except Exception as e:
            logger.error(f"OCR 실행 실패: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"OCR 실행 중 오류가 발생했습니다: {str(e)}")
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Step 5: OCR 정확도 계산
        accuracy_result = calculate_ocr_accuracy(original_text, recognized_text)
        ocr_accuracy = accuracy_result.get("accuracy", 0.0)
        character_match_rate = accuracy_result.get("character_match_rate", 0.0)
        
        # Step 6: evaluations 테이블에 저장
        evaluation_id = uuid.uuid4()
        metrics = {
            "ocr_confidence": ocr_confidence,
            "ocr_accuracy": ocr_accuracy,
            "character_match_rate": character_match_rate,
            "word_match_rate": accuracy_result.get("word_match_rate", 0.0),
            "recognized_text": recognized_text,
            "original_text": original_text,
            "edit_distance": accuracy_result.get("edit_distance", 0),
            "similarity": accuracy_result.get("similarity", 0.0),
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
                    "evaluation_type": "ocr",
                    "metrics": json.dumps(metrics)
                }
            )
            db.commit()
            logger.info(f"OCR 평가 결과 저장 완료: evaluation_id={evaluation_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"OCR 평가 결과 저장 실패: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"OCR 평가 결과 저장 중 오류가 발생했습니다: {str(e)}"
            )
        
        # Step 7: Job variant 상태를 'done'으로 업데이트
        try:
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done', 
                        current_step = 'ocr_eval',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='done'")
        except Exception as e:
            logger.error(f"Job variant 상태 업데이트 실패: {e}")
            db.rollback()
            # 상태 업데이트 실패해도 결과는 반환
            logger.warning(f"Job variant 상태 업데이트 실패했지만 결과는 반환합니다: {e}")
        
        # Step 8: 응답 반환
        return OCREvalOut(
            job_id=body.job_id,
            evaluation_id=str(evaluation_id),
            overlay_id=body.overlay_id,
            ocr_confidence=ocr_confidence,
            ocr_accuracy=ocr_accuracy,
            character_match_rate=character_match_rate,
            recognized_text=recognized_text,
            original_text=original_text
        )
        
    except HTTPException:
        # HTTPException 발생 시 job_variants 상태를 failed로 업데이트
        try:
            if 'job_variants_id' in locals():
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (오류 발생)")
        except Exception as e:
            logger.error(f"Job variant 상태 업데이트 실패 (오류 처리 중): {e}")
            db.rollback()
        raise
    except Exception as e:
        # 기타 예외 발생 시 job_variants 상태를 failed로 업데이트
        try:
            if 'job_variants_id' in locals():
                db.execute(
                    text("""
                        UPDATE jobs_variants 
                        SET status = 'failed', 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_variants_id = :job_variants_id
                    """),
                    {"job_variants_id": job_variants_id}
                )
                db.commit()
                logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='failed' (예외 발생)")
        except Exception as update_error:
            logger.error(f"Job variant 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"OCR 평가 API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


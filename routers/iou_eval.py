
"""IoU 평가 라우터"""
########################################################
# IoU 평가 API
# - 음식 바운딩 박스와 텍스트 영역 겹침 확인
# - evaluations 테이블에 결과 저장
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-28
# author: LEEYH205
# description: IoU evaluation API
# version: 1.1.0
# status: production
# tags: iou, evaluation
# dependencies: fastapi, pydantic, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
import time
from models import IoUEvalIn, IoUEvalOut
from services.iou_eval_service import calculate_iou_with_food
from database import get_db, Job, OverlayLayout, Detection, ImageAsset, JobVariant
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/iou", tags=["iou-eval"])


@router.post("/evaluate", response_model=IoUEvalOut)
def evaluate_iou(body: IoUEvalIn, db: Session = Depends(get_db)):
    """
    IoU 평가: 음식 바운딩 박스와 텍스트 영역 겹침 확인
    
    Args:
        body: IoUEvalIn 모델
            - job_id: 기존 job의 ID - 필수
            - tenant_id: 테넌트 ID - 필수
            - overlay_id: Overlay ID - 필수 (overlay_layouts에서 텍스트 영역 좌표 조회)
    
    Returns:
        IoUEvalOut:
            - job_id: str
            - evaluation_id: str
            - overlay_id: str
            - iou_with_food: float
            - max_iou_detection_id: Optional[str]
            - overlap_detected: bool
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
        
        # Step 0.5: IoU 평가 시작 - job_variants 상태 업데이트 (current_step='iou_eval', status='running')
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'iou_eval',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=iou_eval")
        
        # Step 1: overlay_id 검증 및 텍스트 영역 좌표 조회
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
        
        # 텍스트 영역 좌표 (정규화된 좌표)
        if overlay.x_ratio is None or overlay.y_ratio is None or overlay.width_ratio is None or overlay.height_ratio is None:
            logger.error(f"Text region coordinates not found in overlay layout: overlay_id={body.overlay_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Text region coordinates not found in overlay layout"
            )
        
        text_region = (
            overlay.x_ratio,
            overlay.y_ratio,
            overlay.width_ratio,
            overlay.height_ratio
        )
        
        # Step 2: 음식 바운딩 박스 조회 (detections 테이블)
        # 같은 job_id의 detections 조회
        detections = db.query(Detection).filter(Detection.job_id == job_id).all()
        
        if not detections:
            logger.warning(f"No detections found for job_id={body.job_id}, returning zero IoU")
            # IoU가 0인 결과 반환
            evaluation_id = uuid.uuid4()
            metrics = {
                "iou_with_food": 0.0,
                "max_iou_detection_id": None,
                "overlap_detected": False,
                "all_ious": [],
                "detection_count": 0
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
                        "evaluation_type": "iou",
                        "metrics": json.dumps(metrics)
                    }
                )
                db.commit()
            except Exception as e:
                logger.error(f"IoU 평가 결과 저장 실패: {str(e)}", exc_info=True)
                db.rollback()
            
            return IoUEvalOut(
                job_id=body.job_id,
                evaluation_id=str(evaluation_id),
                overlay_id=body.overlay_id,
                iou_with_food=0.0,
                max_iou_detection_id=None,
                overlap_detected=False
            )
        
        # Step 3: 이미지 크기 조회 (image_assets 테이블)
        # 첫 번째 detection의 image_asset_id 사용
        first_detection = detections[0]
        image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == first_detection.image_asset_id).first()
        
        if not image_asset or not image_asset.width or not image_asset.height:
            logger.error(f"Image asset not found or size not available: image_asset_id={first_detection.image_asset_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Image asset not found or size not available"
            )
        
        image_width = image_asset.width
        image_height = image_asset.height
        
        # Step 4: 음식 바운딩 박스 리스트 구성
        food_boxes = []
        detection_ids = []
        
        for detection in detections:
            if detection.box and isinstance(detection.box, list) and len(detection.box) == 4:
                # box 형식: [x1, y1, x2, y2] (xyxy, 픽셀 좌표)
                food_boxes.append(detection.box)
                detection_ids.append(str(detection.detection_id))
        
        if not food_boxes:
            logger.warning(f"No valid food boxes found in detections for job_id={body.job_id}")
            # IoU가 0인 결과 반환
            evaluation_id = uuid.uuid4()
            metrics = {
                "iou_with_food": 0.0,
                "max_iou_detection_id": None,
                "overlap_detected": False,
                "all_ious": [],
                "detection_count": len(detections)
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
                        "evaluation_type": "iou",
                        "metrics": json.dumps(metrics)
                    }
                )
                db.commit()
            except Exception as e:
                logger.error(f"IoU 평가 결과 저장 실패: {str(e)}", exc_info=True)
                db.rollback()
            
            return IoUEvalOut(
                job_id=body.job_id,
                evaluation_id=str(evaluation_id),
                overlay_id=body.overlay_id,
                iou_with_food=0.0,
                max_iou_detection_id=None,
                overlap_detected=False
            )
        
        # Step 5: IoU 계산 실행
        start_time = time.time()
        try:
            iou_result = calculate_iou_with_food(
                text_region=text_region,
                food_boxes=food_boxes,
                image_width=image_width,
                image_height=image_height,
                boxes_are_normalized=False  # food_boxes는 픽셀 좌표
            )
        except Exception as e:
            logger.error(f"IoU 계산 실패: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"IoU 계산 중 오류가 발생했습니다: {str(e)}")
        
        latency_ms = (time.time() - start_time) * 1000
        
        # 최대 IoU를 가진 detection_id 찾기
        max_iou_detection_id = None
        max_iou_index = iou_result.get("max_iou_detection_id")
        if max_iou_index and int(max_iou_index) >= 0 and int(max_iou_index) < len(detection_ids):
            max_iou_detection_id = detection_ids[int(max_iou_index)]
        
        # Step 6: evaluations 테이블에 저장
        evaluation_id = uuid.uuid4()
        metrics = {
            "iou_with_food": iou_result.get("iou_with_food", 0.0),
            "max_iou_detection_id": max_iou_detection_id,
            "overlap_detected": iou_result.get("overlap_detected", False),
            "all_ious": iou_result.get("all_ious", []),
            "detection_count": len(detections),
            "text_region": list(text_region),
            "image_width": image_width,
            "image_height": image_height,
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
                    "evaluation_type": "iou",
                    "metrics": json.dumps(metrics)
                }
            )
            db.commit()
            logger.info(f"IoU 평가 결과 저장 완료: evaluation_id={evaluation_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"IoU 평가 결과 저장 실패: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"IoU 평가 결과 저장 중 오류가 발생했습니다: {str(e)}"
            )
        
        # Step 7: Job 상태를 'done'으로 업데이트
        try:
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done', 
                        current_step = 'iou_eval',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_variants_id = :job_variants_id
                """),
                {"job_variants_id": job_variants_id}
            )
            db.commit()
            logger.info(f"Job variant 상태 업데이트: job_variants_id={job_variants_id}, status='done'")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패: {e}")
            db.rollback()
            # 상태 업데이트 실패해도 결과는 반환
            logger.warning(f"Job 상태 업데이트 실패했지만 결과는 반환합니다: {e}")
        
        # Step 8: 응답 반환
        return IoUEvalOut(
            job_id=body.job_id,
            evaluation_id=str(evaluation_id),
            overlay_id=body.overlay_id,
            iou_with_food=iou_result.get("iou_with_food", 0.0),
            max_iou_detection_id=max_iou_detection_id,
            overlap_detected=iou_result.get("overlap_detected", False)
        )
        
    except HTTPException:
        # HTTPException 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
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
            logger.error(f"Job 상태 업데이트 실패 (오류 처리 중): {e}")
            db.rollback()
        raise
    except Exception as e:
        # 기타 예외 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
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
            logger.error(f"Job 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"IoU 평가 API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


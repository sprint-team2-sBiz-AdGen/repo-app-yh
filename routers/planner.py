
"""Planner 라우터"""
########################################################
# 텍스트 오버레이 위치 제안 API
# 
# 기능:
# - 금지 영역을 피한 최적의 위치 제안
# - 여러 위치 옵션 생성 (상단, 하단, 좌측, 우측)
# - YOLO 감지 결과 활용
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-21
# author: LEEYH205
# description: Planner logic
# version: 0.2.0
# status: development
# tags: planner
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from models import PlannerIn, PlannerOut, ProposalOut
from utils import abs_from_url
from services.planner_service import propose_overlay_positions
from database import get_db, Job, JobInput, ImageAsset, Detection, YOLORun
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/planner", tags=["planner"])


@router.post("", response_model=PlannerOut, summary="텍스트 오버레이 위치 제안")
def planner(body: PlannerIn, db: Session = Depends(get_db)):
    """
    이미지에 텍스트 오버레이를 배치할 최적의 위치를 제안합니다.
    
    ## 기능
    - 금지 영역(사람, 음식 등)을 피한 최적 위치 제안
    - 최대 10개의 다양한 위치 옵션 제공
    - 최대 크기 제안 포함 (금지 영역과 겹치지 않는 최대 영역)
    - DB에서 YOLO 감지 결과 자동 조회 (job_id 제공 시)
    
    ## 요청 파라미터
    - `job_id`: 기존 job의 ID (DB에서 detections를 가져올 job) - 필수
    - `tenant_id`: 테넌트 ID - 필수
    - `asset_url`: 이미지 URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
    - `detections`: YOLO 감지 결과 (Optional, DB에서 가져올 수 있으면 생략 가능, 하위 호환성 유지)
    - `min_overlay_width`: 최소 오버레이 너비 비율 (기본값: 0.5)
    - `min_overlay_height`: 최소 오버레이 높이 비율 (기본값: 0.12)
    - `max_proposals`: 최대 제안 개수 (기본값: 10)
    - `max_forbidden_iou`: 최대 허용 금지 영역 IoU (기본값: 0.05)
    
    ## 응답
    - `proposals`: 제안 리스트
      - `proposal_id`: 제안 고유 ID
      - `xywh`: [x, y, width, height] 정규화된 좌표 (0-1)
      - `source`: 제안 출처 (rule_top, grid_*, max_size_* 등)
      - `color`: 텍스트 색상 (hex)
      - `size`: 텍스트 크기
      - `score`: 제안 점수 (높을수록 우선순위 높음)
      - `occlusion_iou`: 금지 영역과의 IoU (0에 가까울수록 좋음)
    - `avoid`: 금지 영역 [x, y, width, height] (정규화된 좌표)
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
        
        # Step 1: job_inputs에서 이미지 정보 가져오기
        asset_url = body.asset_url
        if not asset_url:
            job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
            if not job_input:
                logger.error(f"Job input not found: job_id={job_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Job input not found for job_id: {job_id}"
                )
            
            image_asset_id = job_input.img_asset_id
            if not image_asset_id:
                logger.error(f"Image asset ID not found in job_input: job_id={job_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset ID not found in job input"
                )
            
            image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == image_asset_id).first()
            if not image_asset:
                logger.error(f"Image asset not found: image_asset_id={image_asset_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset not found: {image_asset_id}"
                )
            
            asset_url = image_asset.image_url
            logger.info(f"Found image asset from job_input: {image_asset_id}, URL: {asset_url}")
        
        # Step 2: 이미지 로드
        try:
            im = Image.open(abs_from_url(asset_url))
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        # Step 3: DB에서 YOLO 감지 결과 가져오기 (body.detections가 없으면)
        detections = body.detections
        forbidden_mask = None
        
        if not detections:
            # yolo_runs에서 메타데이터 가져오기
            yolo_run = db.query(YOLORun).filter(YOLORun.job_id == job_id).first()
            
            if yolo_run:
                # detections 테이블에서 감지 결과 가져오기
                detection_records = db.query(Detection).filter(
                    Detection.job_id == job_id
                ).order_by(Detection.created_at).all()
                
                if detection_records:
                    boxes = []
                    labels = []
                    confidences = []
                    
                    for det in detection_records:
                        # box는 JSONB로 저장된 [x1, y1, x2, y2] 형식
                        box = det.box if isinstance(det.box, list) else det.box
                        boxes.append(box)
                        labels.append(det.label)
                        confidences.append(float(det.score))
                    
                    detections = {
                        "boxes": boxes,
                        "labels": labels,
                        "confidences": confidences,
                        "forbidden_mask_url": yolo_run.forbidden_mask_url
                    }
                    
                    logger.info(f"Loaded {len(detection_records)} detections from DB for job_id={job_id}")
                else:
                    logger.warning(f"No detections found for job_id={job_id}")
                    detections = None
            else:
                logger.warning(f"No yolo_run found for job_id={job_id}")
                detections = None
        
        # 금지 영역 마스크 추출 (detections에 forbidden_mask_url이 있는 경우)
        if detections and detections.get("forbidden_mask_url"):
            try:
                mask_url = detections["forbidden_mask_url"]
                forbidden_mask = Image.open(abs_from_url(mask_url))
                logger.info(f"금지 영역 마스크 로드: {mask_url}")
            except Exception as e:
                logger.warning(f"금지 영역 마스크 로드 실패: {e}")
                # 마스크 로드 실패해도 계속 진행 (boxes만 사용)
        
        # Step 4: 위치 제안 생성
        try:
            result = propose_overlay_positions(
                image=im,
                detections=detections,
                forbidden_mask=forbidden_mask,
                min_overlay_width=body.min_overlay_width,
                min_overlay_height=body.min_overlay_height,
                max_proposals=body.max_proposals,
                max_forbidden_iou=body.max_forbidden_iou
            )
        except Exception as e:
            logger.error(f"위치 제안 생성 실패: {e}")
            raise HTTPException(status_code=500, detail=f"위치 제안 생성 중 오류가 발생했습니다: {str(e)}")
        
        # Step 5: 응답 모델로 변환
        proposals = [
            ProposalOut(**prop) for prop in result.get("proposals", [])
        ]
        
        return PlannerOut(
            proposals=proposals,
            avoid=result.get("avoid")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Planner API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


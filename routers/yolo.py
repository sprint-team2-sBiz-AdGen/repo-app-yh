
"""YOLO 감지 라우터"""
########################################################
# YOLO Detection API with DB Integration
# - 금지 영역 감지
# - DB에 결과 저장 (vlm_traces)
# - job 상태 업데이트
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-24
# author: LEEYH205
# description: YOLO detection logic with DB integration
# version: 1.0.0
# status: production
# tags: yolo, detection
# dependencies: fastapi, pydantic, PIL, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import json
import os
import uuid
import time
from fastapi import APIRouter, HTTPException, Depends
from PIL import Image
from sqlalchemy.orm import Session
from sqlalchemy import text
from models import DetectIn, DetectOut
from utils import abs_from_url, save_asset
from services.yolo_service import detect_forbidden_areas
from database import get_db, Job, JobInput, ImageAsset, Detection, YOLORun
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/yolo", tags=["yolo"])


@router.post("/detect", response_model=DetectOut)
def detect(body: DetectIn, db: Session = Depends(get_db)):
    """
    YOLO 금지 영역 감지 (DB 연동)
    
    이미지에서 금지 영역을 감지하고 결과를 DB에 저장합니다.
    
    Args:
        body: DetectIn 모델
            - job_id: 기존 job의 ID (업데이트할 job)
            - tenant_id: 테넌트 ID
            - asset_url: 이미지 URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
            - model: 모델 이름 (Optional, 기본값: "forbidden")
        
    Returns:
        DetectOut:
            - job_id: str                  # 업데이트된 job 레코드 ID
            - detection_ids: List[str]     # 생성된 detection 레코드 ID 리스트
            - boxes: List[List[float]]     # 감지된 박스 리스트 (xyxy 형식)
            - model: str                   # 사용된 모델 이름
            - confidences: List[float]     # 신뢰도 리스트
            - classes: List[int]           # 클래스 ID 리스트
            - labels: List[str]            # 라벨 리스트
            - areas: List[float]           # 영역 면적 리스트
            - widths: List[float]          # 너비 리스트
            - heights: List[float]         # 높이 리스트
            - forbidden_mask_url: Optional[str]  # 금지 영역 마스크 URL
            - detections: List[dict]       # JSON 형식 감지 결과
    
    Raises:
        HTTPException 404: job 또는 image_asset을 찾을 수 없는 경우
        HTTPException 400: 이미지 파일을 찾을 수 없거나 로드할 수 없는 경우
        HTTPException 500: YOLO 모델 로드, 감지, 또는 DB 저장 중 오류 발생
    """
    try:
        # Step 0: 기존 job 조회 및 업데이트
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
        
        # job의 tenant_id 확인
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # job 상태 업데이트: current_step='yolo_detect', status='running'
        db.execute(
            text("""
                UPDATE jobs 
                SET status = 'running', 
                    current_step = 'yolo_detect',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        db.flush()
        logger.info(f"Updated job: {job_id} - status=running, current_step=yolo_detect")
        
        # Step 1: job_inputs에서 이미지 정보 가져오기
        asset_url = body.asset_url
        image_asset_id = None
        
        if not asset_url:
            job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
            if not job_input:
                logger.error(f"Job input not found: job_id={job_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Job input not found for job_id: {job_id}"
                )
            
            # job_inputs에서 image_asset_id 가져오기
            image_asset_id = job_input.img_asset_id
            if not image_asset_id:
                logger.error(f"Image asset ID not found in job_input: job_id={job_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset ID not found in job input"
                )
            
            # image_assets에서 이미지 정보 가져오기
            image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == image_asset_id).first()
            if not image_asset:
                logger.error(f"Image asset not found: image_asset_id={image_asset_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset not found: {image_asset_id}"
                )
            
            asset_url = image_asset.image_url
            logger.info(f"Found image asset from job_input: {image_asset_id}, URL: {asset_url}")
        else:
            # asset_url이 제공된 경우, image_asset_id를 조회
            image_asset = db.query(ImageAsset).filter(ImageAsset.image_url == asset_url).first()
            if image_asset:
                image_asset_id = image_asset.image_asset_id
                logger.info(f"Found image asset from URL: {image_asset_id}, URL: {asset_url}")
            else:
                logger.warning(f"Image asset not found for URL: {asset_url}, will skip image_asset_id in detections")
        
        # Step 2: 이미지 로드
        try:
            image_path = abs_from_url(asset_url)
            image = Image.open(image_path)
            logger.info(f"Image loaded successfully: {image_path}, size: {image.size}")
        except FileNotFoundError:
            logger.error(f"Image file not found: {asset_url}")
            raise HTTPException(
                status_code=400,
                detail=f"Image file not found: {asset_url}"
            )
        except Exception as e:
            logger.error(f"Failed to load image: {asset_url}, error: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load image: {str(e)}"
            )
        
        # Step 3: YOLO 모델로 금지 영역 감지
        start_time = time.time()
        try:
            result = detect_forbidden_areas(
                image=image,
                model_name=None,  # config에서 가져옴
                conf_threshold=None,  # config에서 가져옴
                iou_threshold=None,  # config에서 가져옴
                target_classes=None,  # 모든 클래스 감지 후 라벨로 필터링
                forbidden_labels=None  # config에서 가져옴 (없으면 기본 리스트 사용)
            )
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"YOLO detection completed: latency={latency_ms:.2f}ms, detections={len(result.get('boxes', []))}")
        except Exception as e:
            logger.error(f"YOLO detection failed: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"YOLO detection failed: {str(e)}"
            )
        
        # Step 4: 금지 영역 마스크 저장
        forbidden_mask = result.get("forbidden_mask")
        forbidden_mask_url = None
        if forbidden_mask:
            mask_meta = save_asset(body.tenant_id, "forbidden_mask", forbidden_mask, ".png")
            forbidden_mask_url = mask_meta["url"]
            
            # detections.json 저장 (마스크와 같은 디렉토리에)
            detections_json = result.get("detections_json", [])
            if detections_json:
                # 마스크 파일의 디렉토리 경로 추출
                mask_dir = os.path.dirname(abs_from_url(forbidden_mask_url))
                detections_json_path = os.path.join(mask_dir, "detections.json")
                os.makedirs(mask_dir, exist_ok=True)
                
                # JSON 파일 저장
                with open(detections_json_path, "w", encoding="utf-8") as f:
                    json.dump(detections_json, f, indent=2, ensure_ascii=False)
        
        # Step 5: detections 테이블에 각 감지 결과 저장
        detection_ids = []
        boxes = result.get("boxes", [])
        labels = result.get("labels", [])
        confidences = result.get("confidences", [])
        classes = result.get("classes", [])
        
        if image_asset_id:  # image_asset_id가 있는 경우에만 저장
            for i, box in enumerate(boxes):
                detection_id = uuid.uuid4()
                detection_uid = uuid.uuid4().hex
                
                # box를 JSONB 형식으로 저장 [x1, y1, x2, y2]
                box_json = json.dumps(box)
                
                label = labels[i] if i < len(labels) else f"class_{classes[i] if i < len(classes) else 'unknown'}"
                score = confidences[i] if i < len(confidences) else 0.0
                
                # detections 테이블에 저장
                db.execute(
                    text("""
                        INSERT INTO detections (
                            detection_id, job_id, image_asset_id, model_id, box, 
                            label, score, uid, created_at, updated_at
                        )
                        VALUES (
                            :detection_id, :job_id, :image_asset_id, :model_id, CAST(:box AS jsonb),
                            :label, :score, :uid, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "detection_id": detection_id,
                        "job_id": job_id,
                        "image_asset_id": image_asset_id,
                        "model_id": None,  # gen_models 테이블에 YOLO 모델이 등록되어 있으면 해당 ID 사용
                        "box": box_json,
                        "label": label,
                        "score": float(score),
                        "uid": detection_uid
                    }
                )
                detection_ids.append(detection_id)
            
            db.flush()
            logger.info(f"Saved {len(detection_ids)} detections to DB for job_id={job_id}, image_asset_id={image_asset_id}")
        else:
            logger.warning(f"image_asset_id not found, skipping detections table insert for job_id={job_id}")
        
        # Step 5-2: yolo_runs 테이블에 메타데이터 저장
        if image_asset_id:
            yolo_run_id = uuid.uuid4()
            db.execute(
                text("""
                    INSERT INTO yolo_runs (
                        yolo_run_id, job_id, image_asset_id, forbidden_mask_url,
                        model_name, detection_count, latency_ms, created_at, updated_at
                    )
                    VALUES (
                        :yolo_run_id, :job_id, :image_asset_id, :forbidden_mask_url,
                        :model_name, :detection_count, :latency_ms, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (job_id) DO UPDATE SET
                        forbidden_mask_url = EXCLUDED.forbidden_mask_url,
                        model_name = EXCLUDED.model_name,
                        detection_count = EXCLUDED.detection_count,
                        latency_ms = EXCLUDED.latency_ms,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {
                    "yolo_run_id": yolo_run_id,
                    "job_id": job_id,
                    "image_asset_id": image_asset_id,
                    "forbidden_mask_url": forbidden_mask_url,
                    "model_name": body.model,
                    "detection_count": len(detection_ids),
                    "latency_ms": latency_ms
                }
            )
            db.flush()
            logger.info(f"Saved yolo_run to DB: yolo_run_id={yolo_run_id}, job_id={job_id}, latency_ms={latency_ms:.2f}")
        
        # Step 6: jobs 상태를 'done'으로 업데이트
        db.execute(
            text("""
                UPDATE jobs SET status = 'done', updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        
        # Step 7: 커밋
        try:
            db.commit()
            logger.info(f"Saved to DB: job_id={job_id}, detection_ids={len(detection_ids)}")
        except Exception as e:
            logger.error(f"Failed to commit to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save detection result to database: {str(e)}"
            )
        
        # Step 8: 응답 반환
        return DetectOut(
            job_id=body.job_id,  # 요청에서 받은 job_id 그대로 반환
            detection_ids=[str(did) for did in detection_ids],  # 여러 detection_id 반환
            boxes=result.get("boxes", []),
            model=body.model,
            confidences=result.get("confidences", []),
            classes=result.get("classes", []),
            labels=result.get("labels", []),
            areas=result.get("areas", []),
            widths=result.get("widths", []),
            heights=result.get("heights", []),
            forbidden_mask_url=forbidden_mask_url,
            detections=result.get("detections_json", [])
        )
    
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        # 예상치 못한 오류
        logger.error(f"Unexpected error in detect: {str(e)}", exc_info=True)
        if db:
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


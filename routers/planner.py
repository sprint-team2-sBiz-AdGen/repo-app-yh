
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
# updated_at: 2025-12-03
# author: LEEYH205
# description: Planner logic
# version: 2.2.1
# status: development
# tags: planner
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from models import PlannerIn, PlannerOut, ProposalOut
from utils import abs_from_url, save_asset
from services.planner_service import propose_overlay_positions
from database import get_db, Job, JobInput, ImageAsset, Detection, YOLORun, PlannerProposal, JobVariant
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
        
        # Step 0.5: job_variant 상태 확인 (current_step='yolo_detect', status='done'이어야 함)
        if job_variant.current_step != 'yolo_detect' or job_variant.status != 'done':
            logger.error(f"Job variant 상태가 planner 실행 조건을 만족하지 않음: current_step={job_variant.current_step}, status={job_variant.status}")
            raise HTTPException(
                status_code=400,
                detail=f"Job variant 상태가 planner 실행 조건을 만족하지 않습니다. current_step='yolo_detect', status='done'이어야 합니다. (현재: current_step='{job_variant.current_step}', status='{job_variant.status}')"
            )
        
        # Step 0.6: Planner 시작 - job_variants 상태 업데이트 (current_step='planner', status='running')
        db.execute(
            text("""
                UPDATE jobs_variants 
                SET status = 'running', 
                    current_step = 'planner',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_variants_id = :job_variants_id
            """),
            {"job_variants_id": job_variants_id}
        )
        db.flush()
        logger.info(f"Updated job_variant: {job_variants_id} - status=running, current_step=planner")
        
        # Step 1: jobs_variants에서 이미지 정보 가져오기
        asset_url = body.asset_url
        if not asset_url:
            image_asset_id = job_variant.img_asset_id
            if not image_asset_id:
                logger.error(f"Image asset ID not found in job_variant: job_variants_id={job_variants_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset ID not found in job variant"
                )
            
            image_asset = db.query(ImageAsset).filter(ImageAsset.image_asset_id == image_asset_id).first()
            if not image_asset:
                logger.error(f"Image asset not found: image_asset_id={image_asset_id}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Image asset not found: {image_asset_id}"
                )
            
            asset_url = image_asset.image_url
            logger.info(f"Found image asset from job_variant: {image_asset_id}, URL: {asset_url}")
        
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
            # yolo_runs에서 메타데이터 가져오기 (image_asset_id로 필터링)
            yolo_run = db.query(YOLORun).filter(
                YOLORun.job_id == job_id,
                YOLORun.image_asset_id == image_asset_id
            ).first()
            
            if yolo_run:
                # detections 테이블에서 감지 결과 가져오기 (image_asset_id로 필터링)
                detection_records = db.query(Detection).filter(
                    Detection.job_id == job_id,
                    Detection.image_asset_id == image_asset_id
                ).order_by(Detection.created_at).all()
                
                logger.info(f"Loading detections for job_id={job_id}, image_asset_id={image_asset_id}, found {len(detection_records)} records")
                
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
        import time
        start_time = time.time()
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
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"Planner 위치 제안 생성 완료: latency={latency_ms:.2f}ms, proposals={len(result.get('proposals', []))}")
        except Exception as e:
            logger.error(f"위치 제안 생성 실패: {e}")
            raise HTTPException(status_code=500, detail=f"위치 제안 생성 중 오류가 발생했습니다: {str(e)}")
        
        # Step 5: 응답 모델로 변환
        proposals = [
            ProposalOut(**prop) for prop in result.get("proposals", [])
        ]
        
        # Step 5.5: Proposal box를 그린 이미지 생성 및 저장
        proposal_image_asset_id = None
        proposal_image_url = None
        try:
            # 원본 이미지에 proposal box 그리기
            if im and proposals:
                # 이미지를 RGBA로 변환 (투명도 지원)
                proposal_image = im.convert("RGBA")
                draw = ImageDraw.Draw(proposal_image)
                w, h = proposal_image.size
                
                # 폰트 로드 시도
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                except:
                    try:
                        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
                    except:
                        font = ImageFont.load_default()
                
                # 금지 영역 그리기 (빨간색)
                # detections에서 모든 금지 영역 박스 가져오기
                avoid_regions = []
                if detections and detections.get("boxes"):
                    logger.info(f"[Planner Image] YOLO 감지 박스 개수: {len(detections['boxes'])}")
                    for box in detections["boxes"]:
                        x1, y1, x2, y2 = box
                        # 정규화된 xywh로 변환
                        ax = max(0.0, min(1.0, x1 / w))
                        ay = max(0.0, min(1.0, y1 / h))
                        aw = min(1.0, (x2 - x1) / w)
                        ah = min(1.0, (y2 - y1) / h)
                        avoid_regions.append([ax, ay, aw, ah])
                        logger.debug(f"[Planner Image] 금지 영역 추가: [{ax:.3f}, {ay:.3f}, {aw:.3f}, {ah:.3f}]")
                else:
                    # detections가 없으면 DB에서 직접 가져오기 (image_asset_id로 필터링)
                    try:
                        detection_records = db.query(Detection).filter(
                            Detection.job_id == job_id,
                            Detection.image_asset_id == image_asset_id
                        ).all()
                        if detection_records:
                            logger.info(f"[Planner Image] DB에서 {len(detection_records)}개의 감지 결과 로드")
                            for det in detection_records:
                                box = det.box if isinstance(det.box, list) else det.box
                                if box and len(box) == 4:
                                    x1, y1, x2, y2 = box
                                    # 정규화된 xywh로 변환
                                    ax = max(0.0, min(1.0, x1 / w))
                                    ay = max(0.0, min(1.0, y1 / h))
                                    aw = min(1.0, (x2 - x1) / w)
                                    ah = min(1.0, (y2 - y1) / h)
                                    avoid_regions.append([ax, ay, aw, ah])
                                    logger.debug(f"[Planner Image] DB에서 금지 영역 추가: [{ax:.3f}, {ay:.3f}, {aw:.3f}, {ah:.3f}]")
                    except Exception as e:
                        logger.warning(f"[Planner Image] DB에서 감지 결과 로드 실패: {e}")
                
                # 모든 금지 영역 그리기 (각각 개별적으로)
                if avoid_regions:
                    logger.info(f"[Planner Image] {len(avoid_regions)}개의 금지 영역을 개별적으로 그림")
                    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    
                    for i, (ax, ay, aw, ah) in enumerate(avoid_regions):
                        ax_px = int(ax * w)
                        ay_px = int(ay * h)
                        aw_px = int(aw * w)
                        ah_px = int(ah * h)
                        
                        # 각 금지 영역을 개별적으로 그리기
                        overlay_draw.rectangle(
                            [ax_px, ay_px, ax_px + aw_px, ay_px + ah_px],
                            fill=(255, 0, 0, 50),
                            outline="red",
                            width=3
                        )
                        # 라벨 추가
                        overlay_draw.text((ax_px + 5, ay_px + 5), f"AVOID {i+1}", fill="red", font=font)
                    
                    proposal_image = Image.alpha_composite(proposal_image, overlay)
                    draw = ImageDraw.Draw(proposal_image)
                # fallback: avoid 값이 있으면 사용 (이전 방식 - 모든 금지 영역을 포함하는 바운딩 박스)
                elif result.get("avoid"):
                    logger.info(f"[Planner Image] detections가 없어서 result.avoid 사용 (바운딩 박스)")
                    avoid = result.get("avoid")
                    if isinstance(avoid, list) and len(avoid) == 4:
                        ax, ay, aw, ah = avoid
                        ax_px = int(ax * w)
                        ay_px = int(ay * h)
                        aw_px = int(aw * w)
                        ah_px = int(ah * h)
                        # 반투명 빨간색 배경
                        overlay = Image.new("RGBA", (w, h), (255, 0, 0, 50))
                        overlay_draw = ImageDraw.Draw(overlay)
                        overlay_draw.rectangle(
                            [ax_px, ay_px, ax_px + aw_px, ay_px + ah_px],
                            fill=(255, 0, 0, 50),
                            outline="red",
                            width=3
                        )
                        proposal_image = Image.alpha_composite(proposal_image, overlay)
                        draw = ImageDraw.Draw(proposal_image)
                        # 라벨 추가
                        draw.text((ax_px + 5, ay_px + 5), "AVOID", fill="red", font=font)
                
                # Proposal box 그리기 (다양한 색상)
                colors = [
                    (0, 255, 0, 200),    # 초록
                    (0, 0, 255, 200),    # 파랑
                    (255, 255, 0, 200),  # 노랑
                    (255, 0, 255, 200),  # 마젠타
                    (0, 255, 255, 200),  # 시안
                    (255, 165, 0, 200),  # 주황
                ]
                
                for i, proposal in enumerate(proposals):
                    prop_dict = proposal.dict() if hasattr(proposal, 'dict') else proposal
                    xywh = prop_dict.get("xywh", [])
                    if len(xywh) != 4:
                        continue
                    
                    x, y, width, height = xywh
                    x_px = int(x * w)
                    y_px = int(y * h)
                    width_px = int(width * w)
                    height_px = int(height * h)
                    
                    color = colors[i % len(colors)]
                    source = prop_dict.get("source", f"proposal_{i+1}")
                    score = prop_dict.get("score", 0)
                    
                    # 반투명 배경 그리기
                    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    overlay_draw.rectangle(
                        [x_px, y_px, x_px + width_px, y_px + height_px],
                        fill=(color[0], color[1], color[2], 50),
                        outline=(color[0], color[1], color[2], 255),
                        width=3
                    )
                    proposal_image = Image.alpha_composite(proposal_image, overlay)
                    draw = ImageDraw.Draw(proposal_image)
                    
                    # 라벨 추가
                    label = f"{source}\nscore:{score:.2f}"
                    try:
                        bbox = draw.textbbox((x_px + 5, y_px + 5), label, font=font)
                        text_bg = [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2]
                        draw.rectangle(text_bg, fill=(color[0], color[1], color[2], 200))
                        draw.text((x_px + 5, y_px + 5), label, fill="white", font=font)
                    except:
                        draw.rectangle([x_px + 5, y_px + 5, x_px + 200, y_px + 40], fill=(color[0], color[1], color[2], 200))
                        draw.text((x_px + 5, y_px + 5), label, fill="white")
                
                # RGB로 변환하여 저장
                proposal_image_rgb = proposal_image.convert("RGB")
                
                # 이미지 저장
                asset_meta = save_asset(body.tenant_id, "planner", proposal_image_rgb, ".png")
                proposal_image_asset_id = uuid.UUID(asset_meta["asset_id"])
                proposal_image_url = asset_meta["url"]
                
                # image_assets 테이블에 저장
                existing_asset = db.query(ImageAsset).filter(
                    ImageAsset.image_asset_id == proposal_image_asset_id
                ).first()
                
                if not existing_asset:
                    db.execute(
                        text("""
                            INSERT INTO image_assets (
                                image_asset_id, image_type, image_url, width, height,
                                tenant_id, job_id, created_at, updated_at
                            ) VALUES (
                                :image_asset_id, 'planner', :image_url, :width, :height,
                                :tenant_id, :job_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                        """),
                        {
                            "image_asset_id": proposal_image_asset_id,
                            "image_url": proposal_image_url,
                            "width": asset_meta["width"],
                            "height": asset_meta["height"],
                            "tenant_id": body.tenant_id,
                            "job_id": str(job_id)
                        }
                    )
                    db.commit()
                    logger.info(f"Proposal box image saved: image_asset_id={proposal_image_asset_id}, url={proposal_image_url}")
                else:
                    logger.info(f"Proposal box image already exists: image_asset_id={proposal_image_asset_id}")
                    
        except Exception as e:
            logger.error(f"Failed to create and save proposal box image: {e}", exc_info=True)
            # 이미지 저장 실패해도 계속 진행
        
        # Step 5.6: planner_proposals 테이블에 결과 저장
        try:
            # job_input에서 image_asset_id 가져오기 (이미 위에서 확인함)
            job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
            image_asset_id = job_input.img_asset_id if job_input else None
            
            if image_asset_id:
                # 전체 결과를 layout JSONB에 저장
                import json
                layout_data = {
                    "proposals": [prop.dict() if hasattr(prop, 'dict') else prop for prop in proposals],
                    "avoid": result.get("avoid"),
                    "forbidden_position": result.get("forbidden_position"),  # Forbidden 영역 위치 정보 추가
                    "min_overlay_width": body.min_overlay_width,
                    "min_overlay_height": body.min_overlay_height,
                    "max_proposals": body.max_proposals,
                    "max_forbidden_iou": body.max_forbidden_iou,
                    "proposal_image_asset_id": str(proposal_image_asset_id) if proposal_image_asset_id else None,
                    "proposal_image_url": proposal_image_url if proposal_image_asset_id else None
                }
                
                # planner_proposals에 저장 (raw SQL 사용, pk는 SERIAL로 자동 생성)
                proposal_id = uuid.uuid4()
                db.execute(
                    text("""
                        INSERT INTO planner_proposals (
                            proposal_id, image_asset_id, layout, latency_ms,
                            created_at, updated_at
                        ) VALUES (
                            :proposal_id, :image_asset_id, CAST(:layout AS jsonb), :latency_ms,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "proposal_id": proposal_id,
                        "image_asset_id": image_asset_id,
                        "layout": json.dumps(layout_data),
                        "latency_ms": latency_ms
                    }
                )
                db.commit()
                logger.info(f"Planner proposal saved to DB: proposal_id={proposal_id}, image_asset_id={image_asset_id}, proposal_image_asset_id={proposal_image_asset_id}, latency_ms={latency_ms:.2f}")
            else:
                logger.warning(f"Could not save planner proposal: image_asset_id not found for job_id={job_id}")
        except Exception as e:
            logger.error(f"Failed to save planner proposal to DB: {e}")
            db.rollback()
            # DB 저장 실패해도 결과는 반환
            logger.warning(f"Planner proposal DB save failed but continuing: {e}")
        
        # Step 6: Planner 완료 - job_variants 상태 업데이트 (status='done')
        try:
            db.execute(
                text("""
                    UPDATE jobs_variants 
                    SET status = 'done', 
                        current_step = 'planner',
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
        
        return PlannerOut(
            proposals=proposals,
            avoid=result.get("avoid")
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
            if job:
                job.status = 'failed'
                db.commit()
                logger.info(f"Job 상태 업데이트: job_id={job_id}, status='failed' (예외 발생)")
        except Exception as update_error:
            logger.error(f"Job 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"Planner API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")



"""Overlay 라우터"""
########################################################
# Overlay API with DB Integration
# - 텍스트 오버레이 적용
# - DB에 결과 저장 (overlay_layouts)
# - job 상태 업데이트
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-24
# author: LEEYH205
# description: Overlay logic with DB integration
# version: 1.0.0
# status: production
# tags: overlay
# dependencies: fastapi, pydantic, PIL, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, HTTPException, Depends
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
import json
from models import OverlayIn, OverlayOut
from utils import abs_from_url, save_asset, parse_hex_rgba
from database import get_db, Job, JobInput, ImageAsset, PlannerProposal, OverlayLayout
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/overlay", tags=["overlay"])


@router.post("", response_model=OverlayOut)
def overlay(body: OverlayIn, db: Session = Depends(get_db)):
    """
    이미지에 텍스트 오버레이 적용 (DB 연동)
    
    Args:
        body: OverlayIn 모델
            - job_id: 기존 job의 ID (업데이트할 job) - 필수
            - tenant_id: 테넌트 ID - 필수
            - variant_asset_url: 이미지 URL (Optional, job_inputs에서 가져올 수 있으면 생략 가능)
            - proposal_id: Planner proposal ID (Optional)
            - text: 오버레이할 텍스트
            - x_align, y_align: 정렬 방식
            - text_size: 텍스트 크기
            - overlay_color, text_color: 색상
            - margin: 마진
        
    Returns:
        OverlayOut:
            - job_id: str                  # 업데이트된 job 레코드 ID
            - overlay_id: Optional[str]    # 생성된 overlay_layout 레코드 ID
            - render: dict                 # 렌더링된 이미지 메타데이터
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
        
        # Step 0.5: job 상태 확인 (current_step='planner', status='done'이어야 함)
        if job.current_step != 'planner' or job.status != 'done':
            logger.error(f"Job 상태가 overlay 실행 조건을 만족하지 않음: current_step={job.current_step}, status={job.status}")
            raise HTTPException(
                status_code=400,
                detail=f"Job 상태가 overlay 실행 조건을 만족하지 않습니다. current_step='planner', status='done'이어야 합니다. (현재: current_step='{job.current_step}', status='{job.status}')"
            )
        
        # Step 0.6: Overlay 시작 - job 상태 업데이트 (current_step='overlay', status='running')
        try:
            job.current_step = 'overlay'
            job.status = 'running'
            db.commit()
            logger.info(f"Job 상태 업데이트: job_id={job_id}, current_step='overlay', status='running'")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Job 상태 업데이트 중 오류가 발생했습니다: {str(e)}")
        
        # Step 1: 이미지 URL 가져오기
        variant_asset_url = body.variant_asset_url
        if not variant_asset_url:
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
            
            variant_asset_url = image_asset.image_url
            logger.info(f"Found image asset from job_input: {image_asset_id}, URL: {variant_asset_url}")
        
        # Step 2: 이미지 로드 및 오버레이 적용
        try:
            im = Image.open(abs_from_url(variant_asset_url)).convert("RGBA")
        except Exception as e:
            logger.error(f"이미지 로드 실패: {e}")
            raise HTTPException(status_code=400, detail=f"이미지를 로드할 수 없습니다: {str(e)}")
        
        w, h = im.size
        
        # proposal_id가 있으면 planner_proposals에서 정보 가져오기
        proposal_id_uuid = None
        x_ratio, y_ratio, width_ratio, height_ratio = None, None, None, None
        
        if body.proposal_id:
            try:
                proposal_id_uuid = uuid.UUID(body.proposal_id)
                proposal = db.query(PlannerProposal).filter(PlannerProposal.proposal_id == proposal_id_uuid).first()
                if proposal and proposal.layout:
                    # proposal의 layout에서 첫 번째 proposal 사용
                    layout = proposal.layout
                    if isinstance(layout, dict) and layout.get("proposals"):
                        first_proposal = layout["proposals"][0] if layout["proposals"] else None
                        if first_proposal and "xywh" in first_proposal:
                            xywh = first_proposal["xywh"]  # [x, y, width, height] 정규화된 좌표
                            x_ratio, y_ratio, width_ratio, height_ratio = xywh
                            x, y, pw, ph = (int(w * x_ratio), int(h * y_ratio), int(w * width_ratio), int(h * height_ratio))
                            logger.info(f"Using proposal layout: x={x}, y={y}, w={pw}, h={ph}")
                        else:
                            # proposal 정보가 없으면 기본값 사용
                            x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                    else:
                        x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
                else:
                    x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
            except ValueError:
                logger.warning(f"Invalid proposal_id format: {body.proposal_id}, using default layout")
                x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
        else:
            # default proposal region
            x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
            x_ratio, y_ratio, width_ratio, height_ratio = 0.1, 0.05, 0.8, 0.18
        
        # overlay rect
        ol_color = parse_hex_rgba(body.overlay_color, (0, 0, 0, 0))
        if ol_color[3] > 0:
            over = Image.new("RGBA", (pw, ph), ol_color)
            im.alpha_composite(over, dest=(x, y))
        
        # draw text
        draw = ImageDraw.Draw(im)
        # font: default Pillow
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", body.text_size)
        except:
            font = ImageFont.load_default()
        tw, th = draw.textsize(body.text, font=font)
        
        # alignment
        if body.x_align == "left":
            tx = x + 10
        elif body.x_align == "right":
            tx = x + pw - tw - 10
        else:
            tx = x + (pw - tw) // 2
        if body.y_align == "top":
            ty = y + 10
        elif body.y_align == "bottom":
            ty = y + ph - th - 10
        else:
            ty = y + (ph - th) // 2
        tc = parse_hex_rgba(body.text_color, (255, 255, 255, 255))
        draw.text((tx, ty), body.text, fill=tc, font=font)
        
        # Step 3: 오버레이된 이미지 저장
        meta = save_asset(body.tenant_id, "final", im, ".png")
        
        # Step 4: overlay_layouts 테이블에 결과 저장
        overlay_id = None
        try:
            overlay_id_uuid = uuid.uuid4()
            overlay_uid = uuid.uuid4().hex
            
            # layout JSONB 데이터 구성
            layout_data = {
                "text": body.text,
                "x_align": body.x_align,
                "y_align": body.y_align,
                "text_size": body.text_size,
                "overlay_color": body.overlay_color,
                "text_color": body.text_color,
                "margin": body.margin,
                "render": meta
            }
            
            # overlay_layouts에 저장 (raw SQL 사용, pk는 SERIAL로 자동 생성)
            db.execute(
                text("""
                    INSERT INTO overlay_layouts (
                        overlay_id, proposal_id, layout, x_ratio, y_ratio,
                        width_ratio, height_ratio, text_margin, uid,
                        created_at, updated_at
                    ) VALUES (
                        :overlay_id, :proposal_id, CAST(:layout AS jsonb), :x_ratio, :y_ratio,
                        :width_ratio, :height_ratio, :text_margin, :uid,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "overlay_id": overlay_id_uuid,
                    "proposal_id": proposal_id_uuid,
                    "layout": json.dumps(layout_data),
                    "x_ratio": x_ratio if x_ratio is not None else 0.1,
                    "y_ratio": y_ratio if y_ratio is not None else 0.05,
                    "width_ratio": width_ratio if width_ratio is not None else 0.8,
                    "height_ratio": height_ratio if height_ratio is not None else 0.18,
                    "text_margin": body.margin,
                    "uid": overlay_uid
                }
            )
            db.commit()
            overlay_id = str(overlay_id_uuid)
            logger.info(f"Overlay layout saved to DB: overlay_id={overlay_id}, proposal_id={body.proposal_id}")
        except Exception as e:
            logger.error(f"Failed to save overlay layout to DB: {e}")
            db.rollback()
            # DB 저장 실패해도 결과는 반환
            logger.warning(f"Overlay layout DB save failed but continuing: {e}")
        
        # Step 5: Overlay 완료 - job 상태 업데이트 (status='done')
        try:
            job.status = 'done'
            db.commit()
            logger.info(f"Job 상태 업데이트: job_id={job_id}, status='done'")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패: {e}")
            db.rollback()
            # 상태 업데이트 실패해도 결과는 반환
            logger.warning(f"Job 상태 업데이트 실패했지만 결과는 반환합니다: {e}")
        
        return OverlayOut(
            job_id=body.job_id,
            overlay_id=overlay_id,
            render=meta
        )
        
    except HTTPException:
        # HTTPException 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = 'failed'
                db.commit()
                logger.info(f"Job 상태 업데이트: job_id={job_id}, status='failed' (오류 발생)")
        except Exception as e:
            logger.error(f"Job 상태 업데이트 실패 (오류 처리 중): {e}")
            db.rollback()
        raise
    except Exception as e:
        # 기타 예외 발생 시 job 상태를 failed로 업데이트
        try:
            job = db.query(Job).filter(Job.job_id == job_id).first()
            if job:
                job.status = 'failed'
                db.commit()
                logger.info(f"Job 상태 업데이트: job_id={job_id}, status='failed' (예외 발생)")
        except Exception as update_error:
            logger.error(f"Job 상태 업데이트 실패 (예외 처리 중): {update_error}")
            db.rollback()
        logger.error(f"Overlay API 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")


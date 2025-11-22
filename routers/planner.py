
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

from fastapi import APIRouter
from PIL import Image
from models import PlannerIn
from utils import abs_from_url
from services.planner_service import propose_overlay_positions
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/planner", tags=["planner"])


@router.post("")
def planner(body: PlannerIn):
    """이미지에 텍스트 오버레이를 배치할 위치 제안"""
    im = Image.open(abs_from_url(body.asset_url))
    
    # 금지 영역 마스크 추출 (detections에 forbidden_mask_url이 있는 경우)
    forbidden_mask = None
    if body.detections and body.detections.get("forbidden_mask_url"):
        try:
            mask_url = body.detections["forbidden_mask_url"]
            forbidden_mask = Image.open(abs_from_url(mask_url))
            logger.info(f"금지 영역 마스크 로드: {mask_url}")
        except Exception as e:
            logger.warning(f"금지 영역 마스크 로드 실패: {e}")
    
    # 위치 제안 생성
    result = propose_overlay_positions(
        image=im,
        detections=body.detections,
        forbidden_mask=forbidden_mask,
        min_overlay_width=0.5,
        min_overlay_height=0.12,
        max_proposals=10
    )
    
    return result


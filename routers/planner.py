
"""Planner 라우터"""
########################################################
# TODO: Implement the actual planner logic
#       - Propose the text overlay position
#       - Return the proposal
#       - Return the proposal ID
#       - Return the proposal position
#       - Return the proposal color
#       - Return the proposal size
#       - Return the proposal source
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Planner logic
# version: 0.1.0
# status: development
# tags: planner
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import uuid
from fastapi import APIRouter
from PIL import Image
from models import PlannerIn
from utils import abs_from_url

router = APIRouter(prefix="/api/yh/planner", tags=["planner"])


@router.post("")
def planner(body: PlannerIn):
    """이미지에 텍스트 오버레이를 배치할 위치 제안"""
    im = Image.open(abs_from_url(body.asset_url))
    w, h = im.size
    # very simple: propose top banner area avoiding center box if provided
    avoid = None
    if body.detections and body.detections.get("boxes"):
        bx = body.detections["boxes"][0]
        avoid = [bx[0] / w, bx[1] / h, (bx[2] - bx[0]) / w, (bx[3] - bx[1]) / h]  # xywh normalized
    # proposal: top area 80% width, 18% height
    proposal = {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [0.1, 0.05, 0.8, 0.18],
        "color": "0d0d0dff",
        "size": 32,
        "source": "rule"
    }
    return {"proposals": [proposal], "avoid": avoid}


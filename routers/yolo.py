
"""YOLO 감지 라우터"""
########################################################
# TODO: Implement the actual YOLO detection logic
#       - Detect the forbidden area
#       - Return the detected boxes (xyxy)
#       - Return the detected model
#       - Return the detected confidence
#       - Return the detected class
#       - Return the detected area
#       - Return the detected width
#       - Return the detected height
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: YOLO detection logic
# version: 0.1.0
# status: development
# tags: yolo
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from PIL import Image
from models import DetectIn
from utils import abs_from_url

router = APIRouter(prefix="/api/yh/yolo", tags=["yolo"])


@router.post("/detect")
def detect(body: DetectIn):
    """YOLO 감지 (stub: 중앙 30% 영역 금지)"""
    im = Image.open(abs_from_url(body.asset_url))
    w, h = im.size
    cx, cy = w * 0.5, h * 0.5
    bw, bh = w * 0.3, h * 0.3
    box = [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]  # xyxy
    return {"boxes": [box], "model": body.model}


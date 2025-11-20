
"""Evaluation 라우터"""
########################################################
# TODO: Implement the actual evaluation logic
#       - OCR confidence
#       - Text ratio
#       - CLIP score
#       - IoU for forbidden area
#       - Gate pass
# 
#       - For forbidden area, use the bounding box from YOLO
#       - For text area, use the bounding box from Planner
#       - For overlay area, use the bounding box from Overlay
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Evaluation logic
# version: 0.1.0
# status: development
# tags: evaluation
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from models import EvalIn

router = APIRouter(prefix="/api/yh", tags=["evals"])


@router.post("/evals")
def evals(body: EvalIn):
    """평가 메트릭 반환 (mock)"""
    # mock metrics for wiring
    return {
        "ocr_conf": 0.90,
        "text_ratio": 0.12,
        "clip_score": 0.33,
        "iou_forbidden": 0.0,
        "gate_pass": True
    }


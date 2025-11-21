
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

import json
import os
from fastapi import APIRouter
from PIL import Image
from models import DetectIn
from utils import abs_from_url, save_asset
from services.yolo_service import detect_forbidden_areas
from config import ASSETS_DIR, PART_NAME
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/yolo", tags=["yolo"])


@router.post("/detect")
def detect(body: DetectIn):
    """YOLO 금지 영역 감지"""
    im = Image.open(abs_from_url(body.asset_url))
    
    # YOLO 모델로 금지 영역 감지
    # 설정값은 config.py에서 가져옴 (환경 변수로 오버라이드 가능)
    result = detect_forbidden_areas(
        image=im,
        model_name=None,  # config에서 가져옴
        conf_threshold=None,  # config에서 가져옴
        iou_threshold=None,  # config에서 가져옴
        target_classes=None,  # 모든 클래스 감지 후 라벨로 필터링
        forbidden_labels=None  # config에서 가져옴 (없으면 기본 리스트 사용)
    )
    
    # 금지 영역 마스크 저장
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
    
    # 기존 API 형식과 호환되도록 반환
    return {
        "boxes": result["boxes"],
        "model": body.model,
        "confidences": result.get("confidences", []),
        "classes": result.get("classes", []),
        "labels": result.get("labels", []),
        "areas": result.get("areas", []),
        "widths": result.get("widths", []),
        "heights": result.get("heights", []),
        "forbidden_mask_url": forbidden_mask_url,  # 금지 영역 마스크 URL
        "detections": result.get("detections_json", [])  # JSON 형식 감지 결과
    }


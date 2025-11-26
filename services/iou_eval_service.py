
"""IoU 평가 서비스"""
########################################################
# IoU 평가 서비스
# - 음식 바운딩 박스와 텍스트 영역 겹침 확인
# - 기존 _compute_forbidden_iou 함수 재사용
########################################################
# created_at: 2025-11-26
# updated_at: 2025-11-26
# author: LEEYH205
# description: IoU evaluation service
# version: 1.0.0
# status: production
# tags: iou, evaluation
# dependencies: numpy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
from typing import Dict, Any, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


def calculate_iou_with_food(
    text_region: Tuple[float, float, float, float],  # 정규화된 좌표 (x, y, width, height)
    food_boxes: List[List[float]],  # xyxy 형식 (픽셀 좌표) 또는 정규화된 좌표
    image_width: int,
    image_height: int,
    boxes_are_normalized: bool = False  # food_boxes가 정규화된 좌표인지 여부
) -> Dict[str, Any]:
    """
    텍스트 영역과 음식 바운딩 박스 간 IoU 계산
    
    Args:
        text_region: 텍스트 영역 (정규화된 좌표: x, y, width, height)
        food_boxes: 음식 바운딩 박스 리스트 (xyxy 형식)
        image_width, image_height: 이미지 크기
        boxes_are_normalized: food_boxes가 정규화된 좌표인지 여부
    
    Returns:
        {
            "iou_with_food": float,  # 최대 IoU 값
            "max_iou_detection_id": Optional[str],  # 최대 IoU를 가진 detection ID
            "overlap_detected": bool,  # 겹침 감지 여부
            "all_ious": List[float]  # 모든 음식과의 IoU 리스트
        }
    """
    if not food_boxes:
        return {
            "iou_with_food": 0.0,
            "max_iou_detection_id": None,
            "overlap_detected": False,
            "all_ious": []
        }
    
    text_x, text_y, text_width, text_height = text_region
    text_right = text_x + text_width
    text_bottom = text_y + text_height
    text_area = text_width * text_height
    
    if text_area == 0:
        return {
            "iou_with_food": 0.0,
            "max_iou_detection_id": None,
            "overlap_detected": False,
            "all_ious": []
        }
    
    max_iou = 0.0
    max_iou_index = -1
    all_ious = []
    
    for i, food_box in enumerate(food_boxes):
        # food_box 형식: [x1, y1, x2, y2] (xyxy)
        if len(food_box) != 4:
            logger.warning(f"Invalid food_box format: {food_box}, skipping")
            all_ious.append(0.0)
            continue
        
        food_x1, food_y1, food_x2, food_y2 = food_box
        
        # 정규화된 좌표로 변환 (필요한 경우)
        if not boxes_are_normalized:
            food_x1_norm = food_x1 / image_width
            food_y1_norm = food_y1 / image_height
            food_x2_norm = food_x2 / image_width
            food_y2_norm = food_y2 / image_height
        else:
            food_x1_norm = food_x1
            food_y1_norm = food_y1
            food_x2_norm = food_x2
            food_y2_norm = food_y2
        
        # 정규화된 좌표로 변환된 food box의 너비와 높이
        food_width = food_x2_norm - food_x1_norm
        food_height = food_y2_norm - food_y1_norm
        food_area = food_width * food_height
        
        if food_area == 0:
            all_ious.append(0.0)
            continue
        
        # 교집합 계산
        intersection_x1 = max(text_x, food_x1_norm)
        intersection_y1 = max(text_y, food_y1_norm)
        intersection_x2 = min(text_right, food_x2_norm)
        intersection_y2 = min(text_bottom, food_y2_norm)
        
        if intersection_x2 > intersection_x1 and intersection_y2 > intersection_y1:
            intersection_area = (intersection_x2 - intersection_x1) * (intersection_y2 - intersection_y1)
            union_area = text_area + food_area - intersection_area
            
            if union_area > 0:
                iou = intersection_area / union_area
                all_ious.append(iou)
                
                if iou > max_iou:
                    max_iou = iou
                    max_iou_index = i
            else:
                all_ious.append(0.0)
        else:
            all_ious.append(0.0)
    
    overlap_detected = max_iou > 0.0
    
    logger.info(f"IoU 계산 완료: max_iou={max_iou:.3f}, overlap_detected={overlap_detected}, boxes_count={len(food_boxes)}")
    
    return {
        "iou_with_food": float(max_iou),
        "max_iou_detection_id": str(max_iou_index) if max_iou_index >= 0 else None,
        "overlap_detected": overlap_detected,
        "all_ious": [float(iou) for iou in all_ious]
    }


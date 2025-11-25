"""Planner 서비스 - 텍스트 오버레이 위치 제안"""
########################################################
# 텍스트 오버레이 위치 제안 알고리즘
# 
# 기능:
# - 금지 영역을 피한 최적의 위치 제안
# - 여러 위치 옵션 생성 (상단, 하단, 좌측, 우측)
# - 금지 영역 마스크를 활용한 정교한 계산
########################################################
# created_at: 2025-11-21
# updated_at: 2025-11-21
# author: LEEYH205
# description: Planner service for text overlay position proposal
# version: 0.1.0
# status: development
# tags: planner, service
# dependencies: pillow, numpy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import uuid
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import numpy as np
import logging

logger = logging.getLogger(__name__)


def propose_overlay_positions(
    image: Image.Image,
    detections: Optional[Dict[str, Any]] = None,
    forbidden_mask: Optional[Image.Image] = None,
    min_overlay_width: float = 0.5,
    min_overlay_height: float = 0.12,
    max_proposals: int = 10,
    max_forbidden_iou: float = 0.01  # 겹치지 않도록 엄격하게 (기존: 0.05)
) -> Dict[str, Any]:
    """
    텍스트 오버레이 위치 제안
    
    Args:
        image: 입력 이미지
        detections: YOLO 감지 결과 (boxes, labels 등)
        forbidden_mask: 금지 영역 마스크 (이진 이미지)
        min_overlay_width: 최소 오버레이 너비 비율 (0-1)
        min_overlay_height: 최소 오버레이 높이 비율 (0-1)
        max_proposals: 최대 제안 개수
        max_forbidden_iou: 최대 허용 금지 영역 IoU (0-1)
    
    Returns:
        {
            "proposals": [{"proposal_id": str, "xywh": [x, y, w, h], "color": str, "size": int, "source": str, "score": float}],
            "avoid": [x, y, w, h] (normalized xywh)
        }
    """
    w, h = image.size
    
    # 금지 영역 계산
    avoid_regions = []
    if detections and detections.get("boxes"):
        # 모든 박스를 정규화된 xywh 형식으로 변환
        for box in detections["boxes"]:
            x1, y1, x2, y2 = box
            x = max(0.0, min(1.0, x1 / w))
            y = max(0.0, min(1.0, y1 / h))
            width = min(1.0, (x2 - x1) / w)
            height = min(1.0, (y2 - y1) / h)
            avoid_regions.append([x, y, width, height])
    
    # 금지 영역 마스크가 있으면 사용
    mask_array = None
    if forbidden_mask:
        if isinstance(forbidden_mask, Image.Image):
            mask_array = np.array(forbidden_mask.convert("L"))
        else:
            mask_array = np.array(forbidden_mask)
    
    # 여러 위치 후보 생성 (금지 영역을 제외한 영역에서)
    logger.info(f"[Planner] 후보 생성 시작: w={w}, h={h}, avoid_regions={len(avoid_regions) if avoid_regions else 0}, mask_array={mask_array is not None}")
    candidates = _generate_position_candidates(
        w, h,
        avoid_regions,
        mask_array,
        min_overlay_width,
        min_overlay_height,
        max_proposals * 10  # 더 많은 후보 생성 후 필터링 (금지 영역을 피하기 위해 더 많이 생성)
    )
    
    # 각 후보에 대해 IoU 계산 및 필터링
    valid_proposals = []
    logger.info(f"[Planner] 생성된 candidates 개수: {len(candidates)}")
    print(f"[Planner] 생성된 candidates 개수: {len(candidates)}")
    for candidate in candidates:
        x, y, width, height = candidate["xywh"]
        
        # 금지 영역과의 IoU 계산
        occlusion_iou = _compute_forbidden_iou(
            x, y, width, height,
            avoid_regions,
            mask_array,
            w, h
        )
        
        # IoU가 임계값보다 작으면 제안에 포함 (금지 영역과 겹치지 않으면 됨)
        if occlusion_iou <= max_forbidden_iou:
            candidate["occlusion_iou"] = occlusion_iou
            candidate["score"] = candidate.get("score", 1.0) * (1.0 - occlusion_iou)  # 겹침이 적을수록 높은 점수
            valid_proposals.append(candidate)
    
    logger.info(f"[Planner] valid_proposals 개수: {len(valid_proposals)} (max_forbidden_iou={max_forbidden_iou})")
    print(f"[Planner] valid_proposals 개수: {len(valid_proposals)} (max_forbidden_iou={max_forbidden_iou})")
    
    # valid_proposals가 0개이면 fallback: IoU가 가장 낮은 candidate 사용 (하지만 max_forbidden_iou보다 작은 것만)
    if len(valid_proposals) == 0 and len(candidates) > 0:
        logger.warning(f"[Planner] 모든 candidate가 필터링됨 (max_forbidden_iou={max_forbidden_iou}). IoU가 가장 낮은 candidate를 fallback으로 사용")
        print(f"[Planner] 모든 candidate가 필터링됨 (max_forbidden_iou={max_forbidden_iou}). IoU가 가장 낮은 candidate를 fallback으로 사용")
        # 각 candidate의 IoU 계산
        candidate_ious = []
        for candidate in candidates:
            x, y, width, height = candidate["xywh"]
            iou = _compute_forbidden_iou(x, y, width, height, avoid_regions, mask_array, w, h)
            candidate_ious.append((candidate, iou))
        # IoU가 가장 낮은 candidate 선택 (하지만 가능하면 IoU가 0.0에 가까운 것)
        candidate_ious.sort(key=lambda x: x[1])
        best_candidate, best_iou = candidate_ious[0]
        if best_iou > 0.1:
            logger.warning(f"[Planner] Fallback candidate도 IoU가 높음 ({best_iou}). 금지 영역과 겹칠 수 있습니다.")
            print(f"[Planner] Fallback candidate도 IoU가 높음 ({best_iou}). 금지 영역과 겹칠 수 있습니다.")
        best_candidate["occlusion_iou"] = best_iou
        best_candidate["score"] = best_candidate.get("score", 1.0) * (1.0 - best_iou)
        valid_proposals.append(best_candidate)
        logger.info(f"[Planner] Fallback candidate 선택: source={best_candidate.get('source')}, IoU={best_iou}")
        print(f"[Planner] Fallback candidate 선택: source={best_candidate.get('source')}, IoU={best_iou}")
    
    # 크기별로 그룹화하여 다양성 확보
    proposals = []
    size_groups = {}
    
    # 크기별로 그룹화
    for prop in valid_proposals:
        x, y, width, height = prop["xywh"]
        size_key = f"{width:.2f}x{height:.2f}"
        if size_key not in size_groups:
            size_groups[size_key] = []
        size_groups[size_key].append(prop)
    
    # 각 크기 그룹에서 최상위 후보 선택 (다양성 확보)
    # 크기 그룹이 적으면 각 그룹에서 더 많이 선택
    if size_groups:
        proposals_per_size = max(1, (max_proposals + len(size_groups) - 1) // len(size_groups))
    else:
        proposals_per_size = max_proposals
    
    for size_key, group in size_groups.items():
        # 각 그룹 내에서 점수 순으로 정렬
        group.sort(key=lambda p: p.get("score", 0.0), reverse=True)
        
        # 중복 제거: 비슷한 위치의 제안 필터링
        filtered_group = []
        for prop in group:
            x1, y1, w1, h1 = prop["xywh"]
            is_duplicate = False
            
            for existing in filtered_group:
                x2, y2, w2, h2 = existing["xywh"]
                # 위치 차이 계산 (중심점 기준)
                center_x1 = x1 + w1 / 2
                center_y1 = y1 + h1 / 2
                center_x2 = x2 + w2 / 2
                center_y2 = y2 + h2 / 2
                
                # 중심점 거리
                dist_x = abs(center_x1 - center_x2)
                dist_y = abs(center_y1 - center_y2)
                
                # 너무 가까운 위치면 중복으로 간주 (크기의 30% 이내)
                threshold_x = max(w1, w2) * 0.3
                threshold_y = max(h1, h2) * 0.3
                if dist_x < threshold_x and dist_y < threshold_y:
                    is_duplicate = True
                    break
                
                # 같은 크기이고 위치가 거의 같으면 중복
                if abs(w1 - w2) < 0.01 and abs(h1 - h2) < 0.01:
                    if dist_x < 0.05 and dist_y < 0.05:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                filtered_group.append(prop)
                if len(filtered_group) >= proposals_per_size:
                    break
        
        # 각 크기에서 최상위 후보들 선택
        proposals.extend(filtered_group[:proposals_per_size])
    
    # 전체 점수 순으로 정렬
    proposals.sort(key=lambda p: p.get("score", 0.0), reverse=True)
    
    # 제안 개수 제한 (최대 크기 제안을 위해 1개 여유)
    proposals = proposals[:max_proposals]
    
    logger.info(f"[Planner] 크기 그룹화 후 proposals 개수: {len(proposals)}")
    
    # 추가: 금지 영역과 겹치지 않는 최대 크기 제안
    max_size_proposal = _find_max_size_proposal(
        w, h,
        avoid_regions,
        mask_array,
        min_overlay_width,
        min_overlay_height,
        max_forbidden_iou
    )
    
    if max_size_proposal:
        # 최대 크기 제안을 맨 앞에 추가 (우선순위)
        proposals.insert(0, max_size_proposal)
        # 총 개수는 max_proposals + 1 (최대 크기 포함)
        proposals = proposals[:max_proposals + 1]
        logger.info(f"[Planner] max_size_proposal 추가 후 proposals 개수: {len(proposals)}")
    else:
        logger.warning(f"[Planner] max_size_proposal을 찾지 못했습니다")
    
    # avoid 영역 (첫 번째 금지 영역 또는 None)
    avoid = avoid_regions[0] if avoid_regions else None
    
    logger.info(f"[Planner] 최종 반환 proposals 개수: {len(proposals)}")
    
    return {
        "proposals": proposals,
        "avoid": avoid
    }


def _propose_top_banner(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float
) -> Optional[Dict[str, Any]]:
    """상단 배너 위치 제안"""
    # 기본: 상단 10% ~ 28% 영역, 좌우 10% 마진
    x = 0.1
    y = 0.05
    width = 0.8
    height = 0.18
    
    # 금지 영역과 겹치는지 확인
    if _overlaps_with_forbidden(x, y, width, height, avoid_regions, mask_array, w, h):
        # 겹치면 위치 조정 시도
        # 상단을 더 좁게 하거나, 금지 영역 아래로 이동
        if avoid_regions:
            first_avoid = avoid_regions[0]
            avoid_y = first_avoid[1]
            avoid_height = first_avoid[3]
            avoid_bottom = avoid_y + avoid_height
            
            # 금지 영역이 상단에 있으면 더 위로 이동
            if avoid_bottom < 0.3:
                height = min(0.15, avoid_y - 0.02)
                if height < min_height:
                    return None
            else:
                # 금지 영역이 중앙에 있으면 상단을 더 좁게
                height = min(0.12, avoid_y - 0.02)
                if height < min_height:
                    return None
    
    if width < min_width or height < min_height:
        return None
    
    return {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [x, y, width, height],
        "color": "0d0d0dff",
        "size": 32,
        "source": "rule_top"
    }


def _propose_bottom_banner(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float
) -> Optional[Dict[str, Any]]:
    """하단 배너 위치 제안"""
    x = 0.1
    y = 0.82  # 하단에서 18% 높이
    width = 0.8
    height = 0.18
    
    if _overlaps_with_forbidden(x, y, width, height, avoid_regions, mask_array, w, h):
        if avoid_regions:
            first_avoid = avoid_regions[0]
            avoid_y = first_avoid[1]
            avoid_bottom = avoid_y + first_avoid[3]
            
            # 금지 영역이 하단에 있으면 더 아래로 이동
            if avoid_y > 0.7:
                y = min(0.95 - height, avoid_bottom + 0.02)
                if y + height > 1.0 or height < min_height:
                    return None
            else:
                # 금지 영역이 중앙에 있으면 하단을 더 좁게
                height = min(0.12, 1.0 - (avoid_bottom + 0.02))
                y = 1.0 - height
                if height < min_height:
                    return None
    
    if width < min_width or height < min_height:
        return None
    
    return {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [x, y, width, height],
        "color": "0d0d0dff",
        "size": 32,
        "source": "rule_bottom"
    }


def _propose_left_banner(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float
) -> Optional[Dict[str, Any]]:
    """좌측 세로 배너 위치 제안"""
    x = 0.05
    y = 0.1
    width = 0.15
    height = 0.8
    
    if _overlaps_with_forbidden(x, y, width, height, avoid_regions, mask_array, w, h):
        if avoid_regions:
            first_avoid = avoid_regions[0]
            avoid_x = first_avoid[0]
            avoid_width = first_avoid[2]
            avoid_right = avoid_x + avoid_width
            
            # 금지 영역이 좌측에 있으면 더 좁게
            if avoid_right < 0.3:
                width = min(0.12, avoid_x - 0.02)
                if width < min_width:
                    return None
    
    if width < min_width or height < min_height:
        return None
    
    return {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [x, y, width, height],
        "color": "0d0d0dff",
        "size": 28,
        "source": "rule_left"
    }


def _propose_right_banner(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float
) -> Optional[Dict[str, Any]]:
    """우측 세로 배너 위치 제안"""
    x = 0.85
    y = 0.1
    width = 0.15
    height = 0.8
    
    if _overlaps_with_forbidden(x, y, width, height, avoid_regions, mask_array, w, h):
        if avoid_regions:
            first_avoid = avoid_regions[0]
            avoid_x = first_avoid[0]
            
            # 금지 영역이 우측에 있으면 더 좁게
            if avoid_x > 0.7:
                width = min(0.12, 1.0 - (avoid_x + 0.02))
                x = 1.0 - width
                if width < min_width:
                    return None
    
    if width < min_width or height < min_height:
        return None
    
    return {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [x, y, width, height],
        "color": "0d0d0dff",
        "size": 28,
        "source": "rule_right"
    }


def _propose_center_top(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float
) -> Optional[Dict[str, Any]]:
    """중앙 상단 위치 제안 (금지 영역이 없는 경우)"""
    if avoid_regions or mask_array is not None:
        # 금지 영역이 있으면 중앙 상단 제안하지 않음
        return None
    
    x = 0.2
    y = 0.1
    width = 0.6
    height = 0.2
    
    return {
        "proposal_id": str(uuid.uuid4()),
        "xywh": [x, y, width, height],
        "color": "0d0d0dff",
        "size": 32,
        "source": "rule_center"
    }


def _generate_position_candidates(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float,
    max_candidates: int = 15
) -> List[Dict[str, Any]]:
    """
    금지 영역을 제외한 여러 위치 후보 생성
    
    Args:
        w: 이미지 너비
        h: 이미지 높이
        avoid_regions: 금지 영역 리스트
        mask_array: 금지 영역 마스크
        min_width: 최소 너비 비율
        min_height: 최소 높이 비율
        max_candidates: 최대 후보 개수
    
    Returns:
        후보 리스트 [{"xywh": [x, y, w, h], "source": str, "score": float}, ...]
    """
    candidates = []
    
    # 1. 고정 위치 후보들 (기존 규칙 기반)
    fixed_candidates = [
        # 상단 배너
        {"xywh": [0.1, 0.05, 0.8, 0.18], "source": "rule_top", "score": 0.9},
        # 하단 배너
        {"xywh": [0.1, 0.82, 0.8, 0.18], "source": "rule_bottom", "score": 0.8},
        # 좌측 세로
        {"xywh": [0.05, 0.1, 0.15, 0.8], "source": "rule_left", "score": 0.7},
        # 우측 세로
        {"xywh": [0.85, 0.1, 0.15, 0.8], "source": "rule_right", "score": 0.7},
        # 중앙 상단
        {"xywh": [0.2, 0.1, 0.6, 0.2], "source": "rule_center", "score": 0.85},
    ]
    
    candidates.extend(fixed_candidates)
    
    # 2. 그리드 기반 후보 생성 (금지 영역이 있는 경우)
    if avoid_regions or mask_array is not None:
        # 다양한 크기 조합 시도 (금지 영역을 피하기 위해 다양한 크기 필요)
        size_combinations = [
            (0.8, 0.18),  # 넓은 배너 (상단/하단용)
            (0.6, 0.15),  # 중간 배너
            (0.5, 0.12),  # 작은 배너
            (0.4, 0.15),  # 좁은 배너
            (0.7, 0.2),   # 넓고 높은 배너
            (0.3, 0.12),  # 매우 좁은 배너
            (0.9, 0.15),  # 매우 넓은 배너
            (0.65, 0.16), # 중간-넓은 배너
            (0.45, 0.14), # 중간-좁은 배너
        ]
        
        # 최소 크기 제한 확인
        valid_sizes = [
            (w, h) for w, h in size_combinations
            if w >= min_width and h >= min_height
        ]
        
        if not valid_sizes:
            # 최소 크기만 사용
            valid_sizes = [(max(min_width, 0.4), max(min_height, 0.12))]
        
        # 각 크기별로 그리드 생성 (크기 다양성 확보)
        for size_idx, (width, height) in enumerate(valid_sizes):
            # 크기별로 그리드 간격 조정 (큰 크기는 더 넓은 간격)
            # 작은 크기는 더 많은 위치 시도, 큰 크기는 적은 위치 시도
            if width >= 0.7:
                step_x = 3  # 큰 크기는 3개 위치만
                step_y = 3
            elif width >= 0.5:
                step_x = 4  # 중간 크기는 4개 위치
                step_y = 4
            else:
                step_x = 5  # 작은 크기는 5개 위치
                step_y = 5
            
        # 주요 위치만 시도 (상단, 중앙, 하단, 좌측, 우측)
        key_positions = []
        
        # 상단 영역 - 좌측, 중앙, 우측만 시도
        if step_x >= 3:
            key_positions.append((0.0, 0.0, "top_left"))
            key_positions.append(((1.0 - width) / 2, 0.0, "top_center"))
            key_positions.append((1.0 - width, 0.0, "top_right"))
        elif step_x == 2:
            key_positions.append((0.0, 0.0, "top_left"))
            key_positions.append((1.0 - width, 0.0, "top_right"))
        else:
            key_positions.append((0.0, 0.0, "top"))
        
        # 중앙 영역 (금지 영역을 피하기 위해)
        if avoid_regions:
            avoid_y_min = min(reg[1] for reg in avoid_regions)
            avoid_y_max = max(reg[1] + reg[3] for reg in avoid_regions)
            # 금지 영역 위쪽 중앙
            if avoid_y_min > height + 0.1:
                mid_y = (avoid_y_min - height) / 2
                key_positions.append(((1.0 - width) / 2, mid_y, "mid_top"))
            # 금지 영역 아래쪽 중앙
            if avoid_y_max + height < 0.9:
                mid_y = min(avoid_y_max + 0.05, 1.0 - height)
                key_positions.append(((1.0 - width) / 2, mid_y, "mid_bottom"))
        else:
            # 금지 영역이 없으면 중앙 시도
            key_positions.append(((1.0 - width) / 2, (1.0 - height) / 2, "center"))
        
        # 하단 영역 - 좌측, 중앙, 우측만 시도
        if step_x >= 3:
            key_positions.append((0.0, 1.0 - height, "bottom_left"))
            key_positions.append(((1.0 - width) / 2, 1.0 - height, "bottom_center"))
            key_positions.append((1.0 - width, 1.0 - height, "bottom_right"))
        elif step_x == 2:
            key_positions.append((0.0, 1.0 - height, "bottom_left"))
            key_positions.append((1.0 - width, 1.0 - height, "bottom_right"))
        else:
            key_positions.append((0.0, 1.0 - height, "bottom"))
        
        # 좌측/우측 영역 (세로 배너)
        if height > 0.3:  # 세로 배너는 높이가 충분할 때만
            # 좌측 - 상단, 중앙, 하단만 시도
            if step_y >= 3:
                key_positions.append((0.0, 0.0, "left_top"))
                key_positions.append((0.0, (1.0 - height) / 2, "left_center"))
                key_positions.append((0.0, 1.0 - height, "left_bottom"))
            elif step_y == 2:
                key_positions.append((0.0, 0.0, "left_top"))
                key_positions.append((0.0, 1.0 - height, "left_bottom"))
            else:
                key_positions.append((0.0, 0.0, "left"))
            # 우측 - 상단, 중앙, 하단만 시도
            if step_y >= 3:
                key_positions.append((1.0 - width, 0.0, "right_top"))
                key_positions.append((1.0 - width, (1.0 - height) / 2, "right_center"))
                key_positions.append((1.0 - width, 1.0 - height, "right_bottom"))
            elif step_y == 2:
                key_positions.append((1.0 - width, 0.0, "right_top"))
                key_positions.append((1.0 - width, 1.0 - height, "right_bottom"))
            else:
                key_positions.append((1.0 - width, 0.0, "right"))
        
        # 각 위치에 대해 후보 생성
        for x, y, pos_name in key_positions:
                # 경계 체크
                if x + width > 1.0:
                    x = 1.0 - width
                if y + height > 1.0:
                    y = 1.0 - height
                
                if x < 0 or y < 0:
                    continue
                
                # 위치 점수 계산 (상단/좌측에 가까울수록 높은 점수)
                position_score = 1.0 - (y * 0.3 + x * 0.1)  # 상단 우선
                # 크기 점수 (적당한 크기가 높은 점수)
                size_score = (width * 0.4 + height * 0.6) * 0.3
                # 크기 다양성 보너스
                diversity_bonus = (len(valid_sizes) - size_idx) * 0.05
                total_score = position_score + size_score + diversity_bonus
                
                candidates.append({
                    "xywh": [x, y, width, height],
                    "source": f"grid_{pos_name}_w{int(width*10)}_h{int(height*100)}",
                    "score": total_score
                })
    
    # 각 후보에 proposal_id 추가
    for candidate in candidates:
        candidate["proposal_id"] = str(uuid.uuid4())
        candidate["color"] = "0d0d0dff"
        candidate["size"] = 32
    
    return candidates[:max_candidates]


def _compute_forbidden_iou(
    x: float, y: float, width: float, height: float,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    img_w: int, img_h: int
) -> float:
    """
    제안 영역과 금지 영역 간의 IoU (Intersection over Union) 계산
    
    Args:
        x, y, width, height: 제안 영역 (정규화된 좌표)
        avoid_regions: 금지 영역 리스트
        mask_array: 금지 영역 마스크
        img_w, img_h: 이미지 크기
    
    Returns:
        IoU 값 (0.0 ~ 1.0)
    """
    proposal_right = x + width
    proposal_bottom = y + height
    proposal_area = width * height
    
    if proposal_area == 0:
        return 0.0
    
    max_iou = 0.0
    
    # 박스 기반 금지 영역과의 IoU 계산
    for avoid in avoid_regions:
        avoid_x, avoid_y, avoid_w, avoid_h = avoid
        avoid_right = avoid_x + avoid_w
        avoid_bottom = avoid_y + avoid_h
        avoid_area = avoid_w * avoid_h
        
        # 교집합 계산
        intersection_x1 = max(x, avoid_x)
        intersection_y1 = max(y, avoid_y)
        intersection_x2 = min(proposal_right, avoid_right)
        intersection_y2 = min(proposal_bottom, avoid_bottom)
        
        if intersection_x2 > intersection_x1 and intersection_y2 > intersection_y1:
            intersection_area = (intersection_x2 - intersection_x1) * (intersection_y2 - intersection_y1)
            union_area = proposal_area + avoid_area - intersection_area
            
            if union_area > 0:
                iou = intersection_area / union_area
                max_iou = max(max_iou, iou)
    
    # 마스크 기반 금지 영역과의 IoU 계산
    if mask_array is not None:
        # 정규화된 좌표를 픽셀 좌표로 변환
        px1 = max(0, min(img_w - 1, int(x * img_w)))
        py1 = max(0, min(img_h - 1, int(y * img_h)))
        px2 = max(0, min(img_w - 1, int(proposal_right * img_w)))
        py2 = max(0, min(img_h - 1, int(proposal_bottom * img_h)))
        
        if px2 > px1 and py2 > py1:
            # 제안 영역 마스크 생성
            proposal_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            proposal_mask[py1:py2, px1:px2] = 255
            
            # 금지 영역 마스크와 교집합 계산
            intersection_mask = np.logical_and(
                proposal_mask > 128,
                mask_array > 128
            )
            union_mask = np.logical_or(
                proposal_mask > 128,
                mask_array > 128
            )
            
            intersection_pixels = np.sum(intersection_mask)
            union_pixels = np.sum(union_mask)
            
            if union_pixels > 0:
                iou = intersection_pixels / union_pixels
                max_iou = max(max_iou, iou)
    
    return max_iou


def _find_max_size_proposal(
    w: int, h: int,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    min_width: float,
    min_height: float,
    max_forbidden_iou: float
) -> Optional[Dict[str, Any]]:
    """
    금지 영역과 겹치지 않는 최대 크기 제안 찾기
    
    Args:
        w, h: 이미지 크기
        avoid_regions: 금지 영역 리스트
        mask_array: 금지 영역 마스크
        min_width: 최소 너비 비율
        min_height: 최소 높이 비율
        max_forbidden_iou: 최대 허용 IoU
    
    Returns:
        최대 크기 제안 또는 None
    """
    best_proposal = None
    max_area = 0.0
    
    # 금지 영역 분석: 금지 영역 주변의 빈 공간 찾기
    if avoid_regions:
        # 금지 영역의 경계 찾기
        avoid_x_min = min(reg[0] for reg in avoid_regions)
        avoid_y_min = min(reg[1] for reg in avoid_regions)
        avoid_x_max = max(reg[0] + reg[2] for reg in avoid_regions)
        avoid_y_max = max(reg[1] + reg[3] for reg in avoid_regions)
        
        # 가능한 최대 영역들 시도
        candidate_regions = [
            # 상단 영역 (금지 영역 위쪽)
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": avoid_y_min, "name": "top_full"},
            # 하단 영역 (금지 영역 아래쪽)
            {"x": 0.0, "y": avoid_y_max, "width": 1.0, "height": 1.0 - avoid_y_max, "name": "bottom_full"},
            # 좌측 영역 (금지 영역 왼쪽)
            {"x": 0.0, "y": 0.0, "width": avoid_x_min, "height": 1.0, "name": "left_full"},
            # 우측 영역 (금지 영역 오른쪽)
            {"x": avoid_x_max, "y": 0.0, "width": 1.0 - avoid_x_max, "height": 1.0, "name": "right_full"},
        ]
    else:
        # 금지 영역이 없으면 전체 영역 시도
        candidate_regions = [
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0, "name": "full"},
        ]
    
    # 각 후보 영역에서 최대 크기 찾기
    for region in candidate_regions:
        x = region["x"]
        y = region["y"]
        width = region["width"]
        height = region["height"]
        name = region["name"]
        
        # 최소 크기 체크
        if width < min_width or height < min_height:
            continue
        
        # 경계 체크
        if x + width > 1.0:
            width = 1.0 - x
        if y + height > 1.0:
            height = 1.0 - y
        
        if width < min_width or height < min_height:
            continue
        
        # 금지 영역과의 IoU 확인
        iou = _compute_forbidden_iou(x, y, width, height, avoid_regions, mask_array, w, h)
        
        if iou <= max_forbidden_iou:
            area = width * height
            if area > max_area:
                max_area = area
                best_proposal = {
                    "proposal_id": str(uuid.uuid4()),
                    "xywh": [x, y, width, height],
                    "source": f"max_size_{name}",
                    "color": "0d0d0dff",
                    "size": 32,
                    "score": 1.0,
                    "occlusion_iou": iou,
                    "area": area
                }
    
    # 추가: 더 세밀한 탐색 (금지 영역 주변의 최적 크기 찾기)
    if avoid_regions:
        # 상단 영역에서 세밀하게 탐색
        if avoid_y_min > min_height:
            for width in [1.0, 0.95, 0.9, 0.85, 0.8]:
                if width < min_width:
                    continue
                for height in [avoid_y_min - 0.05, avoid_y_min - 0.02, avoid_y_min]:
                    if height < min_height:
                        continue
                    x = (1.0 - width) / 2  # 중앙 정렬
                    y = 0.0
                    
                    iou = _compute_forbidden_iou(x, y, width, height, avoid_regions, mask_array, w, h)
                    if iou <= max_forbidden_iou:
                        area = width * height
                        if area > max_area:
                            max_area = area
                            best_proposal = {
                                "proposal_id": str(uuid.uuid4()),
                                "xywh": [x, y, width, height],
                                "source": f"max_size_top_optimized",
                                "color": "0d0d0dff",
                                "size": 32,
                                "score": 1.0,
                                "occlusion_iou": iou,
                                "area": area
                            }
        
        # 하단 영역에서 세밀하게 탐색
        bottom_height = 1.0 - avoid_y_max
        if bottom_height > min_height:
            for width in [1.0, 0.95, 0.9, 0.85, 0.8]:
                if width < min_width:
                    continue
                for height in [bottom_height, bottom_height - 0.02, bottom_height - 0.05]:
                    if height < min_height:
                        continue
                    x = (1.0 - width) / 2  # 중앙 정렬
                    y = avoid_y_max
                    
                    iou = _compute_forbidden_iou(x, y, width, height, avoid_regions, mask_array, w, h)
                    if iou <= max_forbidden_iou:
                        area = width * height
                        if area > max_area:
                            max_area = area
                            best_proposal = {
                                "proposal_id": str(uuid.uuid4()),
                                "xywh": [x, y, width, height],
                                "source": f"max_size_bottom_optimized",
                                "color": "0d0d0dff",
                                "size": 32,
                                "score": 1.0,
                                "occlusion_iou": iou,
                                "area": area
                            }
    
    return best_proposal


def _overlaps_with_forbidden(
    x: float, y: float, width: float, height: float,
    avoid_regions: List[List[float]],
    mask_array: Optional[np.ndarray],
    img_w: int, img_h: int
) -> bool:
    """제안 영역이 금지 영역과 겹치는지 확인 (IoU > 0)"""
    iou = _compute_forbidden_iou(x, y, width, height, avoid_regions, mask_array, img_w, img_h)
    return iou > 0.0


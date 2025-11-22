"""YOLO 모델 서비스"""
########################################################
# YOLOv8 모델 로드 및 추론 서비스
# 
# 사용 가능한 모델:
# - yolov8x-seg.pt (Segmentation 모델)
#
# 금지 영역 감지:
# - 이미지에서 금지 영역(예: 사람 얼굴, 특정 객체)을 감지
# - 바운딩 박스(xyxy 형식) 반환
########################################################
# created_at: 2025-11-21
# updated_at: 2025-11-21
# author: LEEYH205
# description: YOLO model service
# version: 0.1.0
# status: development
# tags: yolo, model, service
# dependencies: ultralytics, torch, pillow
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
import json
from typing import Optional, Dict, Any, List
from PIL import Image
import numpy as np
import torch
from ultralytics import YOLO
from config import DEVICE_TYPE, MODEL_DIR, YOLO_MODEL_NAME, YOLO_CONF_THRESHOLD, YOLO_IOU_THRESHOLD, YOLO_FORBIDDEN_LABELS
import logging

logger = logging.getLogger(__name__)

# 디바이스 설정
DEVICE = DEVICE_TYPE if DEVICE_TYPE == "cuda" and torch.cuda.is_available() else "cpu"

# 전역 모델 변수 (lazy loading)
_model: Optional[YOLO] = None
_model_path: Optional[str] = None


def get_yolo_model(model_name: str = "yolov8x-seg.pt") -> YOLO:
    """YOLO 모델 로드 (싱글톤 패턴)"""
    global _model, _model_path
    
    model_path = os.path.join(MODEL_DIR, model_name)
    
    # 모델이 로드되지 않았거나 다른 모델을 요청한 경우
    if _model is None or _model_path != model_path:
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"YOLO 모델 파일을 찾을 수 없습니다: {model_path}\n"
                f"다운로드 스크립트를 실행하세요: python download_yolo_model.py"
            )
        
        print(f"Loading YOLO model: {model_name} on {DEVICE}")
        print(f"Model path: {model_path}")
        
        # YOLO 모델 로드
        _model = YOLO(model_path)
        _model_path = model_path
        
        # 디바이스 설정
        if DEVICE == "cuda":
            _model.to(DEVICE)
        
        print(f"✓ YOLO model loaded successfully")
    
    return _model


def detect_forbidden_areas(
    image: Image.Image,
    model_name: Optional[str] = None,
    conf_threshold: Optional[float] = None,
    iou_threshold: Optional[float] = None,
    target_classes: Optional[List[int]] = None,
    forbidden_labels: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    이미지에서 금지 영역 감지
    
    Args:
        image: PIL Image 객체
        model_name: 사용할 YOLO 모델 파일명 (None이면 config에서 가져옴)
        conf_threshold: 신뢰도 임계값 (None이면 config에서 가져옴)
        iou_threshold: IoU 임계값 (None이면 config에서 가져옴)
        target_classes: 감지할 클래스 ID 리스트 (None이면 모든 클래스)
                       COCO 데이터셋: 0=person, 46=banana, 47=apple, ...
        forbidden_labels: 금지 라벨 이름 리스트 (None이면 config에서 가져옴)
    
    Returns:
        {
            "boxes": [[x1, y1, x2, y2], ...],  # xyxy 형식
            "confidences": [0.95, ...],
            "classes": [0, ...],
            "labels": ["person", ...],  # 클래스 이름
            "areas": [1234.5, ...],
            "widths": [100.0, ...],
            "heights": [200.0, ...],
            "model": model_name,
            "forbidden_mask": PIL Image (L 모드)  # 금지 영역 마스크
        }
    """
    # 설정값 적용 (인자로 전달되지 않으면 config에서 가져옴)
    model_name = model_name or YOLO_MODEL_NAME
    conf_threshold = conf_threshold if conf_threshold is not None else YOLO_CONF_THRESHOLD
    iou_threshold = iou_threshold if iou_threshold is not None else YOLO_IOU_THRESHOLD
    
    # 금지 라벨 설정 (인자로 전달되지 않으면 config에서 가져옴)
    if forbidden_labels is None:
        forbidden_labels = YOLO_FORBIDDEN_LABELS
    
    # 기본 금지 라벨 리스트 (config에도 환경 변수에도 없을 때 사용)
    # 광고 이미지에서 텍스트 오버레이를 피해야 할 영역:
    # - 사람 및 동물 (주의 분산)
    # - 전자기기 (브랜드/로고 노출)
    # - 가구 (배경 요소)
    # - 음식 및 식기류 (제품과 혼동)
    # - 가방/소지품 (주의 분산)
    if forbidden_labels is None:
        forbidden_labels = [
            # 사람 및 동물
            "person",
            "hand",
            #"cat",
            #"dog",

            # 음식
            "pizza",
            "sandwich",
            "cake",
            "donut",
            "hot dog",
            "banana",
            "apple",
            "orange",
            "broccoli",
            "carrot",
            
            # 식기류 및 용기
            #"bottle",
            #"cup",
            #"fork",
            #"knife",
            #"spoon",
            #"wine glass",
            "bowl",
            "plate",
            # 전자기기
            #"cell phone",
            #"laptop",
            #"mouse",
            #"keyboard",
            #"remote",
            ####"tv",
            #"microwave",
            #"oven",
            #"toaster",
            #"refrigerator",

            # 가구
            #"chair",
            #"couch",
            #"bed",
            #"dining table",

            # 가방 및 소지품
            #"backpack",
            #"handbag",
            #"suitcase",
            #"umbrella",

            # 기타
            #"clock",
            #"book",
            #"scissors",
            #"vase",
            #"potted plant",
            #"teddy bear",
        ]
    model = get_yolo_model(model_name)
    
    # GPU 메모리 정리
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
        # 메모리 단편화 방지
        import gc
        gc.collect()
    
    # YOLO 추론 실행
    # forbidden_labels를 사용하는 경우 모든 클래스를 감지한 후 필터링
    # (이전 코드와 동일한 방식)
    classes_to_detect = target_classes if (target_classes and forbidden_labels is None) else None
    results = model.predict(
        image,
        conf=conf_threshold,
        iou=iou_threshold,
        device=DEVICE,
        classes=classes_to_detect,  # target_classes가 있고 forbidden_labels가 None일 때만 사용
        verbose=False
    )
    
    boxes = []
    confidences = []
    classes = []
    labels = []
    areas = []
    widths = []
    heights = []
    
    # 결과 파싱
    if results and len(results) > 0:
        result = results[0]
        
        # 모델의 클래스 이름 가져오기 (YOLO 모델은 항상 result.names를 제공)
        model_names = result.names
        
        # 바운딩 박스 정보 추출
        if result.boxes is not None and len(result.boxes) > 0:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                
                # 클래스 이름 가져오기
                label = model_names.get(cls_id, f"class_{cls_id}")
                
                # 라벨 이름 기반 필터링 (이전 코드와 동일)
                if forbidden_labels and label not in forbidden_labels:
                    continue
                
                # target_classes 필터링 (forbidden_labels가 None일 때만 사용)
                if forbidden_labels is None and target_classes is not None:
                    if cls_id not in target_classes:
                        continue
                
                # xyxy 형식으로 변환
                x1, y1, x2, y2 = box.xyxy[0].cpu().tolist()
                conf = float(box.conf[0].cpu())
                
                boxes.append([x1, y1, x2, y2])
                confidences.append(conf)
                classes.append(cls_id)
                labels.append(label)
                
                # 박스 크기 계산
                width = x2 - x1
                height = y2 - y1
                area = width * height
                
                widths.append(width)
                heights.append(height)
                areas.append(area)
    
    # GPU 메모리 정리
    if DEVICE == "cuda":
        torch.cuda.empty_cache()
    
    # 금지 영역 마스크 생성
    forbidden_mask = boxes_to_mask(boxes, image.width, image.height)
    
    # JSON 형식의 감지 결과 생성 (normalized bbox)
    detections_json = []
    img_width = image.width
    img_height = image.height
    
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        # xyxy를 normalized xywh로 변환
        x = max(0.0, min(1.0, x1 / img_width))
        y = max(0.0, min(1.0, y1 / img_height))
        width = min(1.0, (x2 - x1) / img_width)
        height = min(1.0, (y2 - y1) / img_height)
        
        detections_json.append({
            "label": labels[i] if i < len(labels) else f"class_{classes[i] if i < len(classes) else 'unknown'}",
            "confidence": confidences[i] if i < len(confidences) else 0.0,
            "bbox": [x, y, width, height]  # normalized [x, y, width, height]
        })
    
    return {
        "boxes": boxes,  # xyxy 형식 (절대 좌표)
        "confidences": confidences,
        "classes": classes,
        "labels": labels,
        "areas": areas,
        "widths": widths,
        "heights": heights,
        "model": model_name,
        "forbidden_mask": forbidden_mask,  # PIL Image (L 모드, 0=허용, 255=금지)
        "detections_json": detections_json  # JSON 형식 (normalized bbox)
    }


def boxes_to_mask(boxes: List[List[float]], width: int, height: int) -> Image.Image:
    """
    바운딩 박스 리스트를 금지 영역 마스크로 변환
    
    Args:
        boxes: 바운딩 박스 리스트 [[x1, y1, x2, y2], ...] (xyxy 형식, 픽셀 단위)
        width: 이미지 너비
        height: 이미지 높이
    
    Returns:
        PIL Image (L 모드): 0=허용 영역, 255=금지 영역
    """
    # 빈 마스크 생성 (0=허용 영역)
    mask_array = np.zeros((height, width), dtype=np.uint8)
    
    for box in boxes:
        x1, y1, x2, y2 = box
        
        # 좌표를 정수로 변환하고 이미지 범위 내로 제한
        x0 = max(0, int(x1))
        y0 = max(0, int(y1))
        x1_clipped = min(width, int(x2))
        y1_clipped = min(height, int(y2))
        
        # 금지 영역을 255로 설정
        if x1_clipped > x0 and y1_clipped > y0:
            mask_array[y0:y1_clipped, x0:x1_clipped] = 255
    
    # PIL Image로 변환
    return Image.fromarray(mask_array, mode="L")


"""YOLO 감지 테스트 스크립트"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정 (모듈 import 전에 설정해야 함)
# 실제 이미지가 있는 경로로 설정
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

# 환경 변수 설정 후 모듈 import
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from routers.yolo import detect
from models import DetectIn
from utils import abs_from_url


def draw_bboxes_on_image(
    image: Image.Image,
    boxes: list,
    confidences: list = None,
    classes: list = None,
    box_color: str = "red",
    text_color: str = "white",
    line_width: int = 3
) -> Image.Image:
    """
    이미지에 바운딩 박스 그리기
    
    Args:
        image: PIL Image 객체
        boxes: 바운딩 박스 리스트 [[x1, y1, x2, y2], ...]
        confidences: 신뢰도 리스트 (선택사항)
        classes: 클래스 ID 리스트 (선택사항)
        box_color: 박스 색상
        text_color: 텍스트 색상
        line_width: 선 두께
    
    Returns:
        바운딩 박스가 그려진 이미지
    """
    # 이미지를 RGB로 변환 (RGBA도 지원)
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    draw = ImageDraw.Draw(image)
    
    # 폰트 로드 시도
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
        except:
            font = ImageFont.load_default()
    
    # COCO 클래스 이름 (사람과 음식 관련 클래스)
    coco_classes = {
        0: "person",
        46: "banana", 47: "apple", 48: "sandwich", 49: "orange",
        50: "broccoli", 51: "carrot", 52: "hot dog", 53: "pizza",
        54: "donut", 55: "cake"
    }
    
    for i, box in enumerate(boxes):
        x1, y1, x2, y2 = box
        
        # 박스 그리기
        draw.rectangle(
            [x1, y1, x2, y2],
            outline=box_color,
            width=line_width
        )
        
        # 레이블 텍스트 생성
        label_parts = []
        if classes and i < len(classes):
            cls_id = classes[i]
            cls_name = coco_classes.get(cls_id, f"class_{cls_id}")
            label_parts.append(cls_name)
        
        if confidences and i < len(confidences):
            conf = confidences[i]
            label_parts.append(f"{conf:.2f}")
        
        label = " ".join(label_parts) if label_parts else f"Box {i+1}"
        
        # 텍스트 배경 그리기 (가독성 향상)
        try:
            bbox = draw.textbbox((x1, y1 - 20), label, font=font)
            text_bg = [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2]
            draw.rectangle(text_bg, fill=box_color)
            draw.text((x1, y1 - 20), label, fill=text_color, font=font)
        except:
            # 폰트 로드 실패 시 기본 폰트 사용
            draw.rectangle([x1, y1 - 20, x1 + 100, y1], fill=box_color)
            draw.text((x1 + 2, y1 - 18), label, fill=text_color)
    
    return image


def test_yolo_detection():
    """YOLO 금지 영역 감지 테스트"""
    
    # 테스트 데이터
    # image_path: 파일 시스템의 절대 경로 (PIL Image.open()에서 직접 사용)
    # asset_url: API에서 사용하는 URL 형식 (/assets/로 시작)
    #            → detect() 함수 내부에서 abs_from_url()로 절대 경로로 변환됨
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    asset_url = "/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    tenant_id = "test_tenant"
    model = "forbidden"
    
    print("=" * 60)
    print("YOLO Detection 테스트")
    print("=" * 60)
    print(f"이미지 경로: {image_path}")
    print(f"Asset URL: {asset_url}")
    print(f"Tenant ID: {tenant_id}")
    print(f"Model: {model}")
    print("=" * 60)
    
    try:
        # 이미지 로드 및 정보 확인
        print("\n[1/3] 이미지 로드 중...")
        image = Image.open(image_path)
        w, h = image.size
        print(f"✓ 이미지 로드 완료: {w}x{h}")
        
        # YOLO 감지 실행
        print("\n[2/3] YOLO 감지 실행 중...")
        request_body = DetectIn(
            tenant_id=tenant_id,
            asset_url=asset_url,
            model=model
        )
        result = detect(request_body)
        
        # 결과 출력
        print("\n[3/3] 감지 완료!")
        print("\n" + "=" * 60)
        print("YOLO 감지 결과")
        print("=" * 60)
        print(f"✓ 모델: {result.get('model', 'N/A')}")
        print(f"✓ 감지된 박스 개수: {len(result.get('boxes', []))}")
        
        # 각 박스 정보 출력
        for i, box in enumerate(result.get('boxes', [])):
            print(f"\n박스 {i+1}:")
            print(f"  - 형식: xyxy (x1, y1, x2, y2)")
            print(f"  - 좌표: [{box[0]:.2f}, {box[1]:.2f}, {box[2]:.2f}, {box[3]:.2f}]")
            
            # 박스 크기 계산
            box_width = box[2] - box[0]
            box_height = box[3] - box[1]
            box_area = box_width * box_height
            image_area = w * h
            box_ratio = (box_area / image_area) * 100
            
            print(f"  - 너비: {box_width:.2f}px")
            print(f"  - 높이: {box_height:.2f}px")
            print(f"  - 면적: {box_area:.2f}px² ({box_ratio:.2f}% of image)")
            
            # 박스 중심점
            center_x = (box[0] + box[2]) / 2
            center_y = (box[1] + box[3]) / 2
            print(f"  - 중심점: ({center_x:.2f}, {center_y:.2f})")
            
            # 이미지 중심과의 거리
            image_center_x = w / 2
            image_center_y = h / 2
            distance_from_center = ((center_x - image_center_x)**2 + (center_y - image_center_y)**2)**0.5
            print(f"  - 이미지 중심으로부터 거리: {distance_from_center:.2f}px")
        
        # 검증
        print("\n" + "-" * 60)
        print("검증 결과")
        print("-" * 60)
        
        # 박스 형식 검증 (xyxy)
        boxes = result.get('boxes', [])
        if boxes:
            box = boxes[0]
            is_valid_format = (
                len(box) == 4 and
                box[0] < box[2] and  # x1 < x2
                box[1] < box[3] and  # y1 < y2
                box[0] >= 0 and box[1] >= 0 and  # 좌표가 0 이상
                box[2] <= w and box[3] <= h  # 좌표가 이미지 크기 이하
            )
            print(f"✓ 박스 형식 검증: {'통과' if is_valid_format else '실패'}")
            
            if not is_valid_format:
                print("  ⚠ 경고: 박스 좌표가 유효하지 않습니다!")
        else:
            print("⚠ 경고: 감지된 박스가 없습니다!")
        
        # 바운딩 박스를 이미지에 그리기
        print("\n" + "-" * 60)
        print("이미지 시각화")
        print("-" * 60)
        visualized_image = draw_bboxes_on_image(
            image.copy(),
            result.get('boxes', []),
            result.get('confidences', []),
            result.get('classes', [])
        )
        
        # 결과 이미지 저장
        output_dir = os.path.join(project_root, "test", "output")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "yolo_detection_result.png")
        visualized_image.save(output_path)
        print(f"✓ 시각화된 이미지 저장: {output_path}")
        
        # 금지 영역 마스크 저장 (서비스에서 직접 가져오기)
        from services.yolo_service import detect_forbidden_areas
        import json
        service_result = detect_forbidden_areas(
            image=image,
            model_name="yolov8x-seg.pt",
            conf_threshold=0.25,
            iou_threshold=0.45,
            target_classes=None,  # 모든 클래스 감지
            forbidden_labels=None  # 기본 금지 라벨 리스트 사용
        )
        forbidden_mask = service_result.get("forbidden_mask")
        if forbidden_mask:
            mask_path = os.path.join(output_dir, "forbidden_mask.png")
            forbidden_mask.save(mask_path)
            print(f"✓ 금지 영역 마스크 저장: {mask_path}")
            
            # detections.json 저장
            detections_json = service_result.get("detections_json", [])
            if detections_json:
                json_path = os.path.join(output_dir, "detections.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(detections_json, f, indent=2, ensure_ascii=False)
                print(f"✓ 감지 결과 JSON 저장: {json_path}")
                print(f"  - 감지된 객체 수: {len(detections_json)}")
            
            # 마스크를 원본 이미지에 오버레이하여 시각화
            overlay_image = image.copy().convert("RGBA")
            mask_rgba = forbidden_mask.convert("RGBA")
            # 금지 영역을 반투명 빨간색으로 표시
            red_overlay = Image.new("RGBA", overlay_image.size, (255, 0, 0, 100))
            # 마스크가 255인 영역만 오버레이
            mask_alpha = np.array(forbidden_mask) / 255.0
            red_overlay_array = np.array(red_overlay)
            red_overlay_array[:, :, 3] = (red_overlay_array[:, :, 3] * mask_alpha).astype(np.uint8)
            red_overlay = Image.fromarray(red_overlay_array)
            overlay_image = Image.alpha_composite(overlay_image, red_overlay)
            overlay_path = os.path.join(output_dir, "forbidden_area_overlay.png")
            overlay_image.convert("RGB").save(overlay_path)
            print(f"✓ 금지 영역 오버레이 저장: {overlay_path}")
        
        print("=" * 60)
        
        return result
        
    except FileNotFoundError:
        print(f"\n❌ 오류: 이미지를 찾을 수 없습니다: {image_path}")
        print("이미지 경로를 확인해주세요.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def test_yolo_multiple_models():
    """다양한 모델로 YOLO 감지 테스트"""
    
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    asset_url = "/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    tenant_id = "test_tenant"
    
    models_to_test = ["forbidden", "custom"]
    
    print("=" * 60)
    print("YOLO 다중 모델 테스트")
    print("=" * 60)
    
    results = {}
    
    for model in models_to_test:
        print(f"\n모델: {model}")
        print("-" * 60)
        
        try:
            request_body = DetectIn(
                tenant_id=tenant_id,
                asset_url=asset_url,
                model=model
            )
            result = detect(request_body)
            results[model] = result
            
            print(f"✓ 감지 완료")
            print(f"  - 박스 개수: {len(result.get('boxes', []))}")
            print(f"  - 반환된 모델: {result.get('model', 'N/A')}")
            
        except Exception as e:
            print(f"❌ 오류: {e}")
            results[model] = None
    
    # 비교 요약
    print("\n" + "=" * 60)
    print("비교 요약")
    print("=" * 60)
    for model, result in results.items():
        if result:
            print(f"{model}: {len(result.get('boxes', []))}개 박스 감지")
        else:
            print(f"{model}: 실패")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="YOLO 감지 테스트")
    parser.add_argument("--mode", choices=["single", "multiple"], default="single",
                       help="테스트 모드: single (기본), multiple (다중 모델)")
    args = parser.parse_args()
    
    if args.mode == "single":
        test_yolo_detection()
    else:
        test_yolo_multiple_models()


"""Planner 위치 제안 테스트 스크립트"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정 (모듈 import 전에 설정해야 함)
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

# 환경 변수 설정 후 모듈 import
from PIL import Image, ImageDraw, ImageFont
from routers.planner import planner
from models import PlannerIn
from utils import abs_from_url, save_asset
import json


def draw_proposals_on_image(
    image: Image.Image,
    proposals: list,
    avoid: list = None,
    proposal_color: str = "green",
    avoid_color: str = "red",
    line_width: int = 3
) -> Image.Image:
    """
    이미지에 제안 위치와 금지 영역 그리기
    
    Args:
        image: PIL Image 객체
        proposals: 제안 리스트 [{"xywh": [x, y, w, h], ...}, ...]
        avoid: 금지 영역 [x, y, w, h] (정규화된 좌표)
        proposal_color: 제안 영역 색상
        avoid_color: 금지 영역 색상
        line_width: 선 두께
    
    Returns:
        제안 위치가 그려진 이미지
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    draw = ImageDraw.Draw(image)
    w, h = image.size
    
    # 폰트 로드 시도
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
        except:
            font = ImageFont.load_default()
    
    # 금지 영역 그리기
    if avoid:
        ax, ay, aw, ah = avoid
        ax_px = int(ax * w)
        ay_px = int(ay * h)
        aw_px = int(aw * w)
        ah_px = int(ah * h)
        
        draw.rectangle(
            [ax_px, ay_px, ax_px + aw_px, ay_px + ah_px],
            outline=avoid_color,
            width=line_width
        )
        
        # 금지 영역 레이블
        label = "FORBIDDEN"
        try:
            bbox = draw.textbbox((ax_px, ay_px - 25), label, font=font)
            text_bg = [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2]
            draw.rectangle(text_bg, fill=avoid_color)
            draw.text((ax_px, ay_px - 25), label, fill="white", font=font)
        except:
            draw.rectangle([ax_px, ay_px - 25, ax_px + 120, ay_px], fill=avoid_color)
            draw.text((ax_px, ay_px - 25), label, fill="white")
    
    # 제안 위치 그리기
    colors = ["green", "blue", "yellow", "cyan", "magenta"]
    for i, proposal in enumerate(proposals):
        xywh = proposal.get("xywh", [])
        if len(xywh) != 4:
            continue
        
        x, y, width, height = xywh
        x_px = int(x * w)
        y_px = int(y * h)
        width_px = int(width * w)
        height_px = int(height * h)
        
        # 제안 영역 색상 (여러 제안이 있으면 다른 색상 사용)
        color = colors[i % len(colors)]
        
        # 반투명 배경 그리기
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle(
            [x_px, y_px, x_px + width_px, y_px + height_px],
            fill=(0, 255, 0, 50) if color == "green" else (0, 0, 255, 50),
            outline=color,
            width=line_width
        )
        image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(image)
        
        # 제안 레이블
        source = proposal.get("source", "unknown")
        proposal_id = proposal.get("proposal_id", "")[:8]
        label = f"{source} ({proposal_id})"
        
        try:
            bbox = draw.textbbox((x_px, y_px - 25), label, font=font)
            text_bg = [bbox[0] - 4, bbox[1] - 2, bbox[2] + 4, bbox[3] + 2]
            draw.rectangle(text_bg, fill=color)
            draw.text((x_px, y_px - 25), label, fill="white", font=font)
        except:
            draw.rectangle([x_px, y_px - 25, x_px + 200, y_px], fill=color)
            draw.text((x_px, y_px - 25), label, fill="white")
    
    return image


def test_planner_basic():
    """기본 Planner 테스트 (금지 영역 없음)"""
    
    print("=" * 60)
    print("Planner 기본 테스트 (금지 영역 없음)")
    print("=" * 60)
    
    # 테스트 이미지 생성
    print("\n[1/4] 테스트 이미지 생성 중...")
    test_image = Image.new("RGB", (800, 600), color="lightblue")
    print(f"✓ 이미지 생성 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # 이미지 저장
    from utils import save_asset
    asset_meta = save_asset("test_planner", "test_image", test_image, ".png")
    asset_url = asset_meta["url"]
    print(f"✓ 이미지 저장 완료: {asset_url}")
    
    # Planner 호출
    print("\n[2/4] Planner 위치 제안 생성 중...")
    body = PlannerIn(
        tenant_id="test_planner",
        asset_url=asset_url,
        detections=None  # 금지 영역 없음
    )
    
    result = planner(body)
    proposals = result.get("proposals", [])
    avoid = result.get("avoid")
    
    print(f"✓ 제안 생성 완료: {len(proposals)}개 제안")
    for i, prop in enumerate(proposals):
        xywh = prop.get("xywh", [])
        source = prop.get("source", "unknown")
        print(f"  제안 {i+1}: {source} - xywh={xywh}")
    
    # 시각화
    print("\n[3/4] 제안 위치 시각화 중...")
    visualized = draw_proposals_on_image(test_image, proposals, avoid)
    
    # 시각화 결과 저장
    output_path = os.path.join(project_root, "test", "output", "planner_basic_proposals.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    visualized.save(output_path)
    print(f"✓ 시각화 결과 저장: {output_path}")
    
    # 결과 출력
    print("\n[4/4] 테스트 완료!")
    print(f"  - 제안 개수: {len(proposals)}")
    print(f"  - 금지 영역: {avoid}")
    print(f"  - 시각화 파일: {output_path}")
    
    return result


def load_yolo_results_from_files(output_dir: str, image_width: int, image_height: int, use_copy: bool = False):
    """
    기존 YOLO 결과 파일들을 읽어서 Planner가 사용할 수 있는 형식으로 변환
    
    Args:
        output_dir: YOLO 결과 파일들이 있는 디렉토리
        image_width: 이미지 너비 (bbox 변환용)
        image_height: 이미지 높이 (bbox 변환용)
        use_copy: True면 "detections copy.json" 사용, False면 "detections.json" 사용
    
    Returns:
        detections 딕셔너리 (Planner 형식)
    """
    detections = {
        "boxes": [],
        "labels": [],
        "confidences": [],
        "forbidden_mask_url": None,
        "detections": []
    }
    
    # detections.json 읽기 (우선순위: detections copy.json > detections.json)
    if use_copy:
        detections_json_path = os.path.join(output_dir, "detections copy.json")
        if not os.path.exists(detections_json_path):
            detections_json_path = os.path.join(output_dir, "detections.json")
    else:
        detections_json_path = os.path.join(output_dir, "detections.json")
        # detections.json이 없거나 비어있으면 copy 파일 시도
        if not os.path.exists(detections_json_path):
            detections_json_path = os.path.join(output_dir, "detections copy.json")
    
    if os.path.exists(detections_json_path):
        with open(detections_json_path, "r", encoding="utf-8") as f:
            detections_json = json.load(f)
        
        # normalized [x, y, width, height] → xyxy [x1, y1, x2, y2] (절대 좌표) 변환
        boxes = []
        labels = []
        confidences = []
        
        for det in detections_json:
            label = det.get("label", "unknown")
            confidence = det.get("confidence", 0.0)
            bbox = det.get("bbox", [0, 0, 0, 0])  # [x, y, width, height] normalized
            
            if len(bbox) == 4:
                x_norm, y_norm, w_norm, h_norm = bbox
                # normalized → 절대 좌표 변환
                x1 = x_norm * image_width
                y1 = y_norm * image_height
                x2 = (x_norm + w_norm) * image_width
                y2 = (y_norm + h_norm) * image_height
                
                boxes.append([x1, y1, x2, y2])
                labels.append(label)
                confidences.append(confidence)
        
        detections["boxes"] = boxes
        detections["labels"] = labels
        detections["confidences"] = confidences
        detections["detections"] = detections_json
    
    # forbidden_mask.png 읽기 및 URL 생성
    forbidden_mask_path = os.path.join(output_dir, "forbidden_mask.png")
    if os.path.exists(forbidden_mask_path):
        # 마스크를 asset으로 저장하여 URL 생성
        forbidden_mask = Image.open(forbidden_mask_path)
        mask_meta = save_asset("test_planner", "forbidden_mask", forbidden_mask, ".png")
        detections["forbidden_mask_url"] = mask_meta["url"]
    
    return detections


def test_planner_with_detections():
    """기존 YOLO 결과 파일을 사용한 Planner 테스트 (DB에서 가져오는 것과 유사한 플로우)"""
    
    print("=" * 60)
    print("Planner 테스트 (기존 YOLO 결과 파일 사용)")
    print("=" * 60)
    print("※ Planner는 YOLO를 실행하지 않고, 기존 YOLO 결과 파일을 읽어서 위치 제안")
    print("※ 나중에는 DB에서 가져올 예정")
    print("=" * 60)
    
    # 실제 이미지 사용 (YOLO 테스트에서 사용한 이미지)
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    output_dir = os.path.join(project_root, "test", "output")
    
    if not os.path.exists(image_path):
        print(f"⚠ 경고: 이미지를 찾을 수 없습니다: {image_path}")
        print("기본 테스트 이미지로 대체합니다.")
        test_image = Image.new("RGB", (800, 600), color="lightblue")
        asset_meta = save_asset("test_planner", "test_image", test_image, ".png")
        asset_url = asset_meta["url"]
    else:
        print(f"\n[1/6] 이미지 로드 중: {image_path}")
        test_image = Image.open(image_path)
        print(f"✓ 이미지 로드 완료: {test_image.size[0]}x{test_image.size[1]}")
        
        # 이미지 저장
        asset_meta = save_asset("test_planner", "test_image", test_image, ".png")
        asset_url = asset_meta["url"]
        print(f"✓ 이미지 저장 완료: {asset_url}")
    
    # [Step 1] 기존 YOLO 결과 파일 읽기 (나중에는 DB에서 가져옴)
    print("\n[2/6] 기존 YOLO 결과 파일 읽기 중...")
    print(f"  결과 디렉토리: {output_dir}")
    
    try:
        detections = load_yolo_results_from_files(
            output_dir=output_dir,
            image_width=test_image.width,
            image_height=test_image.height
        )
        
        print(f"✓ YOLO 결과 파일 읽기 완료:")
        print(f"  - detections.json: {len(detections['detections'])}개 감지 결과")
        print(f"  - 금지 객체: {len(detections['boxes'])}개")
        if detections.get("forbidden_mask_url"):
            print(f"  - 금지 영역 마스크 URL: {detections['forbidden_mask_url']}")
        
        if detections["boxes"]:
            print(f"  감지된 금지 객체:")
            for i, (box, label, conf) in enumerate(zip(detections["boxes"][:5], detections["labels"][:5], detections["confidences"][:5])):
                print(f"    {i+1}. {label} (신뢰도: {conf:.2f}) - bbox: {box}")
        else:
            print("  ⚠ 경고: 감지된 객체가 없습니다. detections.json을 확인하세요.")
        
    except Exception as e:
        print(f"⚠ YOLO 결과 파일 읽기 실패: {e}")
        print("더미 감지 결과 사용")
        import traceback
        traceback.print_exc()
        # 더미 감지 결과 (이미지 중앙에 금지 영역)
        w, h = test_image.size
        detections = {
            "boxes": [[w*0.3, h*0.3, w*0.7, h*0.7]],
            "labels": ["person"],
            "confidences": [0.9],
            "forbidden_mask_url": None,
            "detections": []
        }
    
    # [Step 2] Planner 호출 (YOLO 결과만 받아서 위치 제안)
    print("\n[3/6] Planner 위치 제안 생성 중 (YOLO 결과 사용)...")
    print("  ※ Planner는 YOLO를 실행하지 않고, YOLO 결과만 받아서 위치 제안")
    body = PlannerIn(
        tenant_id="test_planner",
        asset_url=asset_url,
        detections=detections  # YOLO 결과 전달 (나중에는 DB에서 가져온 데이터)
    )
    
    result = planner(body)
    proposals = result.get("proposals", [])
    avoid = result.get("avoid")
    
    print(f"✓ 제안 생성 완료: {len(proposals)}개 제안")
    for i, prop in enumerate(proposals):
        xywh = prop.get("xywh", [])
        source = prop.get("source", "unknown")
        print(f"  제안 {i+1}: {source} - xywh={xywh}")
    
    if avoid:
        print(f"  금지 영역: {avoid}")
    
    # 시각화
    print("\n[4/6] 제안 위치 시각화 중...")
    visualized = draw_proposals_on_image(test_image, proposals, avoid)
    
    # 시각화 결과 저장
    output_path = os.path.join(project_root, "test", "output", "planner_with_detections.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    visualized.save(output_path)
    print(f"✓ 시각화 결과 저장: {output_path}")
    
    # 결과 JSON 저장
    print("\n[5/6] 결과 JSON 저장 중...")
    json_path = os.path.join(project_root, "test", "output", "planner_result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✓ 결과 JSON 저장: {json_path}")
    
    # 플로우 요약
    print("\n[6/6] 플로우 요약:")
    print("  1. 기존 YOLO 결과 파일 읽기 (나중에는 DB에서 가져옴)")
    print("  2. Planner API 호출 → YOLO 결과를 받아서 위치 제안")
    print("  3. 결과 시각화 및 저장")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
    print(f"  - 제안 개수: {len(proposals)}")
    print(f"  - 금지 영역: {avoid}")
    print(f"  - 시각화 파일: {output_path}")
    print(f"  - 결과 JSON: {json_path}")
    
    return result


def test_planner_service_direct():
    """Planner 서비스를 직접 호출하는 테스트"""
    
    print("=" * 60)
    print("Planner 서비스 직접 테스트")
    print("=" * 60)
    
    from services.planner_service import propose_overlay_positions
    
    # 테스트 이미지 생성
    print("\n[1/3] 테스트 이미지 생성 중...")
    test_image = Image.new("RGB", (800, 600), color="lightblue")
    print(f"✓ 이미지 생성 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # 금지 영역 마스크 생성 (중앙에 금지 영역)
    print("\n[2/3] 금지 영역 마스크 생성 중...")
    import numpy as np
    mask_array = np.zeros((600, 800), dtype=np.uint8)
    # 중앙 영역을 금지 영역으로 설정
    mask_array[200:400, 250:550] = 255
    forbidden_mask = Image.fromarray(mask_array, mode="L")
    print("✓ 금지 영역 마스크 생성 완료 (중앙 영역)")
    
    # 더미 감지 결과
    detections = {
        "boxes": [[250, 200, 550, 400]],
        "labels": ["person"],
        "confidences": [0.9]
    }
    
    # Planner 서비스 직접 호출
    print("\n[3/3] Planner 서비스 호출 중...")
    result = propose_overlay_positions(
        image=test_image,
        detections=detections,
        forbidden_mask=forbidden_mask,
        min_overlay_width=0.5,
        min_overlay_height=0.12,
        max_proposals=5
    )
    
    proposals = result.get("proposals", [])
    avoid = result.get("avoid")
    
    print(f"✓ 제안 생성 완료: {len(proposals)}개 제안")
    for i, prop in enumerate(proposals):
        xywh = prop.get("xywh", [])
        source = prop.get("source", "unknown")
        print(f"  제안 {i+1}: {source} - xywh={xywh}")
    
    # 시각화
    visualized = draw_proposals_on_image(test_image, proposals, avoid)
    output_path = os.path.join(project_root, "test", "output", "planner_service_direct.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    visualized.save(output_path)
    print(f"✓ 시각화 결과 저장: {output_path}")
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Planner 위치 제안 테스트")
    parser.add_argument("--test", choices=["basic", "detections", "service", "all"], default="all",
                       help="테스트 모드: basic (기본), detections (YOLO 감지 포함), service (서비스 직접), all (모두)")
    args = parser.parse_args()
    
    try:
        if args.test == "basic" or args.test == "all":
            test_planner_basic()
            print("\n")
        
        if args.test == "detections" or args.test == "all":
            test_planner_with_detections()
            print("\n")
        
        if args.test == "service" or args.test == "all":
            test_planner_service_direct()
            print("\n")
        
        print("=" * 60)
        print("✓ 모든 테스트 완료!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


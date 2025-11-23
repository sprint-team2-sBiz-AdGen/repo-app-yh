"""Overlay 텍스트 삽입 테스트 스크립트"""
import sys
import os
import json
import argparse

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# ASSETS_DIR 환경 변수를 먼저 설정 (모듈 import 전에 설정해야 함)
ASSETS_DIR = os.getenv("ASSETS_DIR", "/opt/feedlyai/assets")
os.environ["ASSETS_DIR"] = ASSETS_DIR

# 환경 변수 설정 후 모듈 import
from PIL import Image, ImageDraw, ImageFont
from utils import abs_from_url, save_asset, parse_hex_rgba


def load_planner_result(json_path: str) -> dict:
    """
    planner_result.json 파일 읽기
    
    Args:
        json_path: planner_result.json 파일 경로
    
    Returns:
        planner 결과 딕셔너리
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"planner_result.json을 찾을 수 없습니다: {json_path}")
    
    with open(json_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    
    return result


def load_font(size: int, font_candidates: list = None) -> ImageFont.FreeTypeFont:
    """
    폰트 후보 리스트에서 사용 가능한 폰트 로드
    
    Args:
        size: 폰트 크기
        font_candidates: 폰트 경로 후보 리스트
    
    Returns:
        로드된 폰트 객체
    """
    if font_candidates is None:
        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold.ttf",
            "DejaVuSans.ttf",
        ]
    
    for path in font_candidates:
        try:
            font = ImageFont.truetype(path, size)
            return font
        except Exception:
            continue
    
    # 모든 폰트 로드 실패 시 기본 폰트 사용
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.Draw) -> str:
    """
    텍스트를 주어진 너비에 맞게 여러 줄로 나누기 (overlay_copy.py 방식)
    
    Args:
        text: 원본 텍스트
        font: 폰트 객체
        max_width: 최대 너비 (픽셀)
        draw: ImageDraw 객체
    
    Returns:
        줄바꿈이 포함된 텍스트 문자열
    """
    words = text.split()
    if not words:
        return text
    
    lines = []
    current = []
    
    for word in words:
        test_line = " ".join(current + [word]) if current else word
        
        # 텍스트 너비 측정
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            try:
                width, _ = draw.textsize(test_line, font=font)
            except:
                width = len(test_line) * font.size // 2
        
        if width <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    
    if current:
        lines.append(" ".join(current))
    
    return "\n".join(lines) if lines else text


def overlay_text_on_image(
    image: Image.Image,
    proposal: dict,
    text: str,
    padding_ratio: float = 0.08,
    line_spacing: int = 6,
    min_font_size: int = 12,
    max_font_size: int = 96
) -> Image.Image:
    """
    이미지에 텍스트 오버레이 적용 (overlay_copy.py 방식 개선)
    
    Args:
        image: 원본 이미지 (PIL Image)
        proposal: 제안 정보 {"xywh": [x, y, w, h], "color": hex, "size": int, ...}
        text: 오버레이할 텍스트
        padding_ratio: 패딩 비율 (0-1)
        line_spacing: 줄 간격 (픽셀)
        min_font_size: 최소 폰트 크기
        max_font_size: 최대 폰트 크기
    
    Returns:
        텍스트가 오버레이된 이미지
    """
    # 이미지를 RGBA로 변환
    if image.mode != "RGBA":
        im = image.convert("RGBA")
    else:
        im = image.copy()
    
    w, h = im.size
    
    # proposal의 정규화된 좌표를 픽셀 좌표로 변환
    xywh = proposal.get("xywh", [0, 0, 0.8, 0.18])
    x_norm, y_norm, width_norm, height_norm = xywh
    
    x_px = int(x_norm * w)
    y_px = int(y_norm * h)
    width_px = int(width_norm * w)
    height_px = int(height_norm * h)
    
    # bbox 형식으로 변환 [x0, y0, x1, y1]
    bbox = [x_px, y_px, x_px + width_px, y_px + height_px]
    
    # 패딩 적용 (overlay_copy.py의 _apply_padding 방식)
    pad_x = int((bbox[2] - bbox[0]) * padding_ratio)
    pad_y = int((bbox[3] - bbox[1]) * padding_ratio)
    padded_bbox = [
        max(0, bbox[0] + pad_x),
        max(0, bbox[1] + pad_y),
        min(w, bbox[2] - pad_x),
        min(h, bbox[3] - pad_y)
    ]
    
    # 사용 가능한 영역 계산
    available_width = padded_bbox[2] - padded_bbox[0]
    available_height = padded_bbox[3] - padded_bbox[1]
    
    # 텍스트 색상 파싱
    text_color_hex = proposal.get("color", "ffffffff")
    text_color = parse_hex_rgba(text_color_hex, (255, 255, 255, 255))
    
    # 텍스트 크기 (초기값)
    text_size = proposal.get("size", 32)
    max_size = min(max_font_size, text_size * 3)
    min_size = max(min_font_size, 12)
    
    # 텍스트 그리기 준비
    draw = ImageDraw.Draw(im)
    
    # 폰트 크기를 반복적으로 조정하여 영역에 맞게 최적화 (overlay_copy.py 방식)
    optimal_font = None
    optimal_wrapped_text = None
    
    # 큰 크기부터 시작해서 점점 줄여가며 최적 크기 찾기 (2씩 감소)
    for test_size in range(max_size, min_size - 1, -2):
        # 폰트 로드 (여러 후보 시도)
        test_font = load_font(test_size)
        
        # 텍스트를 여러 줄로 나누기
        wrapped = wrap_text(text, test_font, available_width, draw)
        
        # multiline_textbbox를 사용하여 정확한 크기 계산
        try:
            text_bbox = draw.multiline_textbbox(
                (0, 0),
                wrapped,
                font=test_font,
                spacing=line_spacing,
                align="center"
            )
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except:
            # multiline_textbbox가 없는 경우 fallback
            try:
                # 각 줄의 크기를 개별적으로 계산
                lines = wrapped.split("\n")
                text_width = 0
                text_height = 0
                for line in lines:
                    try:
                        bbox = draw.textbbox((0, 0), line, font=test_font)
                        line_w = bbox[2] - bbox[0]
                        line_h = bbox[3] - bbox[1]
                    except:
                        try:
                            line_w, line_h = draw.textsize(line, font=test_font)
                        except:
                            line_w = len(line) * test_size // 2
                            line_h = test_size
                    text_width = max(text_width, line_w)
                    text_height += line_h
                text_height += line_spacing * (len(lines) - 1)
            except:
                # 최후의 수단
                text_width = available_width
                text_height = available_height
        
        # 영역에 맞는지 확인
        if text_width <= available_width and text_height <= available_height:
            optimal_font = test_font
            optimal_wrapped_text = wrapped
            break
    
    # 최적 폰트가 없으면 최소 크기로 폴백
    if optimal_font is None:
        optimal_font = load_font(min_size)
        optimal_wrapped_text = wrap_text(text, optimal_font, available_width, draw)
    
    # 중앙 좌표 계산
    x_center = (padded_bbox[0] + padded_bbox[2]) / 2
    y_center = (padded_bbox[1] + padded_bbox[3]) / 2
    
    # multiline_text를 사용하여 텍스트 그리기 (anchor="mm"로 중앙 정렬)
    try:
        draw.multiline_text(
            (x_center, y_center),
            optimal_wrapped_text,
            font=optimal_font,
            fill=text_color,
            anchor="mm",  # 중앙 정렬
            align="center",
            spacing=line_spacing
        )
    except:
        # anchor를 지원하지 않는 경우 fallback
        # 텍스트 크기 계산
        try:
            text_bbox = draw.multiline_textbbox(
                (0, 0),
                optimal_wrapped_text,
                font=optimal_font,
                spacing=line_spacing,
                align="center"
            )
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
        except:
            text_width = available_width
            text_height = available_height
        
        # 수동으로 중앙 정렬
        text_x = x_center - text_width / 2
        text_y = y_center - text_height / 2
        
        draw.multiline_text(
            (text_x, text_y),
            optimal_wrapped_text,
            font=optimal_font,
            fill=text_color,
            align="center",
            spacing=line_spacing
        )
    
    return im


def test_overlay_single():
    """단일 proposal에 텍스트 오버레이 테스트"""
    
    print("=" * 60)
    print("Overlay 텍스트 삽입 테스트 (단일)")
    print("=" * 60)
    
    # planner_result.json 읽기
    output_dir = os.path.join(project_root, "test", "output")
    json_path = os.path.join(output_dir, "planner_result.json")
    
    print(f"\n[1/4] planner_result.json 읽기 중...")
    print(f"  경로: {json_path}")
    
    try:
        planner_result = load_planner_result(json_path)
        proposals = planner_result.get("proposals", [])
        print(f"✓ 제안 개수: {len(proposals)}")
    except FileNotFoundError as e:
        print(f"❌ 오류: {e}")
        print("먼저 test_planner.py를 실행하여 planner_result.json을 생성해주세요.")
        sys.exit(1)
    
    if not proposals:
        print("❌ 오류: 제안이 없습니다.")
        sys.exit(1)
    
    # 원본 이미지 로드
    print(f"\n[2/4] 원본 이미지 로드 중...")
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    
    if not os.path.exists(image_path):
        print(f"⚠ 경고: 이미지를 찾을 수 없습니다: {image_path}")
        print("기본 테스트 이미지로 대체합니다.")
        test_image = Image.new("RGB", (800, 600), color="lightblue")
    else:
        test_image = Image.open(image_path)
        print(f"✓ 이미지 로드 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # 광고 문구
    ad_copy = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    
    # 첫 번째 proposal에 텍스트 오버레이
    print(f"\n[3/4] 텍스트 오버레이 적용 중...")
    print(f"  제안: {proposals[0].get('source', 'unknown')}")
    print(f"  위치: {proposals[0].get('xywh', [])}")
    print(f"  텍스트: {ad_copy}")
    
    result_image = overlay_text_on_image(test_image, proposals[0], ad_copy)
    
    # 결과 저장
    print(f"\n[4/4] 결과 저장 중...")
    output_path = os.path.join(output_dir, "overlay_single.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_image.convert("RGB").save(output_path)
    print(f"✓ 결과 저장: {output_path}")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
    print(f"  - 사용된 제안: {proposals[0].get('source', 'unknown')}")
    print(f"  - 결과 파일: {output_path}")
    
    return result_image


def test_overlay_all():
    """모든 proposal에 텍스트 오버레이 테스트 (각각 별도 이미지)"""
    
    print("=" * 60)
    print("Overlay 텍스트 삽입 테스트 (모든 제안)")
    print("=" * 60)
    
    # planner_result.json 읽기
    output_dir = os.path.join(project_root, "test", "output")
    json_path = os.path.join(output_dir, "planner_result.json")
    
    print(f"\n[1/4] planner_result.json 읽기 중...")
    print(f"  경로: {json_path}")
    
    try:
        planner_result = load_planner_result(json_path)
        proposals = planner_result.get("proposals", [])
        print(f"✓ 제안 개수: {len(proposals)}")
    except FileNotFoundError as e:
        print(f"❌ 오류: {e}")
        print("먼저 test_planner.py를 실행하여 planner_result.json을 생성해주세요.")
        sys.exit(1)
    
    if not proposals:
        print("❌ 오류: 제안이 없습니다.")
        sys.exit(1)
    
    # 원본 이미지 로드
    print(f"\n[2/4] 원본 이미지 로드 중...")
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    
    if not os.path.exists(image_path):
        print(f"⚠ 경고: 이미지를 찾을 수 없습니다: {image_path}")
        print("기본 테스트 이미지로 대체합니다.")
        test_image = Image.new("RGB", (800, 600), color="lightblue")
    else:
        test_image = Image.open(image_path)
        print(f"✓ 이미지 로드 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # 광고 문구
    ad_copy = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    
    # 각 proposal에 텍스트 오버레이
    print(f"\n[3/4] 텍스트 오버레이 적용 중...")
    print(f"  총 {len(proposals)}개 제안에 텍스트 오버레이")
    
    results = []
    for i, proposal in enumerate(proposals):
        source = proposal.get("source", "unknown")
        print(f"  [{i+1}/{len(proposals)}] {source}...")
        
        result_image = overlay_text_on_image(test_image.copy(), proposal, ad_copy)
        results.append((i, proposal, result_image))
    
    # 결과 저장
    print(f"\n[4/4] 결과 저장 중...")
    for i, proposal, result_image in results:
        source = proposal.get("source", "unknown")
        proposal_id = proposal.get("proposal_id", "")[:8]
        output_path = os.path.join(output_dir, f"overlay_{i+1:02d}_{source}_{proposal_id}.png")
        result_image.convert("RGB").save(output_path)
        print(f"  ✓ [{i+1}/{len(proposals)}] {output_path}")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
    print(f"  - 처리된 제안: {len(proposals)}개")
    print(f"  - 결과 파일: {output_dir}/overlay_*.png")
    
    return results


def test_overlay_combined():
    """모든 proposal에 텍스트 오버레이 테스트 (하나의 이미지에 모두 표시)"""
    
    print("=" * 60)
    print("Overlay 텍스트 삽입 테스트 (통합)")
    print("=" * 60)
    
    # planner_result.json 읽기
    output_dir = os.path.join(project_root, "test", "output")
    json_path = os.path.join(output_dir, "planner_result.json")
    
    print(f"\n[1/4] planner_result.json 읽기 중...")
    print(f"  경로: {json_path}")
    
    try:
        planner_result = load_planner_result(json_path)
        proposals = planner_result.get("proposals", [])
        print(f"✓ 제안 개수: {len(proposals)}")
    except FileNotFoundError as e:
        print(f"❌ 오류: {e}")
        print("먼저 test_planner.py를 실행하여 planner_result.json을 생성해주세요.")
        sys.exit(1)
    
    if not proposals:
        print("❌ 오류: 제안이 없습니다.")
        sys.exit(1)
    
    # 원본 이미지 로드
    print(f"\n[2/4] 원본 이미지 로드 중...")
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    
    if not os.path.exists(image_path):
        print(f"⚠ 경고: 이미지를 찾을 수 없습니다: {image_path}")
        print("기본 테스트 이미지로 대체합니다.")
        test_image = Image.new("RGB", (800, 600), color="lightblue")
    else:
        test_image = Image.open(image_path)
        print(f"✓ 이미지 로드 완료: {test_image.size[0]}x{test_image.size[1]}")
    
    # 광고 문구
    ad_copy = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    
    # 모든 proposal에 텍스트 오버레이 (하나의 이미지에)
    print(f"\n[3/4] 텍스트 오버레이 적용 중...")
    print(f"  총 {len(proposals)}개 제안에 텍스트 오버레이 (통합)")
    
    result_image = test_image.copy()
    for i, proposal in enumerate(proposals):
        source = proposal.get("source", "unknown")
        print(f"  [{i+1}/{len(proposals)}] {source}...")
        result_image = overlay_text_on_image(result_image, proposal, ad_copy)
    
    # 결과 저장
    print(f"\n[4/4] 결과 저장 중...")
    output_path = os.path.join(output_dir, "overlay_combined.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_image.convert("RGB").save(output_path)
    print(f"✓ 결과 저장: {output_path}")
    
    print("\n" + "=" * 60)
    print("테스트 완료!")
    print("=" * 60)
    print(f"  - 처리된 제안: {len(proposals)}개")
    print(f"  - 결과 파일: {output_path}")
    
    return result_image


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Overlay 텍스트 삽입 테스트")
    parser.add_argument(
        "--test",
        choices=["single", "all", "combined"],
        default="single",
        help="테스트 모드: single (첫 번째 제안만), all (모든 제안 각각), combined (모든 제안 통합)"
    )
    
    args = parser.parse_args()
    
    if args.test == "single":
        test_overlay_single()
    elif args.test == "all":
        test_overlay_all()
    elif args.test == "combined":
        test_overlay_combined()
    else:
        print(f"❌ 알 수 없는 테스트 모드: {args.test}")
        sys.exit(1)


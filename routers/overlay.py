
"""Overlay 라우터"""
########################################################
# TODO: Implement the actual overlay logic
#       - Apply the text overlay to the image
#       - Return the overlay image
#       - Return the overlay image URL
#       - Return the overlay image metadata
#       - Return the overlay image size
#       - Return the overlay image format
#       - Return the overlay image quality
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Overlay logic
# version: 0.1.0
# status: development
# tags: overlay
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from PIL import Image, ImageDraw, ImageFont
from models import OverlayIn
from utils import abs_from_url, save_asset, parse_hex_rgba

router = APIRouter(prefix="/api/yh/overlay", tags=["overlay"])


@router.post("")
def overlay(body: OverlayIn):
    """이미지에 텍스트 오버레이 적용"""
    im = Image.open(abs_from_url(body.variant_asset_url)).convert("RGBA")
    w, h = im.size
    # default proposal region
    x, y, pw, ph = (int(w * 0.1), int(h * 0.05), int(w * 0.8), int(h * 0.18))
    # overlay rect
    ol_color = parse_hex_rgba(body.overlay_color, (0, 0, 0, 0))
    if ol_color[3] > 0:
        over = Image.new("RGBA", (pw, ph), ol_color)
        im.alpha_composite(over, dest=(x, y))
    # draw text
    draw = ImageDraw.Draw(im)
    # font: default Pillow
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", body.text_size)
    except:
        font = ImageFont.load_default()
    tw, th = draw.textsize(body.text, font=font)
    # alignment
    if body.x_align == "left":
        tx = x + 10
    elif body.x_align == "right":
        tx = x + pw - tw - 10
    else:
        tx = x + (pw - tw) // 2
    if body.y_align == "top":
        ty = y + 10
    elif body.y_align == "bottom":
        ty = y + ph - th - 10
    else:
        ty = y + (ph - th) // 2
    tc = parse_hex_rgba(body.text_color, (255, 255, 255, 255))
    draw.text((tx, ty), body.text, fill=tc, font=font)

    meta = save_asset(body.tenant_id, "final", im, ".png")
    return {"render": meta}


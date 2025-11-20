
"""유틸리티 함수"""
########################################################
# TODO: Implement the actual utility functions
#       - abs_from_url
#       - save_asset
#       - parse_hex_rgba
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Utility functions
# version: 0.1.0
# status: development
# tags: utility
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
import uuid
import datetime
from typing import Optional, Tuple
from fastapi import HTTPException
from PIL import Image
from config import ASSETS_DIR, PART_NAME


def abs_from_url(url: str) -> str:
    """asset URL을 절대 경로로 변환"""
    if not url.startswith("/assets/"):
        raise HTTPException(400, "asset_url must start with /assets/")
    return os.path.join(ASSETS_DIR, url[len("/assets/"):])


def save_asset(tenant_id: str, kind: str, image: Image.Image, ext=".png") -> dict:
    """이미지를 저장하고 메타데이터 반환"""
    today = datetime.datetime.utcnow()
    # 파트별 폴더 구조: {PART_NAME}/tenants/{tenant_id}/{kind}/{year}/{month}/{day}
    rel_dir = f"{PART_NAME}/tenants/{tenant_id}/{kind}/{today.year}/{today.month:02d}/{today.day:02d}"
    abs_dir = os.path.join(ASSETS_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    asset_id = str(uuid.uuid4())
    rel_path = f"{rel_dir}/{asset_id}{ext}"
    abs_path = os.path.join(ASSETS_DIR, rel_path)
    image.save(abs_path)
    return {"asset_id": asset_id, "url": f"/assets/{rel_path}", "width": image.width, "height": image.height}


def parse_hex_rgba(s: Optional[str], default: Tuple[int, int, int, int] = (0, 0, 0, 0)) -> Tuple[int, int, int, int]:
    """16진수 RGBA 문자열을 튜플로 변환"""
    if not s:
        return default
    s = s.strip().lstrip("#")
    if len(s) == 8:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = int(s[6:8], 16)
        return (r, g, b, a)
    if len(s) == 6:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        a = 255
        return (r, g, b, a)
    return default


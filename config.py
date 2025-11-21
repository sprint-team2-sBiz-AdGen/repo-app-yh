
"""설정 및 환경 변수 관리"""
########################################################
# TODO: Implement the actual configuration logic
#       - ASSETS_DIR
#       - PART_NAME
#       - PORT
#       - HOST
#       - DB_HOST
#       - DB_PORT
#       - DB_NAME
#       - DB_USER
#       - DB_PASSWORD
#       - DATABASE_URL
#       - PART_ASSETS_DIR
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Configuration logic
# version: 0.1.0
# status: development
# tags: configuration
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
ASSETS_DIR = os.getenv("ASSETS_DIR", "/var/www/assets")
PART_NAME = os.getenv("PART_NAME", "yh")  # 파트 이름 (ye, yh, js, sh)
PORT = int(os.getenv("PORT", "8011"))
HOST = os.getenv("HOST", "127.0.0.1")  # 로컬 개발 시 localhost만, Docker에서는 0.0.0.0

# Docker 환경에서는 'postgres' 호스트명 사용, 로컬에서는 'localhost'
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "feedlyai")
DB_USER = os.getenv("DB_USER", "feedlyai")
DB_PASSWORD = os.getenv("DB_PASSWORD", "feedlyai_dev_password_74154")

# DATABASE_URL이 명시적으로 설정되지 않았거나 빈 문자열이면 자동 구성
DATABASE_URL = os.getenv("DATABASE_URL") or f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 파트별 assets 디렉토리
PART_ASSETS_DIR = os.path.join(ASSETS_DIR, PART_NAME)

# LLaVa 모델 설정
LLAVA_MODEL_NAME = os.getenv("LLAVA_MODEL_NAME", "llava-hf/llava-1.5-7b-hf")
DEVICE_TYPE = os.getenv("DEVICE_TYPE", "cuda")  # cuda 또는 cpu

# 양자화 설정 (8-bit 양자화 사용 여부)
# 환경변수 USE_QUANTIZATION을 설정하여 제어 가능
# "true", "1", "yes", "on" 등의 문자열이면 양자화 사용, 그 외는 사용 안 함
# 기본값: true (양자화 사용)
USE_QUANTIZATION = os.getenv("USE_QUANTIZATION", "true").lower() in ("true", "1", "yes", "on")

# 모델 저장 디렉토리 (프로젝트 루트의 model 폴더)
# config.py가 프로젝트 루트에 있으므로 현재 파일의 디렉토리를 기준으로 설정
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model")
os.makedirs(MODEL_DIR, exist_ok=True)

# YOLO 모델 설정
YOLO_MODEL_NAME = os.getenv("YOLO_MODEL_NAME", "yolov8x-seg.pt")
YOLO_CONF_THRESHOLD = float(os.getenv("YOLO_CONF_THRESHOLD", "0.25"))
YOLO_IOU_THRESHOLD = float(os.getenv("YOLO_IOU_THRESHOLD", "0.45"))

# YOLO 금지 라벨 설정 (쉼표로 구분된 문자열 또는 JSON 배열)
# 환경 변수가 없으면 기본 금지 라벨 리스트 사용
YOLO_FORBIDDEN_LABELS_ENV = os.getenv("YOLO_FORBIDDEN_LABELS", None)
if YOLO_FORBIDDEN_LABELS_ENV:
    import json
    try:
        # JSON 배열 형식 시도
        YOLO_FORBIDDEN_LABELS = json.loads(YOLO_FORBIDDEN_LABELS_ENV)
    except json.JSONDecodeError:
        # 쉼표로 구분된 문자열 형식
        YOLO_FORBIDDEN_LABELS = [label.strip() for label in YOLO_FORBIDDEN_LABELS_ENV.split(",") if label.strip()]
else:
    # 기본값: None (서비스에서 기본 리스트 사용)
    YOLO_FORBIDDEN_LABELS = None


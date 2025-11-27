
"""FastAPI 애플리케이션 메인 진입점"""
########################################################
# TODO: Implement the actual main application logic
#       - FastAPI app
#       - Middleware
#       - Routers
#       - Metrics endpoint
########################################################
# created_at: 2025-11-13
# updated_at: 2025-11-24
# author: LEEYH205
# description: Main application logic
# version: 0.1.0
# status: development
# tags: main
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
import subprocess
import logging
from fastapi import FastAPI
from config import PART_NAME, HOST, PORT
from middleware import metrics_middleware, metrics_endpoint
from routers import (
    yolo, planner, overlay, evals, llava_stage1, llava_stage2, health,
    gpt, refined_ad_copy, ocr_eval, readability_eval, iou_eval, instagram_feed
)

logger = logging.getLogger(__name__)

# 애플리케이션 시작 시 폰트 설치 확인
def check_and_install_fonts():
    """폰트 설치 확인 및 설치"""
    try:
        # 폰트 설치 스크립트 실행
        result = subprocess.run(
            ["/usr/local/bin/install_fonts.sh"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            logger.info("✓ 폰트 설치 확인 완료")
            if result.stdout:
                logger.info(f"폰트 설치 로그:\n{result.stdout}")
        else:
            logger.warning(f"⚠️ 폰트 설치 스크립트 실행 중 경고: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error("❌ 폰트 설치 스크립트 실행 시간 초과")
    except Exception as e:
        logger.error(f"❌ 폰트 설치 확인 중 오류: {e}")

# 애플리케이션 시작 시 폰트 확인
check_and_install_fonts()

# root_path는 리버스 프록시(nginx) 뒤에서만 필요
# 직접 접근 시에는 None으로 설정하여 /docs가 정상 작동하도록 함
ROOT_PATH = os.getenv("ROOT_PATH", None)
if ROOT_PATH is None and PART_NAME == "yh":
    # 환경 변수가 없으면 기본적으로 None (직접 접근 모드)
    # nginx 뒤에서 실행할 때는 ROOT_PATH=/api/yh 환경 변수 설정
    ROOT_PATH = None

app = FastAPI(
    title=f"app-{PART_NAME} (Planner/Overlay/Eval)",
    root_path=ROOT_PATH
)

# 미들웨어 등록
app.middleware("http")(metrics_middleware)

# 라우터 등록
app.include_router(yolo.router)
app.include_router(planner.router)
app.include_router(overlay.router)
app.include_router(evals.router)
app.include_router(llava_stage1.router)
app.include_router(llava_stage2.router)
app.include_router(ocr_eval.router)
app.include_router(readability_eval.router)
app.include_router(iou_eval.router)
app.include_router(gpt.router)
app.include_router(refined_ad_copy.router)
app.include_router(instagram_feed.router)
app.include_router(health.router)

# 메트릭 엔드포인트
app.get("/metrics")(metrics_endpoint)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)

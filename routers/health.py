
"""Health check 라우터"""
########################################################
# TODO: Implement the actual health check logic
#       - DB connection test
#       - Model connection test
#       - Asset connection test
#       - API connection test
#       - Service connection test
#       - etc.
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Health check logic
# version: 0.1.0
# status: development
# tags: health
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from config import PART_NAME

router = APIRouter(tags=["health"])


@router.get("/healthz")
def health(db: Session = Depends(get_db)):
    """헬스 체크 엔드포인트 (DB 연결 테스트 포함)"""
    # DB 연결 테스트
    db.execute(text("SELECT 1"))
    return {"ok": True, "service": f"app-{PART_NAME}"}


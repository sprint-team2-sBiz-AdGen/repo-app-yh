
"""Overlay Layouts 조회 라우터"""
########################################################
# TODO: Implement the actual overlay layouts logic
#       - Get overlay layouts from the database
#       - Return the overlay layouts
#       - Return the total number of overlay layouts
#       - Return the limit and offset
#       - Return the proposal_id
#       - Return the overlay_id
#       - Return the layout
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Overlay layouts logic
# version: 0.1.0
# status: development
# tags: overlay-layouts
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db, OverlayLayout

router = APIRouter(prefix="/api/yh/overlay-layouts", tags=["overlay-layouts"])


@router.get("")
def get_overlay_layouts(
    limit: int = 10,
    offset: int = 0,
    proposal_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """overlay_layouts 테이블 조회"""
    query = db.query(OverlayLayout)
    
    # proposal_id 필터링 (선택사항)
    if proposal_id:
        query = query.filter(OverlayLayout.proposal_id == proposal_id)
    
    # 전체 개수
    total = query.count()
    
    # 페이지네이션
    layouts = query.order_by(OverlayLayout.created_at.desc()).offset(offset).limit(limit).all()
    
    # 결과 변환
    results = []
    for layout in layouts:
        results.append({
            "overlay_id": str(layout.overlay_id),
            "proposal_id": str(layout.proposal_id) if layout.proposal_id else None,
            "layout": layout.layout,
            "x_ratio": layout.x_ratio,
            "y_ratio": layout.y_ratio,
            "width_ratio": layout.width_ratio,
            "height_ratio": layout.height_ratio,
            "text_margin": layout.text_margin,
            "created_at": layout.created_at.isoformat() if layout.created_at else None,
            "updated_at": layout.updated_at.isoformat() if layout.updated_at else None
        })
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": results
    }


@router.get("/{overlay_id}")
def get_overlay_layout(overlay_id: str, db: Session = Depends(get_db)):
    """특정 overlay_layout 조회"""
    layout = db.query(OverlayLayout).filter(OverlayLayout.overlay_id == overlay_id).first()
    
    if not layout:
        raise HTTPException(status_code=404, detail="Overlay layout not found")
    
    return {
        "overlay_id": str(layout.overlay_id),
        "proposal_id": str(layout.proposal_id) if layout.proposal_id else None,
        "layout": layout.layout,
        "x_ratio": layout.x_ratio,
        "y_ratio": layout.y_ratio,
        "width_ratio": layout.width_ratio,
        "height_ratio": layout.height_ratio,
        "text_margin": layout.text_margin,
        "created_at": layout.created_at.isoformat() if layout.created_at else None,
        "updated_at": layout.updated_at.isoformat() if layout.updated_at else None
    }


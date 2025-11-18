
import os, uuid, datetime, math, json
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB

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

app = FastAPI(title="app-yh (Planner/Overlay/Eval)")

# 파트별 assets 디렉토리
PART_ASSETS_DIR = os.path.join(ASSETS_DIR, PART_NAME)

# 데이터베이스 연결
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# OverlayLayout 모델
class OverlayLayout(Base):
    __tablename__ = "overlay_layouts"
    
    overlay_id = Column(UUID(as_uuid=True), primary_key=True)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey("planner_proposals.proposal_id"))
    layout = Column(JSONB)
    x_ratio = Column(Float)
    y_ratio = Column(Float)
    width_ratio = Column(Float)
    height_ratio = Column(Float)
    text_margin = Column(String(50))
    uid = Column(String(255))
    pk = Column(Integer)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

# DB 세션 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def abs_from_url(url: str) -> str:
    if not url.startswith("/assets/"):
        raise HTTPException(400, "asset_url must start with /assets/")
    return os.path.join(ASSETS_DIR, url[len("/assets/"):])

def save_asset(tenant_id: str, kind: str, image: Image.Image, ext=".png") -> dict:
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

# -------- YOLO (stub) --------
class DetectIn(BaseModel):
    tenant_id: str
    asset_url: str
    model: Optional[str] = "forbidden"

@app.post("/api/yh/yolo/detect")
def detect(body: DetectIn):
    # stub: forbid center square 30%
    from PIL import Image
    im = Image.open(abs_from_url(body.asset_url))
    w,h = im.size
    cx,cy = w*0.5,h*0.5
    bw,bh = w*0.3,h*0.3
    box = [cx-bw/2, cy-bh/2, cx+bw/2, cy+bh/2]  # xyxy
    return {"boxes":[box], "model": body.model}

# -------- Planner --------
class PlannerIn(BaseModel):
    tenant_id: str
    asset_url: str
    detections: Optional[dict] = None

@app.post("/api/yh/planner")
def planner(body: PlannerIn):
    from PIL import Image
    im = Image.open(abs_from_url(body.asset_url))
    w,h = im.size
    # very simple: propose top banner area avoiding center box if provided
    avoid = None
    if body.detections and body.detections.get("boxes"):
        bx = body.detections["boxes"][0]
        avoid = [bx[0]/w, bx[1]/h, (bx[2]-bx[0])/w, (bx[3]-bx[1])/h]  # xywh normalized
    # proposal: top area 80% width, 18% height
    proposal = {"proposal_id": str(uuid.uuid4()), "xywh":[0.1, 0.05, 0.8, 0.18], "color":"0d0d0dff", "size":32, "source":"rule"}
    return {"proposals":[proposal], "avoid": avoid}

# -------- Overlay --------
class OverlayIn(BaseModel):
    tenant_id: str
    variant_asset_url: str
    proposal_id: Optional[str] = None
    text: str
    x_align: str = "center"
    y_align: str = "top"
    text_size: int = 32
    overlay_color: Optional[str] = None  # "00000080"
    text_color: Optional[str] = "ffffffff"
    margin: Optional[str] = "8px"

def parse_hex_rgba(s: Optional[str], default=(0,0,0,0)):
    if not s: return default
    s = s.strip().lstrip("#")
    if len(s)==8:
        r = int(s[0:2],16); g=int(s[2:4],16); b=int(s[4:6],16); a=int(s[6:8],16)
        return (r,g,b,a)
    if len(s)==6:
        r = int(s[0:2],16); g=int(s[2:4],16); b=int(s[4:6],16); a=255
        return (r,g,b,a)
    return default

@app.post("/api/yh/overlay")
def overlay(body: OverlayIn):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(abs_from_url(body.variant_asset_url)).convert("RGBA")
    w,h = im.size
    # default proposal region
    x,y,pw,ph = (int(w*0.1), int(h*0.05), int(w*0.8), int(h*0.18))
    # overlay rect
    ol_color = parse_hex_rgba(body.overlay_color, (0,0,0,0))
    if ol_color[3] > 0:
        over = Image.new("RGBA", (pw,ph), ol_color)
        im.alpha_composite(over, dest=(x,y))
    # draw text
    draw = ImageDraw.Draw(im)
    # font: default Pillow
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", body.text_size)
    except:
        font = ImageFont.load_default()
    tw,th = draw.textsize(body.text, font=font)
    # alignment
    if body.x_align=="left": tx = x + 10
    elif body.x_align=="right": tx = x + pw - tw - 10
    else: tx = x + (pw - tw)//2
    if body.y_align=="top": ty = y + 10
    elif body.y_align=="bottom": ty = y + ph - th - 10
    else: ty = y + (ph - th)//2
    tc = parse_hex_rgba(body.text_color, (255,255,255,255))
    draw.text((tx,ty), body.text, fill=tc, font=font)

    meta = save_asset(body.tenant_id, "final", im, ".png")
    return {"render": meta}

# -------- Evals --------
class EvalIn(BaseModel):
    tenant_id: str
    render_asset_url: str

@app.post("/api/yh/evals")
def evals(body: EvalIn):
    # mock metrics for wiring
    return {"ocr_conf": 0.90, "text_ratio": 0.12, "clip_score": 0.33, "iou_forbidden": 0.0, "gate_pass": True}

class JudgeIn(BaseModel):
    tenant_id: str
    render_asset_url: str

@app.post("/api/yh/llava/judge")
def judge(body: JudgeIn):
    return {"on_brief": True, "occlusion": False, "contrast_ok": True, "cta_present": True, "issues":[]}

@app.get("/healthz")
def health(db: Session = Depends(get_db)):
    # DB 연결 테스트
    db.execute(text("SELECT 1"))
    return {"ok": True, "service": f"app-{PART_NAME}"}

# -------- Database 조회 --------
@app.get("/api/yh/overlay-layouts")
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

@app.get("/api/yh/overlay-layouts/{overlay_id}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)


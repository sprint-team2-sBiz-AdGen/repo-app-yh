"""폰트 설정 및 매핑"""
########################################################
# Font Configuration and Mapping
# - 폰트 스타일별 경로 매핑
# - 폰트 이름별 경로 매핑
# - LLaVA 프롬프트용 폰트 리스트
########################################################
# created_at: 2025-11-25
# updated_at: 2025-11-25
# author: LEEYH205
# description: Font configuration for overlay and LLaVA recommendation
# version: 1.0.0
# status: production
# tags: font, configuration
# dependencies: None
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

# 폰트 스타일별 경로 매핑 (fallback용, 우선순위 없음 - LLaVA 추천 폰트를 직접 사용)
FONT_STYLE_MAP = {
    "serif": [
        # 한글 serif 폰트 없음 - serif는 기본 DejaVu만 사용 (fallback)
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    ],
    "sans-serif": [
        # Pass 폴더의 폰트만 사용 (fallback용, 우선순위 없음 - LLaVA가 font_name 추천해야 함)
        "/usr/share/fonts/truetype/custom/GmarketSansTTFMedium.ttf",
        "/usr/share/fonts/truetype/custom/BMDOHYEON_ttf.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        # Cafe24 폰트 (Pass: Classictype, Danjunghae, Ssurround)
        "/usr/share/fonts/truetype/custom/test2/Cafe24Classictype-v1.1.ttf",
        "/usr/share/fonts/truetype/custom/test2/Cafe24Danjunghae-v2.0.ttf",
        "/usr/share/fonts/truetype/custom/test2/Cafe24Ssurround-v2.0.ttf",
        # Jalnan 폰트 (Pass: Jalnan, Jalnan Gothic)
        "/usr/share/fonts/truetype/custom/test2/Jalnan2TTF.ttf",
        "/usr/share/fonts/truetype/custom/test2/JalnanGothicTTF.ttf",
        # DdangFonts (Pass: Light, Medium)
        "/usr/share/fonts/truetype/custom/test2/DdangFontsMedium.ttf",
        "/usr/share/fonts/truetype/custom/test2/DdangFontsLight.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ],
    "bold": [
        # Pass 폴더의 폰트만 사용 (fallback용, 우선순위 없음 - LLaVA가 font_name 추천해야 함)
        "/usr/share/fonts/truetype/custom/PretendardGOV-Bold.ttf",
        "/usr/share/fonts/truetype/custom/GmarketSansTTFBold.ttf",
        "/usr/share/fonts/truetype/custom/BMEuljiro10yearslater.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        # Cafe24 Bold (Pass: Supermagic)
        "/usr/share/fonts/truetype/custom/test2/Cafe24Supermagic-Bold-v1.0.ttf",
        # DdangFonts Bold (Pass: Bold)
        "/usr/share/fonts/truetype/custom/test2/DdangFontsBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ],
    "italic": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"
    ]
}

# 폰트 크기 카테고리 매핑
FONT_SIZE_MAP = {
    "small": (12, 24),
    "medium": (24, 48),
    "large": (48, 96)
}

# 폰트 이름별 경로 매핑 (LLaVA 추천 폰트 이름 -> 실제 파일 경로)
# Pass 폴더의 폰트만 사용 (총 16개)
FONT_NAME_MAP = {
    # Pretendard GOV Bold (test1/Pass)
    "pretendard gov bold": "/usr/share/fonts/truetype/custom/PretendardGOV-Bold.ttf",
    "pretendard bold": "/usr/share/fonts/truetype/custom/PretendardGOV-Bold.ttf",
    # Gmarket Sans (test1/Pass)
    "gmarket sans": "/usr/share/fonts/truetype/custom/GmarketSansTTFMedium.ttf",
    "gmarket": "/usr/share/fonts/truetype/custom/GmarketSansTTFMedium.ttf",
    "gmarket sans medium": "/usr/share/fonts/truetype/custom/GmarketSansTTFMedium.ttf",
    "gmarket sans bold": "/usr/share/fonts/truetype/custom/GmarketSansTTFBold.ttf",
    # Baemin (test1/Pass)
    "baemin dohyeon": "/usr/share/fonts/truetype/custom/BMDOHYEON_ttf.ttf",
    "baemin euljiro": "/usr/share/fonts/truetype/custom/BMEuljiro10yearslater.ttf",
    "baemin": "/usr/share/fonts/truetype/custom/BMDOHYEON_ttf.ttf",
    # Nanum Gothic Bold (test1/Pass)
    "nanum gothic bold": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    # Cafe24 폰트 (test2/Pass: Classictype, Danjunghae, Ssurround, Supermagic)
    "cafe24 classictype": "/usr/share/fonts/truetype/custom/test2/Cafe24Classictype-v1.1.ttf",
    "cafe24 classic": "/usr/share/fonts/truetype/custom/test2/Cafe24Classictype-v1.1.ttf",
    "cafe24 danjunghae": "/usr/share/fonts/truetype/custom/test2/Cafe24Danjunghae-v2.0.ttf",
    "cafe24 ssurround": "/usr/share/fonts/truetype/custom/test2/Cafe24Ssurround-v2.0.ttf",
    "cafe24 supermagic": "/usr/share/fonts/truetype/custom/test2/Cafe24Supermagic-Bold-v1.0.ttf",
    "cafe24 supermagic bold": "/usr/share/fonts/truetype/custom/test2/Cafe24Supermagic-Bold-v1.0.ttf",
    # Jalnan 폰트 (test2/Pass: Jalnan, Jalnan Gothic)
    "jalnan": "/usr/share/fonts/truetype/custom/test2/Jalnan2TTF.ttf",
    "jalnan2": "/usr/share/fonts/truetype/custom/test2/Jalnan2TTF.ttf",
    "jalnan gothic": "/usr/share/fonts/truetype/custom/test2/JalnanGothicTTF.ttf",
    # DdangFonts (test2/Pass: Light, Medium, Bold, 기본값은 Medium)
    "ddangfonts": "/usr/share/fonts/truetype/custom/test2/DdangFontsMedium.ttf",
    "ddangfonts light": "/usr/share/fonts/truetype/custom/test2/DdangFontsLight.ttf",
    "ddangfonts medium": "/usr/share/fonts/truetype/custom/test2/DdangFontsMedium.ttf",
    "ddangfonts bold": "/usr/share/fonts/truetype/custom/test2/DdangFontsBold.ttf",
    "땅스부대찌개": "/usr/share/fonts/truetype/custom/test2/DdangFontsMedium.ttf",
    "땅스부대찌개 light": "/usr/share/fonts/truetype/custom/test2/DdangFontsLight.ttf",
    "땅스부대찌개 medium": "/usr/share/fonts/truetype/custom/test2/DdangFontsMedium.ttf",
    "땅스부대찌개 bold": "/usr/share/fonts/truetype/custom/test2/DdangFontsBold.ttf",
}


def get_korean_font_note() -> str:
    """
    LLaVA 프롬프트용 한글 폰트 안내 텍스트 생성
    
    Returns:
        한글 폰트 안내 문자열
    """
    return """
## Korean Text Detected
The ad copy contains Korean characters (한글). For Korean text, consider:

### **sans-serif** (Modern and clean fonts):
- **Gmarket Sans** (friendly, approachable) - good for casual, commercial, friendly styles
  - Variants: Medium, Bold
- **Baemin Dohyeon** (unique, distinctive) - good for brand identity, memorable styles
- **Nanum Gothic Bold** (classic, reliable) - good for general purpose, readable styles
- **Cafe24 Classictype** (elegant, classic) - good for traditional, sophisticated styles
- **Cafe24 Danjunghae** (warm, friendly) - good for approachable, cozy styles
- **Cafe24 Ssurround** (playful, dynamic) - good for energetic, fun styles
- **Jalnan** (bold, impactful) - good for attention-grabbing, strong styles
- **Jalnan Gothic** (modern, clean) - good for contemporary, sleek styles
- **DdangFonts** (unique, distinctive) - good for memorable, brand identity styles
  - Variants: Light, Medium, Bold

### **bold** (Strong and impactful):
- **Pretendard GOV Bold** (professional emphasis)
- **Gmarket Sans Bold** (commercial emphasis)
- **Baemin Euljiro** (retro, nostalgic, bold)
- **Nanum Gothic Bold** (classic bold)
- **Cafe24 Supermagic** (bold, magical) - good for eye-catching, bold styles
- **DdangFonts Bold** (strong, distinctive)

**Available Korean fonts (use exact names - Pass 폴더의 폰트만):**
Pretendard GOV Bold,
Gmarket Sans, Gmarket Sans Bold,
Baemin Dohyeon, Baemin Euljiro,
Nanum Gothic Bold,
Cafe24 Classictype, Cafe24 Danjunghae, Cafe24 Ssurround, Cafe24 Supermagic,
Jalnan, Jalnan Gothic,
DdangFonts, DdangFonts Light, DdangFonts Medium, DdangFonts Bold
"""


def get_font_name_list_for_llava() -> str:
    """
    LLaVA 프롬프트 IMPORTANT 섹션용 폰트 이름 리스트 생성
    
    Returns:
        폰트 이름 리스트 문자열
    """
    return """  * **Sans-serif**: "Gmarket Sans", "Gmarket Sans Bold", "Baemin Dohyeon", "Nanum Gothic Bold", "Cafe24 Classictype", "Cafe24 Danjunghae", "Cafe24 Ssurround", "Jalnan", "Jalnan Gothic", "DdangFonts", "DdangFonts Light", "DdangFonts Medium"
  * **Bold/Unique**: "Pretendard GOV Bold", "Baemin Euljiro", "Cafe24 Supermagic", "DdangFonts Bold"
  * For English text: leave empty or use generic names like "Arial", "Helvetica"
  * If you recommend a specific font, use its EXACT name from the list above (e.g., "Gmarket Sans", "Cafe24 Classictype", "Jalnan", "DdangFonts Bold")"""


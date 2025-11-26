#!/bin/bash
# 폰트 설치 스크립트
# /opt/feedlyai/fonts에서 폰트를 읽어서 /usr/share/fonts/truetype/custom에 설치

set -e

FONT_SOURCE_DIR="/opt/feedlyai/fonts"
FONT_DEST_DIR="/usr/share/fonts/truetype/custom"
FONT_DEST_DIR_TEST2="/usr/share/fonts/truetype/custom/test2"
NANUM_DEST_DIR="/usr/share/fonts/truetype/nanum"

echo "=== 폰트 설치 시작 ==="

# 디렉토리 생성
mkdir -p "$FONT_DEST_DIR"
mkdir -p "$FONT_DEST_DIR_TEST2"
mkdir -p "$NANUM_DEST_DIR"

# 폰트 소스 디렉토리 확인
if [ ! -d "$FONT_SOURCE_DIR" ]; then
    echo "⚠️  경고: 폰트 소스 디렉토리가 없습니다: $FONT_SOURCE_DIR"
    echo "   호스트에서 폰트를 설치해야 합니다."
    exit 0  # 에러가 아니므로 0으로 종료
fi

# test1 폰트 복사
if [ -d "$FONT_SOURCE_DIR/test1/download_koreanfont" ]; then
    echo "📁 test1 폰트 복사 중..."
    
    # Gmarket Sans
    if [ -f "$FONT_SOURCE_DIR/test1/download_koreanfont/GmarketSansTTF/GmarketSansTTFMedium.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test1/download_koreanfont/GmarketSansTTF/GmarketSansTTFMedium.ttf" "$FONT_DEST_DIR/"
        echo "  ✓ GmarketSansTTFMedium.ttf"
    fi
    if [ -f "$FONT_SOURCE_DIR/test1/download_koreanfont/GmarketSansTTF/GmarketSansTTFBold.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test1/download_koreanfont/GmarketSansTTF/GmarketSansTTFBold.ttf" "$FONT_DEST_DIR/"
        echo "  ✓ GmarketSansTTFBold.ttf"
    fi
    
    # Baemin
    if [ -f "$FONT_SOURCE_DIR/test1/download_koreanfont/BMDOHYEON_ttf.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test1/download_koreanfont/BMDOHYEON_ttf.ttf" "$FONT_DEST_DIR/"
        echo "  ✓ BMDOHYEON_ttf.ttf"
    fi
    if [ -f "$FONT_SOURCE_DIR/test1/download_koreanfont/BMEuljiro10yearslater.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test1/download_koreanfont/BMEuljiro10yearslater.ttf" "$FONT_DEST_DIR/"
        echo "  ✓ BMEuljiro10yearslater.ttf"
    fi
    
    # Pretendard GOV
    if [ -f "$FONT_SOURCE_DIR/test1/download_koreanfont/PretendardGOV-1.3.9/public/static/alternative/PretendardGOV-Bold.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test1/download_koreanfont/PretendardGOV-1.3.9/public/static/alternative/PretendardGOV-Bold.ttf" "$FONT_DEST_DIR/"
        echo "  ✓ PretendardGOV-Bold.ttf"
    fi
else
    echo "⚠️  test1 폰트 디렉토리를 찾을 수 없습니다"
fi

# test2 폰트 복사
if [ -d "$FONT_SOURCE_DIR/test2/download_koreanfont" ]; then
    echo "📁 test2 폰트 복사 중..."
    
    # Cafe24
    for font in "Cafe24Classictype-v1.1/Cafe24Classictype-v1.1.ttf" \
                "Cafe24Danjunghae-v2.0/Cafe24Danjunghae-v2.0.ttf" \
                "Cafe24Ssurround-v2.0/Cafe24Ssurround-v2.0.ttf" \
                "Cafe24Supermagic-Bold-v1.0/Cafe24Supermagic-Bold-v1.0.ttf"; do
        if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/$font" ]; then
            filename=$(basename "$font")
            cp "$FONT_SOURCE_DIR/test2/download_koreanfont/$font" "$FONT_DEST_DIR_TEST2/"
            echo "  ✓ $filename"
        fi
    done
    
    # Jalnan
    if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/Jalnan2/Jalnan2TTF.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test2/download_koreanfont/Jalnan2/Jalnan2TTF.ttf" "$FONT_DEST_DIR_TEST2/"
        echo "  ✓ Jalnan2TTF.ttf"
    fi
    if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/JalnanGothic/JalnanGothicTTF.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test2/download_koreanfont/JalnanGothic/JalnanGothicTTF.ttf" "$FONT_DEST_DIR_TEST2/"
        echo "  ✓ JalnanGothicTTF.ttf"
    fi
    
    # DdangFonts
    if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Light.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Light.ttf" "$FONT_DEST_DIR_TEST2/DdangFontsLight.ttf"
        echo "  ✓ DdangFontsLight.ttf"
    fi
    if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Medium.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Medium.ttf" "$FONT_DEST_DIR_TEST2/DdangFontsMedium.ttf"
        echo "  ✓ DdangFontsMedium.ttf"
    fi
    if [ -f "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Bold.ttf" ]; then
        cp "$FONT_SOURCE_DIR/test2/download_koreanfont/DdangFontsTTF/DdangFonts-Bold.ttf" "$FONT_DEST_DIR_TEST2/DdangFontsBold.ttf"
        echo "  ✓ DdangFontsBold.ttf"
    fi
else
    echo "⚠️  test2 폰트 디렉토리를 찾을 수 없습니다"
fi

# Nanum 폰트 링크 생성
if find /usr/share/fonts -name "*NanumGothic*Bold*" -type f | head -1 | xargs -I {} ln -sf {} "$NANUM_DEST_DIR/NanumGothicBold.ttf" 2>/dev/null; then
    echo "  ✓ NanumGothicBold.ttf 링크 생성"
fi

# 폰트 캐시 업데이트
echo "🔄 폰트 캐시 업데이트 중..."
fc-cache -fv

echo "=== 폰트 설치 완료 ==="


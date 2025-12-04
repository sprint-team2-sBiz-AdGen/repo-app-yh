# 한글 폰트 설치 가이드

GCP Ubuntu 서버에서 한글 텍스트를 이미지에 오버레이하려면 한글 폰트를 설치해야 합니다.

## 한글 폰트 설치 방법

### 1. 나눔 폰트 설치 (추천)

```bash
sudo apt-get update
sudo apt-get install fonts-nanum fonts-nanum-coding fonts-nanum-extra
```

설치 후 폰트 경로:
- `/usr/share/fonts/truetype/nanum/NanumGothic.ttf`
- `/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf`
- `/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf`
- `/usr/share/fonts/truetype/nanum/NanumMyeongjo.ttf` (serif)

### 2. 은 폰트(Unfonts) 설치

```bash
sudo apt-get install fonts-unfonts-core fonts-unfonts-extra
```

설치 후 폰트 경로:
- `/usr/share/fonts/truetype/unfonts-core/UnDotum.ttf`
- `/usr/share/fonts/truetype/unfonts-core/UnDotumBold.ttf`

### 3. 백묵 폰트(Baekmuk) 설치

```bash
sudo apt-get install fonts-baekmuk
```

설치 후 폰트 경로:
- `/usr/share/fonts/truetype/baekmuk/baekmuk-gulim.ttf`
- `/usr/share/fonts/truetype/baekmuk/baekmuk-batang.ttf`

### 4. Noto Sans KR (이미 포함되어 있을 수 있음)

```bash
sudo apt-get install fonts-noto-cjk
```

설치 후 폰트 경로:
- `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`
- `/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf`

## Docker 컨테이너에 설치하기

### 방법 1: Dockerfile에 추가

```dockerfile
RUN apt-get update && \
    apt-get install -y fonts-nanum fonts-nanum-coding fonts-nanum-extra \
                       fonts-unfonts-core fonts-unfonts-extra \
                       fonts-baekmuk fonts-noto-cjk && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

### 방법 2: 실행 중인 컨테이너에 설치

```bash
docker exec -it feedlyai-work-yh bash
apt-get update
apt-get install -y fonts-nanum fonts-nanum-coding fonts-nanum-extra
apt-get install -y fonts-unfonts-core fonts-unfonts-extra
apt-get install -y fonts-baekmuk
exit
```

### 방법 3: 수동 폰트 파일 복사

```bash
# 호스트에 폰트 파일 다운로드 후
docker cp /path/to/font.ttf feedlyai-work-yh:/usr/share/fonts/truetype/
docker exec feedlyai-work-yh fc-cache -f -v
```

## 폰트 설치 확인

```bash
# 컨테이너 내부에서 확인
docker exec feedlyai-work-yh find /usr/share/fonts -name "*nanum*" -o -name "*noto*" -o -name "*unfonts*" -o -name "*baekmuk*"
```

## 코드에서 사용

`routers/overlay.py`의 `FONT_STYLE_MAP`에 한글 폰트 경로가 이미 추가되어 있습니다. 폰트를 설치하면 자동으로 한글 텍스트가 올바르게 렌더링됩니다.

## 추가 무료 한글 폰트 (수동 설치)

다음 폰트들은 상업적 사용이 가능한 무료 한글 폰트입니다:

- **본고딕(Noto Sans KR)**: 이미 포함됨
- **프리텐다드(Pretendard)**: https://github.com/orioncactus/pretendard
- **G마켓 산스**: https://company.gmarket.co.kr/company/company.aspx?Idx=102
- **배달의민족체**: https://www.woowahan.com/#/fonts
- **스포카 한 산스**: https://spoqa.github.io/spoqa-han-sans/

수동 설치 시:
```bash
mkdir -p /usr/share/fonts/truetype/custom
# 폰트 파일 복사
cp font.ttf /usr/share/fonts/truetype/custom/
fc-cache -f -v
```

## 참고

- 폰트 설치 후 `fc-cache -f -v` 명령으로 폰트 캐시를 갱신해야 할 수 있습니다.
- PIL/Pillow는 TTF, OTF, TTC 형식을 지원합니다.
- 폰트 경로는 `FONT_STYLE_MAP`에서 우선순위 순서로 시도됩니다.


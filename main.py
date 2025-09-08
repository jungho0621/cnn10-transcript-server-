from yt_dlp import YoutubeDL
import os, re

def vtt_to_text(vtt_path: str) -> str:
    """VTT 파일을 일반 텍스트로 변환"""
    out_lines = []
    with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.lower().startswith("webvtt"):
                continue
            if "-->" in s:
                continue
            if re.fullmatch(r"\d+", s):
                continue
            out_lines.append(s)
    txt = " ".join(out_lines)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

def fetch_via_ytdlp(vid: str):
    """yt-dlp Python API로 영어 자막 추출"""
    url = f"https://www.youtube.com/watch?v={vid}"
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "outtmpl": f"{vid}.%(ext)s"
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        subs = info.get("requested_subtitles")
        if not subs:
            raise ValueError("no subtitles via yt-dlp")

    # 실제로 저장된 파일 경로 확인
    candidates = []
    if os.path.exists(f"{vid}.en.vtt"):
        candidates.append(f"{vid}.en.vtt")
    if os.path.exists(f"{vid}.en-US.vtt"):
        candidates.append(f"{vid}.en-US.vtt")

    if not candidates:
        raise FileNotFoundError("no VTT file written")

    # 가장 큰 파일(=내용 많은 것) 선택
    vtt_path = max(candidates, key=lambda p: os.path.getsize(p))
    text = vtt_to_text(vtt_path)
    if not text:
        raise ValueError("empty transcript text from yt-dlp")

    return text, "yt_dlp"

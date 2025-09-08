from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
from yt_dlp import YoutubeDL
import os, re

app = Flask(__name__)

@app.get("/")
def home():
    return "OK"

# ----- 유틸: VTT -> 텍스트 -----
def vtt_to_text(vtt_path: str) -> str:
    out = []
    with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s: continue
            if s.lower().startswith("webvtt"): continue
            if "-->" in s: continue
            if re.fullmatch(r"\d+", s): continue
            out.append(s)
    txt = " ".join(out)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

# ----- 1순위: 공식 API -----
def fetch_via_api(vid: str):
    tlist = YouTubeTranscriptApi.list_transcripts(vid)

    # 수동 영어
    try:
        tr = tlist.find_transcript(['en','en-US'])
        return tr.fetch(), "manual_en"
    except Exception:
        pass

    # 자동 생성 영어
    try:
        tr = tlist.find_generated_transcript(['en'])
        return tr.fetch(), "auto_en"
    except Exception:
        pass

    # 다른 언어 -> 영어 번역
    try:
        any_tr = next(iter(tlist))
        tr_en = any_tr.translate('en')
        return tr_en.fetch(), f"translated_from_{any_tr.language_code}"
    except Exception:
        raise NoTranscriptFound("no transcript via API")

# ----- 2순위: yt-dlp Python API (자동/수동 자막 파일 강제 추출) -----
def fetch_via_ytdlp(vid: str):
    url = f"https://www.youtube.com/watch?v={vid}"
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en","en-US"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "outtmpl": f"{vid}.%(ext)s",   # <id>.en.vtt / <id>.en-US.vtt 로 저장됨
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        subs = info.get("requested_subtitles")
        if not subs:
            raise ValueError("no subtitles via yt-dlp")

    candidates = []
    if os.path.exists(f"{vid}.en.vtt"):
        candidates.append(f"{vid}.en.vtt")
    if os.path.exists(f"{vid}.en-US.vtt"):
        candidates.append(f"{vid}.en-US.vtt")
    if not candidates:
        raise FileNotFoundError("no VTT file written")

    vtt_path = max(candidates, key=lambda p: os.path.getsize(p))
    text = vtt_to_text(vtt_path)
    if not text:
        raise ValueError("empty transcript text from yt-dlp")
    return text, "yt_dlp"

@app.get("/debug")
def debug_tracks():
    vid = request.args.get("id", "").strip()
    if not vid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(vid)
        infos = [{"language": getattr(t,"language",None),
                  "language_code": getattr(t,"language_code",None),
                  "is_generated": getattr(t,"is_generated",None)} for t in tlist]
        return jsonify({"ok": True, "tracks": infos})
    except TranscriptsDisabled:
        return jsonify({"ok": False, "error": "transcripts_disabled"}), 404
    except NoTranscriptFound:
        return jsonify({"ok": False, "error": "no_transcript_found"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404

@app.get("/transcript")
def transcript():
    vid = request.args.get("id", "").strip()
    if not vid:
        return jsonify({"ok": False, "error": "missing id"}), 400

    # 1) 공식 API 시도
    try:
        chunks, source = fetch_via_api(vid)
        text = " ".join(c["text"].replace("\n"," ").strip() for c in chunks if c["text"].strip())
        if text:
            return jsonify({"ok": True, "video_id": vid, "length": len(text), "source": source, "text": text})
    except Exception:
        pass

    # 2) yt-dlp 백업 시도
    try:
        text, source = fetch_via_ytdlp(vid)
        return jsonify({"ok": True, "video_id": vid, "length": len(text), "source": source, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"no transcript (api+yt-dlp): {e}"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

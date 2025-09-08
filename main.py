from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import os, tempfile, uuid, subprocess, re, pathlib

app = Flask(__name__)

@app.get("/")
def home():
    return "OK"

def fetch_best_english_via_api(vid: str):
    tlist = YouTubeTranscriptApi.list_transcripts(vid)
    # 1) 고정 영어
    try:
        tr = tlist.find_transcript(['en','en-US'])
        return tr.fetch(), "manual_en"
    except Exception:
        pass
    # 2) 자동 생성 영어
    try:
        tr = tlist.find_generated_transcript(['en'])
        return tr.fetch(), "auto_en"
    except Exception:
        pass
    # 3) 다른 언어 → 영어 번역
    try:
        any_tr = next(iter(tlist))
        tr_en = any_tr.translate('en')
        return tr_en.fetch(), f"translated_from_{any_tr.language_code}"
    except Exception:
        raise NoTranscriptFound("no transcript via API")

def vtt_to_text(vtt_path: str) -> str:
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
    # 중복/겹침 줄바꿈 정리
    txt = " ".join(out_lines)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

def fetch_via_ytdlp(vid: str):
    """자막 파일을 yt-dlp로 강제 추출 (자동자막 포함)"""
    tmpdir = tempfile.gettempdir()
    base = os.path.join(tmpdir, f"{uuid.uuid4()}")
    # 자막만 받도록 옵션 구성
    # --skip-download : 영상은 받지 않음
    # --write-auto-sub : 자동자막 허용
    # --sub-langs en,en-US : 영어 우선
    cmd = [
        "yt-dlp",
        f"https://www.youtube.com/watch?v={vid}",
        "--skip-download",
        "--write-auto-sub",
        "--write-sub",
        "--sub-langs", "en,en-US",
        "--sub-format", "vtt",
        "-o", base + ".%(ext)s"
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # 생성된 .vtt 찾기
    candidates = list(pathlib.Path(tmpdir).glob(pathlib.Path(base).name + "*.vtt"))
    if not candidates:
        raise FileNotFoundError("no vtt produced")
    # 가장 긴 파일을 선택(보통 en 또는 en-US)
    vtt_path = max(candidates, key=lambda p: p.stat().st_size)
    text = vtt_to_text(str(vtt_path))
    if not text:
        raise ValueError("empty transcript from vtt")
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
    # 1) API 시도
    try:
        chunks, source = fetch_best_english_via_api(vid)
        text = " ".join(c["text"].replace("\n"," ").strip() for c in chunks if c["text"].strip())
        if text:
            return jsonify({"ok": True, "video_id": vid, "length": len(text), "source": source, "text": text})
    except Exception:
        pass
    # 2) 실패 시 yt-dlp 백업
    try:
        text, source = fetch_via_ytdlp(vid)
        return jsonify({"ok": True, "video_id": vid, "length": len(text), "source": source, "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": f"no transcript (api+yt-dlp) : {e}"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

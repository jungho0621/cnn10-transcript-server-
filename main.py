from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
import os

app = Flask(__name__)

@app.get("/")
def home():
    return "OK"

def fetch_best_english(vid: str):
    """
    1) 수동 영어(en,en-US)
    2) 자동 생성 영어(en)
    3) 다른 언어 → 영어 번역본(가능할 때)
    순서로 최대한 끌어오기
    """
    tlist = YouTubeTranscriptApi.list_transcripts(vid)

    # 1) 수동 영어
    try:
        tr = tlist.find_transcript(['en', 'en-US'])
        return tr.fetch(), "manual_en"
    except Exception:
        pass

    # 2) 자동 생성 영어
    try:
        tr = tlist.find_generated_transcript(['en'])
        return tr.fetch(), "auto_en"
    except Exception:
        pass

    # 3) 다른 언어 하나 → 영어 번역
    try:
        any_tr = next(iter(tlist))
        tr_en = any_tr.translate('en')
        return tr_en.fetch(), f"translated_from_{any_tr.language_code}"
    except Exception:
        raise NoTranscriptFound("no transcript track that can be fetched or translated to English")

@app.get("/debug")
def debug_transcripts():
    vid = request.args.get("id", "").strip()
    if not vid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(vid)
        infos = []
        for tr in tlist:
            infos.append({
                "language": getattr(tr, "language", None),
                "language_code": getattr(tr, "language_code", None),
                "is_generated": getattr(tr, "is_generated", None),
                "url": getattr(tr, "url", None)  # 어떤 건 None일 수 있음
            })
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
    try:
        chunks, source = fetch_best_english(vid)
        text = " ".join(c["text"].replace("\n", " ").strip() for c in chunks if c["text"].strip())
        return jsonify({"ok": True, "video_id": vid, "length": len(text), "source": source, "text": text})
    except (NoTranscriptFound, TranscriptsDisabled):
        return jsonify({"ok": False, "error": "no transcript available (captions disabled or none)"}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

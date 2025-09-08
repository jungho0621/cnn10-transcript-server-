from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
import os

app = Flask(__name__)

@app.get("/")
def home():
    return "OK"

@app.get("/transcript")
def transcript():
    vid = request.args.get("id", "").strip()
    if not vid:
        return jsonify({"ok": False, "error": "missing id"}), 400
    try:
        tlist = YouTubeTranscriptApi.list_transcripts(vid)
        tr = None
        try:
            tr = tlist.find_transcript(['en','en-US'])
        except:
            pass
        if tr is None:
            try:
                tr = tlist.find_generated_transcript(['en'])
            except:
                pass
        if tr is None:
            try:
                any_tr = next(iter(tlist))
                tr = any_tr.translate('en')
            except:
                return jsonify({"ok": False, "error": "no transcript available (captions disabled or blocked)"}), 404

        chunks = tr.fetch()
        text = " ".join(c["text"].replace("\n"," ").strip() for c in chunks if c["text"].strip())
        return jsonify({"ok": True, "video_id": vid, "length": len(text), "text": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

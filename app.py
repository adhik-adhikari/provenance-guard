import uuid

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

import storage
from signals import get_llm_score, get_stylometric_score
from scoring import score_confidence
from labels import get_label
from timestamps import now_iso

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

storage.init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id", "anonymous")

    if not text:
        return jsonify({"error": "text field is required"}), 400

    try:
        content_id = str(uuid.uuid4())
        llm_score = get_llm_score(text)
        stylometric_score = get_stylometric_score(text)
        result = score_confidence(llm_score, stylometric_score)
        label = get_label(result["attribution"])

        record = {
            "content_id": content_id,
            "creator_id": creator_id,
            "text": text,
            "timestamp": now_iso(),
            "llm_score": llm_score,
            "stylometric_score": stylometric_score,
            "combined_score": result["combined_score"],
            "confidence": result["confidence"],
            "attribution": result["attribution"],
            "label": label,
            "status": "classified",
            "appeal_reasoning": None,
            "appeal_timestamp": None,
        }
        storage.insert_submission(record)

        return jsonify(
            {
                "content_id": content_id,
                "attribution": result["attribution"],
                "confidence": result["confidence"],
                "label": label,
                "llm_score": llm_score,
                "stylometric_score": stylometric_score,
            }
        )
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(force=True, silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id or not creator_reasoning:
        return jsonify({"error": "content_id and creator_reasoning are required"}), 400

    record = storage.get_submission(content_id)
    if not record:
        return jsonify({"error": "content_id not found"}), 404

    storage.update_appeal(content_id, creator_reasoning, now_iso())

    return jsonify(
        {
            "content_id": content_id,
            "status": "under_review",
            "message": "Appeal received and logged for human review.",
        }
    )


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": storage.get_log()})


@app.route("/analytics", methods=["GET"])
def analytics():
    return jsonify(storage.get_analytics())


if __name__ == "__main__":
    app.run(debug=True, port=5050)

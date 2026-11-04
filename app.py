import os
import uuid
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from flask_cors import CORS
from supabase import create_client
from werkzeug.utils import secure_filename

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # server-side only!
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
BUCKET = "project-images"
TABLE = "projects"
ALLOWED_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

# Jin websites ko API fetch karne ki permission hai
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "https://webshakti.net.in/"
    ).split(",")
]

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB (Vercel limit 4.5 MB)

# Sirf /api/* ko CORS allow
CORS(app, resources={r"/api/*": {"origins": ALLOWED_ORIGINS}})


# ---------- helpers ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def upload_image(file):
    """Image Supabase Storage me upload karke public URL return karta hai."""
    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    path = f"{uuid.uuid4().hex}.{ext}"
    supabase.storage.from_(BUCKET).upload(
        path,
        file.read(),
        {"content-type": file.mimetype or f"image/{ext}"},
    )
    return supabase.storage.from_(BUCKET).get_public_url(path)


# ---------- admin panel ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Galat password", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def admin():
    res = supabase.table(TABLE).select("*").order("created_at", desc=True).execute()
    return render_template("admin.html", projects=res.data)


@app.route("/add", methods=["POST"])
@login_required
def add_project():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    link = request.form.get("link", "").strip()
    image = request.files.get("image")

    if not name or not description or not link:
        flash("Name, description aur link zaroori hain", "error")
        return redirect(url_for("admin"))

    image_url = None
    try:
        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Sirf png/jpg/jpeg/webp/gif allowed hai", "error")
                return redirect(url_for("admin"))
            image_url = upload_image(image)

        supabase.table(TABLE).insert({
            "name": name,
            "description": description,
            "link": link,
            "image_url": image_url,
        }).execute()
        flash("Project add ho gaya ✅", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("admin"))


@app.route("/delete/<int:project_id>", methods=["POST"])
@login_required
def delete_project(project_id):
    try:
        supabase.table(TABLE).delete().eq("id", project_id).execute()
        flash("Project delete ho gaya", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("admin"))


# ---------- public API (webshaktii fetch karegi) ----------
@app.route("/api/projects", methods=["GET"])
def api_projects():
    try:
        res = supabase.table(TABLE).select("*").order("created_at", desc=True).execute()
        return jsonify({"success": True, "count": len(res.data), "data": res.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/projects/<int:project_id>", methods=["GET"])
def api_project(project_id):
    try:
        res = supabase.table(TABLE).select("*").eq("id", project_id).execute()
        if not res.data:
            return jsonify({"success": False, "error": "Not found"}), 404
        return jsonify({"success": True, "data": res.data[0]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
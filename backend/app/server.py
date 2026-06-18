from __future__ import annotations

import tempfile
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_file, session
from flask_cors import CORS
from openpyxl import Workbook

from .auth import admin_logged_in, clear_failed_login, is_locked_out, record_failed_login
from .config import Config
from .db import connect, init_db
from .excel_import import parse_members_from_workbook
from .face import FaceVerifier
from .utils import decode_data_url, ensure_face_dir, haversine, now_ist_iso


verifier = FaceVerifier()


def create_app() -> Flask:
    Config.refresh()
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SESSION_SECRET
    app.config["SESSION_COOKIE_SAMESITE"] = Config.SESSION_COOKIE_SAMESITE
    app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
    CORS(app, origins=Config.ALLOWED_ORIGIN, supports_credentials=True)
    init_db()
    ensure_face_dir()
    verifier.warm()

    def require_admin(handler):
        @wraps(handler)
        def wrapper(*args, **kwargs):
            if not admin_logged_in():
                return jsonify({"error": "Admin login required"}), 401
            return handler(*args, **kwargs)

        return wrapper

    def get_active_event(conn):
        return conn.execute(
            "SELECT * FROM events WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def get_member(conn, event_id: int, enrollment: str):
        return conn.execute(
            """
            SELECT m.*,
                   EXISTS(
                     SELECT 1 FROM attendance a
                     WHERE a.event_id = m.event_id AND a.enrollment = m.enrollment
                   ) AS already_marked
            FROM members m
            WHERE m.event_id = ? AND m.enrollment = ?
            """,
            (event_id, enrollment),
        ).fetchone()

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "face_mode": "deepface" if verifier.available else "fallback"})

    @app.post("/api/login")
    def login():
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        if is_locked_out(client_ip):
            return jsonify({"error": "Too many failed attempts. Try again later."}), 429
        payload = request.get_json(silent=True) or {}
        if payload.get("password") != Config.ADMIN_PASSWORD:
            record_failed_login(client_ip)
            return jsonify({"error": "Invalid password"}), 401
        clear_failed_login(client_ip)
        session["is_admin"] = True
        return jsonify({"success": True})

    @app.post("/api/logout")
    def logout():
        session.clear()
        return jsonify({"success": True})

    @app.post("/api/create-event")
    @require_admin
    def create_event():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        date = str(payload.get("date", "")).strip()
        club_name = str(payload.get("club_name", "")).strip()
        if not name or not date or not club_name:
            return jsonify({"error": "name, date, and club_name are required"}), 400
        with connect() as conn:
            conn.execute("UPDATE events SET is_active = 0 WHERE is_active = 1")
            cursor = conn.execute(
                "INSERT INTO events(name, date, club_name, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                (name, date, club_name, now_ist_iso()),
            )
            event_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO geo_settings(event_id, center_lat, center_lng, radius_metres, enabled, created_at, updated_at)
                VALUES (?, NULL, NULL, ?, 0, ?, ?)
                """,
                (event_id, Config.DEFAULT_RADIUS_METRES, now_ist_iso(), now_ist_iso()),
            )
        return jsonify({"success": True, "event_id": event_id})

    @app.post("/api/import")
    @require_admin
    def import_members():
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            return jsonify({"error": "No file uploaded"}), 400
        if not uploaded.filename.lower().endswith(".xlsx"):
            return jsonify({"error": "Only .xlsx files are supported"}), 400
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "Create an event first"}), 400
            try:
                members, warnings = parse_members_from_workbook(uploaded.read())
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            imported = 0
            skipped: list[str] = list(warnings)
            for member in members:
                exists = conn.execute(
                    "SELECT 1 FROM members WHERE event_id = ? AND enrollment = ?",
                    (event["id"], member["enrollment"]),
                ).fetchone()
                if exists:
                    skipped.append(f"Enrollment {member['enrollment']} already exists for this event")
                    continue
                conn.execute(
                    """
                    INSERT INTO members(event_id, enrollment, name, department, course, institute, email, phone, face_registered, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        event["id"],
                        member["enrollment"],
                        member["name"],
                        member["department"],
                        member["course"],
                        member["institute"],
                        member["email"] or None,
                        member["phone"] or None,
                        now_ist_iso(),
                    ),
                )
                imported += 1
        return jsonify({"success": True, "imported": imported, "warnings": skipped})

    @app.get("/api/members")
    @require_admin
    def list_members():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"members": [], "event": None})
            members = conn.execute(
                "SELECT * FROM members WHERE event_id = ? ORDER BY enrollment ASC", (event["id"],)
            ).fetchall()
        return jsonify({"event": dict(event), "members": [dict(member) for member in members]})

    @app.get("/api/public-members")
    def public_members():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"members": [], "event": None})
            members = conn.execute(
                """
                SELECT enrollment, name, department, course, institute, face_registered
                FROM members
                WHERE event_id = ?
                ORDER BY enrollment ASC
                """,
                (event["id"],),
            ).fetchall()
        return jsonify({"event": dict(event), "members": [dict(member) for member in members]})

    @app.get("/api/member/<enrollment>")
    def member_details(enrollment: str):
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "No active event"}), 404
            member = get_member(conn, event["id"], enrollment)
            if not member:
                return jsonify({"error": "Not registered for this event"}), 404
            return jsonify({"member": dict(member)})

    @app.post("/api/geo/set")
    @require_admin
    def set_geo():
        payload = request.get_json(silent=True) or {}
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "Create an event first"}), 400
            center_lat = payload.get("center_lat")
            center_lng = payload.get("center_lng")
            radius_metres = int(payload.get("radius_metres", Config.DEFAULT_RADIUS_METRES))
            enabled = 1 if payload.get("enabled") else 0
            if enabled and (center_lat is None or center_lng is None):
                return jsonify({"error": "center_lat and center_lng are required when geo is enabled"}), 400
            conn.execute(
                """
                UPDATE geo_settings
                SET center_lat = ?, center_lng = ?, radius_metres = ?, enabled = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (center_lat, center_lng, radius_metres, enabled, now_ist_iso(), event["id"]),
            )
            settings = conn.execute("SELECT * FROM geo_settings WHERE event_id = ?", (event["id"],)).fetchone()
        return jsonify({"success": True, "settings": dict(settings)})

    @app.get("/api/geo/get")
    def get_geo():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"event": None, "settings": None})
            settings = conn.execute("SELECT * FROM geo_settings WHERE event_id = ?", (event["id"],)).fetchone()
        return jsonify({"event": dict(event), "settings": dict(settings) if settings else None})

    @app.post("/api/check-location")
    def check_location():
        payload = request.get_json(silent=True) or {}
        lat = payload.get("lat")
        lng = payload.get("lng")
        if lat is None or lng is None:
            return jsonify({"allowed": False, "message": "Location is required"}), 400
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"allowed": False, "message": "No active event"}), 400
            settings = conn.execute("SELECT * FROM geo_settings WHERE event_id = ?", (event["id"],)).fetchone()
            if not settings or not settings["enabled"]:
                return jsonify({"allowed": True, "distance_metres": None, "message": "Geo check disabled"})
            if settings["center_lat"] is None or settings["center_lng"] is None:
                return jsonify({"allowed": False, "message": "Venue boundary is not configured"}), 400
            distance = haversine(float(lat), float(lng), settings["center_lat"], settings["center_lng"])
            allowed = distance <= settings["radius_metres"]
        return jsonify(
            {
                "allowed": allowed,
                "distance_metres": round(distance, 1),
                "message": "Inside venue boundary" if allowed else "You must be physically present at the venue",
            }
        )

    @app.post("/api/register-face")
    @require_admin
    def register_face():
        payload = request.get_json(silent=True) or {}
        enrollment = str(payload.get("enrollment", "")).strip()
        image_data = payload.get("image_data")
        if not enrollment or not image_data:
            return jsonify({"error": "enrollment and image_data are required"}), 400
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "Create an event first"}), 400
            member = get_member(conn, event["id"], enrollment)
            if not member:
                return jsonify({"error": "Member not found"}), 404
            face_path = ensure_face_dir() / f"{enrollment}.jpg"
            face_path.write_bytes(decode_data_url(image_data))
            conn.execute(
                "UPDATE members SET face_registered = 1 WHERE event_id = ? AND enrollment = ?",
                (event["id"], enrollment),
            )
        return jsonify({"success": True, "path": str(face_path)})

    @app.post("/api/verify")
    def verify():
        payload = request.get_json(silent=True) or {}
        enrollment = str(payload.get("enrollment", "")).strip()
        image_data = payload.get("image_data")
        if not enrollment or not image_data:
            return jsonify({"error": "enrollment and image_data are required"}), 400
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "No active event"}), 400
            member = get_member(conn, event["id"], enrollment)
            if not member:
                return jsonify({"error": "Not registered for this event"}), 404
            if member["already_marked"]:
                return jsonify({"error": "Attendance already marked"}), 409
            reference_path = ensure_face_dir() / f"{enrollment}.jpg"
            if not reference_path.exists():
                return jsonify({"error": "Face not registered yet"}), 400
            temp_dir = Path(tempfile.gettempdir())
            probe_path = temp_dir / f"{enrollment}.jpg"
            probe_path.write_bytes(decode_data_url(image_data))
            matched, face_score, mode = verifier.verify(probe_path, reference_path)
            conn.execute(
                """
                INSERT INTO verification_sessions(event_id, enrollment, verified, face_score, location_allowed, updated_at)
                VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(event_id, enrollment)
                DO UPDATE SET verified = excluded.verified, face_score = excluded.face_score, updated_at = excluded.updated_at
                """,
                (event["id"], enrollment, 1 if matched else 0, face_score, now_ist_iso()),
            )
        return jsonify({"matched": matched, "confidence": round(face_score, 2), "mode": mode})

    @app.post("/api/mark")
    def mark_attendance():
        payload = request.get_json(silent=True) or {}
        enrollment = str(payload.get("enrollment", "")).strip()
        method = str(payload.get("method", "biometric")).strip() or "biometric"
        admin_note = str(payload.get("admin_note", "")).strip() or None
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "No active event"}), 400
            member = get_member(conn, event["id"], enrollment)
            if not member:
                return jsonify({"error": "Not registered for this event"}), 404
            if member["already_marked"]:
                return jsonify({"error": "Attendance already marked"}), 409
            if method == "manual":
                if not admin_logged_in():
                    return jsonify({"error": "Admin login required for manual override"}), 401
                if not admin_note:
                    return jsonify({"error": "admin_note is required for manual override"}), 400
            else:
                verification = conn.execute(
                    "SELECT * FROM verification_sessions WHERE event_id = ? AND enrollment = ?",
                    (event["id"], enrollment),
                ).fetchone()
                if not verification or not verification["verified"]:
                    return jsonify({"error": "Face verification required"}), 400
            device_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            conn.execute(
                """
                INSERT INTO attendance(event_id, enrollment, timestamp_ist, method, device_ip, admin_note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event["id"], enrollment, now_ist_iso(), method, device_ip, admin_note),
            )
        return jsonify({"success": True})

    @app.get("/api/attendance")
    @require_admin
    def attendance():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"event": None, "attendance": []})
            rows = conn.execute(
                """
                SELECT a.*, m.name, m.department, m.course, m.institute
                FROM attendance a
                JOIN members m ON m.event_id = a.event_id AND m.enrollment = a.enrollment
                WHERE a.event_id = ?
                ORDER BY a.timestamp_ist DESC
                """,
                (event["id"],),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS count FROM members WHERE event_id = ?", (event["id"],)).fetchone()
        return jsonify({"event": dict(event), "attendance": [dict(row) for row in rows], "total_members": total["count"]})

    @app.get("/api/export")
    @require_admin
    def export_attendance():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "No active event"}), 400
            rows = conn.execute(
                """
                SELECT m.enrollment, m.name, m.department, m.course, a.timestamp_ist, a.method, a.admin_note
                FROM attendance a
                JOIN members m ON m.event_id = a.event_id AND m.enrollment = a.enrollment
                WHERE a.event_id = ?
                ORDER BY a.timestamp_ist ASC
                """,
                (event["id"],),
            ).fetchall()
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Attendance"
        sheet.append(["Enrollment", "Name", "Department", "Course", "Timestamp IST", "Method", "Admin Note"])
        for row in rows:
            sheet.append(
                [
                    row["enrollment"],
                    row["name"],
                    row["department"],
                    row["course"],
                    row["timestamp_ist"],
                    row["method"],
                    row["admin_note"],
                ]
            )
        export_path = Path(tempfile.gettempdir()) / "attendance_export.xlsx"
        workbook.save(export_path)
        return send_file(export_path, as_attachment=True, download_name="attendance_export.xlsx")

    @app.post("/api/reset-session")
    @require_admin
    def reset_session():
        with connect() as conn:
            event = get_active_event(conn)
            if not event:
                return jsonify({"error": "No active event"}), 400
            conn.execute("DELETE FROM verification_sessions WHERE event_id = ?", (event["id"],))
        return jsonify({"success": True})

    return app

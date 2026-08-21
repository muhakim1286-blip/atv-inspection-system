#!/usr/bin/env python3
"""
ATV Inspection System - FastAPI Backend
Handles form submissions, database storage, photo uploads, and predictive maintenance alerts
"""

import os
import base64
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# ==================== CONFIG ====================

ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",")]
SESSION_DAYS = 7
PBKDF2_ITERATIONS = 260000
DB_PATH = os.environ.get("DB_PATH", "atv_inspections.db")
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", "uploads"))
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8MB per photo after client-side compression

UPLOADS_DIR.mkdir(exist_ok=True)

FLEET = [
    {"atv_id": "New1", "display_name": "New 1"},
    {"atv_id": "New2", "display_name": "New 2"},
    {"atv_id": "New3", "display_name": "New 3"},
    {"atv_id": "New4", "display_name": "New 4"},
    {"atv_id": "New5", "display_name": "New 5"},
    {"atv_id": "New6", "display_name": "New 6"},
    {"atv_id": "Gova7", "display_name": "Gova (7)"},
    {"atv_id": "Syafiq8", "display_name": "Syafiq (8)"},
    {"atv_id": "Mike9", "display_name": "Mike (9)"},
    {"atv_id": "Mirza10", "display_name": "Mirza (10)"},
    {"atv_id": "Ummu11", "display_name": "Ummu (11)"},
    {"atv_id": "Ira12", "display_name": "Ira (12)"},
    {"atv_id": "Vernon13", "display_name": "Vernon (13)"},
]
FLEET_NAMES = {atv["atv_id"]: atv["display_name"] for atv in FLEET}

# Initialize FastAPI app
app = FastAPI(title="ATV Inspection API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ==================== AUTH ====================
# Staff submissions are intentionally open (no login) - only the admin dashboard is gated,
# with named email+password accounts (see the create-user / list-users / reset-password CLI below).

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt, hash_hex = stored_hash.split('$')
        dk = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return secrets.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False

async def require_admin_key(authorization: str = Header(default="")) -> str:
    """Validates the session token and returns the logged-in admin's email."""
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT email, expires_at FROM sessions WHERE token = ?', (token,))
    row = c.fetchone()
    conn.close()

    if not row or datetime.fromisoformat(row[1]) < datetime.now():
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return row[0]

# ==================== DATA MODELS ====================

class LoginRequest(BaseModel):
    email: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class InspectionData(BaseModel):
    """Inspection form data from staff"""
    date: str
    staff_name: str
    atv_id: str
    engine_check: Optional[bool] = None
    brakes_check: Optional[bool] = None
    tires_check: Optional[bool] = None
    lights_check: Optional[bool] = None
    throttle_check: Optional[bool] = None
    acceleration_check: Optional[bool] = None
    steering_check: Optional[bool] = None
    noises_check: Optional[bool] = None
    overall_condition: str
    remarks: str = ""
    photos: Dict[str, Optional[str]] = {}

# ==================== DATABASE SETUP ====================

def init_database():
    """Create database tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id TEXT UNIQUE,
            date TEXT,
            staff_name TEXT,
            atv_id TEXT,
            engine_check BOOLEAN,
            brakes_check BOOLEAN,
            tires_check BOOLEAN,
            lights_check BOOLEAN,
            throttle_check BOOLEAN,
            acceleration_check BOOLEAN,
            steering_check BOOLEAN,
            noises_check BOOLEAN,
            overall_condition TEXT,
            remarks TEXT,
            submitted_at TEXT,
            locked BOOLEAN DEFAULT 1,
            immutable BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspection_id TEXT,
            type TEXT,
            timestamp TEXT,
            file_path TEXT,
            file_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(inspection_id) REFERENCES inspections(inspection_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT UNIQUE,
            atv_id TEXT,
            inspection_id TEXT,
            issue_type TEXT,
            severity TEXT,
            probability FLOAT,
            recommendation TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved BOOLEAN DEFAULT 0,
            resolved_at TIMESTAMP,
            resolved_by TEXT,
            FOREIGN KEY(inspection_id) REFERENCES inspections(inspection_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    ''')

    # Migration: alerts table may pre-date the resolved_by column
    c.execute("PRAGMA table_info(alerts)")
    if 'resolved_by' not in [col[1] for col in c.fetchall()]:
        c.execute("ALTER TABLE alerts ADD COLUMN resolved_by TEXT")

    conn.commit()
    conn.close()

# ==================== HELPER FUNCTIONS ====================

SEVERITY_ORDER = "CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END"

def save_photo(inspection_id: str, photo_type: str, data_url: Optional[str]):
    """Decode a base64 data URL photo and save it to disk. Returns (filename, file_hash) or None."""
    if not data_url or not data_url.startswith("data:image"):
        return None

    try:
        header, b64data = data_url.split(",", 1)
        raw = base64.b64decode(b64data)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(status_code=400, detail=f"Invalid photo data for '{photo_type}'")

    if len(raw) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=400, detail=f"Photo '{photo_type}' too large (max 8MB)")

    ext = "png" if "png" in header else "jpg"
    filename = f"{inspection_id}_{photo_type}.{ext}"
    (UPLOADS_DIR / filename).write_bytes(raw)
    file_hash = hashlib.sha256(raw).hexdigest()
    return filename, file_hash

def generate_alerts(data: InspectionData, inspection_id: str, atv_id: str) -> List[dict]:
    """Generate predictive maintenance alerts"""
    alerts = []

    if data.brakes_check is False:
        alerts.append({
            "alert_id": f"ALR-{inspection_id}-BRAKES",
            "issue_type": "brakes_critical",
            "severity": "CRITICAL",
            "probability": 1.0,
            "recommendation": "DO NOT OPERATE - Brake system failure detected"
        })

    if data.steering_check is False:
        alerts.append({
            "alert_id": f"ALR-{inspection_id}-STEERING",
            "issue_type": "steering_critical",
            "severity": "CRITICAL",
            "probability": 1.0,
            "recommendation": "DO NOT OPERATE - Steering malfunction detected"
        })

    if data.engine_check is False:
        alerts.append({
            "alert_id": f"ALR-{inspection_id}-ENGINE",
            "issue_type": "engine_failure",
            "severity": "CRITICAL",
            "probability": 1.0,
            "recommendation": "Engine failure - Repair before next use"
        })

    if data.throttle_check is False:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        c.execute('SELECT COUNT(*) FROM inspections WHERE atv_id = ? AND throttle_check = 0 AND date >= ?', (atv_id, week_ago))
        throttle_count = c.fetchone()[0]
        conn.close()

        if throttle_count >= 2:
            alerts.append({
                "alert_id": f"ALR-{inspection_id}-THROTTLE",
                "issue_type": "throttle_deteriorating",
                "severity": "HIGH",
                "probability": 0.75,
                "recommendation": "Throttle failing - Schedule repair TODAY"
            })
        elif throttle_count == 1:
            alerts.append({
                "alert_id": f"ALR-{inspection_id}-THROTTLE",
                "issue_type": "throttle_issue",
                "severity": "MEDIUM",
                "probability": 0.5,
                "recommendation": "Throttle stiff - Monitor and repair within 48 hours"
            })

    if data.noises_check is False:
        alerts.append({
            "alert_id": f"ALR-{inspection_id}-NOISE",
            "issue_type": "engine_noise",
            "severity": "HIGH",
            "probability": 0.6,
            "recommendation": "Engine knocking detected - Get diagnostic within 24 hours"
        })

    if data.overall_condition == "unsafe":
        alerts.append({
            "alert_id": f"ALR-{inspection_id}-UNSAFE",
            "issue_type": "unsafe_operation",
            "severity": "CRITICAL",
            "probability": 1.0,
            "recommendation": "ATV marked UNSAFE - Do not operate until repairs completed"
        })

    return alerts

# ==================== ENDPOINTS ====================

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_database()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]
    conn.close()
    if user_count == 0:
        print("WARNING: No admin users exist yet. Run: python backend_main.py create-user <email> <password>")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "version": "1.1.0",
        "message": "ATV Inspection API is running",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/health")
async def health():
    """Health check for monitoring"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/fleet")
async def get_fleet():
    """List configured ATVs (public - used by the staff form)"""
    return {"count": len(FLEET), "fleet": FLEET}

@app.post("/api/auth/login")
async def login(data: LoginRequest):
    email = data.email.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT password_hash FROM users WHERE email = ?', (email,))
    row = c.fetchone()

    if not row or not verify_password(data.password, row[0]):
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat()
    c.execute('INSERT INTO sessions (token, email, expires_at) VALUES (?, ?, ?)', (token, email, expires_at))
    conn.commit()
    conn.close()

    return {"token": token, "email": email, "expires_at": expires_at}

@app.post("/api/auth/logout")
async def logout(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM sessions WHERE token = ?', (token,))
    conn.commit()
    conn.close()
    return {"status": "logged_out"}

@app.get("/api/auth/me")
async def me(admin_email: str = Depends(require_admin_key)):
    return {"email": admin_email}

@app.post("/api/auth/change-password")
async def change_password(data: ChangePasswordRequest, admin_email: str = Depends(require_admin_key)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT password_hash FROM users WHERE email = ?', (admin_email,))
    row = c.fetchone()

    if not row or not verify_password(data.current_password, row[0]):
        conn.close()
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    c.execute('UPDATE users SET password_hash = ? WHERE email = ?', (hash_password(data.new_password), admin_email))
    conn.commit()
    conn.close()
    return {"status": "password_changed"}

@app.post("/api/inspections/submit")
async def submit_inspection(data: InspectionData):
    """
    Receive inspection form submission from staff
    - Validate data
    - Store in database (locked & immutable)
    - Save uploaded photos
    - Generate predictive maintenance alerts
    - Return confirmation
    """
    try:
        inspection_id = f"INS-{data.date.replace('-', '')}-{data.atv_id.replace('-', '')}-{int(datetime.now().timestamp() * 1000) % 10000:04d}"

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute('''
            INSERT INTO inspections
            (inspection_id, date, staff_name, atv_id, engine_check, brakes_check,
             tires_check, lights_check, throttle_check, acceleration_check,
             steering_check, noises_check, overall_condition, remarks, submitted_at, locked, immutable)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
        ''', (
            inspection_id, data.date, data.staff_name, data.atv_id,
            data.engine_check, data.brakes_check, data.tires_check, data.lights_check,
            data.throttle_check, data.acceleration_check, data.steering_check, data.noises_check,
            data.overall_condition, data.remarks, datetime.now().isoformat()
        ))

        for photo_type, data_url in data.photos.items():
            saved = save_photo(inspection_id, photo_type, data_url)
            if saved:
                filename, file_hash = saved
                c.execute('''
                    INSERT INTO photos (inspection_id, type, timestamp, file_path, file_hash)
                    VALUES (?, ?, ?, ?, ?)
                ''', (inspection_id, photo_type, datetime.now().isoformat(), filename, file_hash))

        alerts = generate_alerts(data, inspection_id, data.atv_id)

        for alert in alerts:
            c.execute('''
                INSERT INTO alerts (alert_id, atv_id, inspection_id, issue_type, severity, probability, recommendation)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                alert['alert_id'], data.atv_id, inspection_id, alert['issue_type'],
                alert['severity'], alert['probability'], alert['recommendation']
            ))

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "inspection_id": inspection_id,
            "message": "Inspection submitted and locked",
            "locked": True,
            "immutable": True,
            "alerts_generated": len(alerts),
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/inspections")
async def get_inspections(limit: int = 100, atv_id: Optional[str] = None, _: str = Depends(require_admin_key)):
    """Retrieve inspection records"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if atv_id:
            c.execute('SELECT * FROM inspections WHERE atv_id = ? ORDER BY submitted_at DESC LIMIT ?', (atv_id, limit))
        else:
            c.execute('SELECT * FROM inspections ORDER BY submitted_at DESC LIMIT ?', (limit,))

        columns = [desc[0] for desc in c.description]
        records = [dict(zip(columns, row)) for row in c.fetchall()]
        for r in records:
            r["display_name"] = FLEET_NAMES.get(r["atv_id"], r["atv_id"])
        conn.close()

        return {"count": len(records), "records": records}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/inspections/{inspection_id}")
async def get_inspection_detail(inspection_id: str, _: str = Depends(require_admin_key)):
    """Retrieve a single inspection with its photos and alerts"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('SELECT * FROM inspections WHERE inspection_id = ?', (inspection_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Inspection not found")

    columns = [desc[0] for desc in c.description]
    record = dict(zip(columns, row))
    record["display_name"] = FLEET_NAMES.get(record["atv_id"], record["atv_id"])

    c.execute('SELECT type, file_path, timestamp FROM photos WHERE inspection_id = ?', (inspection_id,))
    record["photos"] = [{"type": t, "url": f"/uploads/{fp}", "timestamp": ts} for t, fp, ts in c.fetchall()]

    c.execute(f'SELECT * FROM alerts WHERE inspection_id = ? ORDER BY {SEVERITY_ORDER}', (inspection_id,))
    acolumns = [desc[0] for desc in c.description]
    record["alerts"] = [dict(zip(acolumns, r)) for r in c.fetchall()]

    conn.close()
    return record

@app.get("/api/alerts")
async def get_alerts(unresolved_only: bool = True, _: str = Depends(require_admin_key)):
    """Get predictive maintenance alerts, most severe first"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if unresolved_only:
            c.execute(f'SELECT * FROM alerts WHERE resolved = 0 ORDER BY {SEVERITY_ORDER}, probability DESC, created_at DESC')
        else:
            c.execute(f'SELECT * FROM alerts ORDER BY resolved ASC, {SEVERITY_ORDER}, created_at DESC LIMIT 200')

        columns = [desc[0] for desc in c.description]
        records = [dict(zip(columns, row)) for row in c.fetchall()]
        for r in records:
            r["display_name"] = FLEET_NAMES.get(r["atv_id"], r["atv_id"])
        conn.close()

        return {"count": len(records), "alerts": records}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/api/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, admin_email: str = Depends(require_admin_key)):
    """Mark an alert as resolved"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'UPDATE alerts SET resolved = 1, resolved_at = ?, resolved_by = ? WHERE alert_id = ?',
        (datetime.now().isoformat(), admin_email, alert_id)
    )
    updated = c.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"status": "resolved", "alert_id": alert_id}

@app.get("/api/dashboard/summary")
async def dashboard_summary(_: str = Depends(require_admin_key)):
    """Get summary for admin dashboard"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")

        c.execute("SELECT COUNT(*) FROM inspections WHERE date = ?", (today,))
        total_today = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM inspections WHERE date = ? AND overall_condition = ?", (today, "ready"))
        ready_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM inspections WHERE date = ? AND overall_condition = ?", (today, "issues"))
        issues_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM inspections WHERE date = ? AND overall_condition = ?", (today, "unsafe"))
        unsafe_count = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM alerts WHERE resolved = 0")
        unresolved_alerts = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM alerts WHERE resolved = 0 AND severity = 'CRITICAL'")
        critical_alerts = c.fetchone()[0]

        c.execute("SELECT COUNT(DISTINCT staff_name) FROM inspections WHERE date = ?", (today,))
        staff_today = c.fetchone()[0]

        c.execute("SELECT submitted_at FROM inspections ORDER BY submitted_at DESC LIMIT 1")
        latest = c.fetchone()

        conn.close()

        return {
            "date": today,
            "total_inspections": total_today,
            "total_fleet": len(FLEET),
            "ready": ready_count,
            "issues": issues_count,
            "unsafe": unsafe_count,
            "unresolved_alerts": unresolved_alerts,
            "critical_alerts": critical_alerts,
            "staff_active_today": staff_today,
            "latest_submission": latest[0] if latest else None,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/dashboard/atv-status")
async def atv_status(_: str = Depends(require_admin_key)):
    """Get current status of every ATV in the fleet (including ones not yet checked today)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")

        c.execute('''
            SELECT atv_id, overall_condition, submitted_at, remarks, staff_name
            FROM inspections WHERE date = ? ORDER BY atv_id, submitted_at DESC
        ''', (today,))

        records = c.fetchall()
        conn.close()

        status_by_atv = {}
        for atv_id, condition, submitted_at, remarks, staff_name in records:
            if atv_id not in status_by_atv:
                status_by_atv[atv_id] = {
                    "atv_id": atv_id,
                    "status": condition,
                    "last_checked": submitted_at,
                    "notes": remarks,
                    "staff": staff_name
                }

        result = []
        for atv in FLEET:
            aid = atv["atv_id"]
            if aid in status_by_atv:
                entry = dict(status_by_atv[aid])
            else:
                entry = {"atv_id": aid, "status": "not_checked", "last_checked": None, "notes": None, "staff": None}
            entry["display_name"] = atv["display_name"]
            result.append(entry)

        return {"count": len(result), "atv_status": result}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ==================== USER MANAGEMENT CLI ====================
# There is no open signup endpoint (that would let anyone register as admin).
# Manage the small set of admin accounts from the command line instead:
#   python backend_main.py create-user <email> <password>
#   python backend_main.py reset-password <email> <new-password>
#   python backend_main.py list-users
#   python backend_main.py remove-user <email>
# On Render, run these from the service's Shell tab (available on paid plans).

def _run_cli(argv):
    init_database()
    command = argv[1]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if command == "create-user":
        if len(argv) != 4:
            print("Usage: python backend_main.py create-user <email> <password>")
            return 1
        email = argv[2].strip().lower()
        password = argv[3]
        if len(password) < 8:
            print("Password must be at least 8 characters")
            return 1
        try:
            c.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', (email, hash_password(password)))
            conn.commit()
            print(f"Created admin user: {email}")
        except sqlite3.IntegrityError:
            print(f"A user with email {email} already exists. Use reset-password to change their password.")
            return 1

    elif command == "reset-password":
        if len(argv) != 4:
            print("Usage: python backend_main.py reset-password <email> <new-password>")
            return 1
        email = argv[2].strip().lower()
        password = argv[3]
        if len(password) < 8:
            print("Password must be at least 8 characters")
            return 1
        c.execute('UPDATE users SET password_hash = ? WHERE email = ?', (hash_password(password), email))
        if c.rowcount == 0:
            print(f"No user found with email {email}")
            return 1
        conn.commit()
        print(f"Password updated for {email}")

    elif command == "remove-user":
        if len(argv) != 3:
            print("Usage: python backend_main.py remove-user <email>")
            return 1
        email = argv[2].strip().lower()
        c.execute('DELETE FROM users WHERE email = ?', (email,))
        c.execute('DELETE FROM sessions WHERE email = ?', (email,))
        conn.commit()
        print(f"Removed user (if they existed): {email}")

    elif command == "list-users":
        c.execute('SELECT email, created_at FROM users ORDER BY created_at')
        rows = c.fetchall()
        if not rows:
            print("No admin users yet.")
        for email, created_at in rows:
            print(f"  {email}  (created {created_at})")

    else:
        print(f"Unknown command: {command}")
        print("Usage: python backend_main.py [create-user|reset-password|remove-user|list-users] ...")
        return 1

    conn.close()
    return 0

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sys.exit(_run_cli(sys.argv))

    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("ATV Inspection API starting...")
    print(f"API docs: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)

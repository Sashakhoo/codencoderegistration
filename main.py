"""
codencode.my — Registration Backend
====================================
Receives student registration JSON, generates a PDF summary,
emails it to the student + codencodemy@gmail.com via Brevo API.

Deploy on Railway. Set these environment variables:
  BREVO_API_KEY   your Brevo API key (xkeysib-...)
  FROM_EMAIL      e.g. codencodemy@gmail.com
  FROM_NAME       e.g. codencode Academy
  TO_EMAIL        e.g. codencodemy@gmail.com
  ALLOWED_ORIGIN  e.g. https://codencode.my
"""

import os
import io
import base64
import logging
import sqlite3
import requests
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────────────
app = FastAPI(title="codencode Registration API", version="2.0.0")

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "http://localhost", "http://127.0.0.1"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────
BREVO_API_KEY  = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL     = os.getenv("FROM_EMAIL", "codencodemy@gmail.com")
FROM_NAME      = os.getenv("FROM_NAME",  "CODE N CODE Academy")
TO_EMAIL       = os.getenv("TO_EMAIL",   "codencodemy@gmail.com")
BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

# QR code path — embed as base64 at startup so it works in Railway
QR_B64 = None
QR_PATH_LOCAL = "/app/duitnow_qr.jpeg"   # put the QR image in your repo root as duitnow_qr.png
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("WORKSHOP_DB", BASE_DIR / "workshop.db"))


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows(cur):
    return [dict(row) for row in cur.fetchall()]


def row(cur):
    item = cur.fetchone()
    return dict(item) if item else None


def init_workshop_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS workshops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                emoji TEXT DEFAULT '📚',
                description TEXT DEFAULT '',
                workshop_date TEXT NOT NULL,
                time_start TEXT DEFAULT '09:00',
                time_end TEXT DEFAULT '17:00',
                location TEXT DEFAULT '',
                location_type TEXT DEFAULT 'physical',
                language TEXT DEFAULT 'English',
                color_theme TEXT DEFAULT 'python',
                recurrence TEXT DEFAULT 'none',
                published INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS workshop_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                material_type TEXT NOT NULL DEFAULT 'pdf',
                icon TEXT DEFAULT '📄',
                file_size TEXT DEFAULT '',
                duration TEXT DEFAULT '',
                section TEXT DEFAULT 'Materials',
                download_url TEXT DEFAULT '#',
                sort_order INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS workshop_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
                time_slot TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS workshop_announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
                icon TEXT DEFAULT '📢',
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS workshop_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
                student_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT DEFAULT '',
                age_range TEXT DEFAULT '',
                occupation TEXT DEFAULT '',
                industry TEXT DEFAULT '',
                experience_level TEXT DEFAULT '',
                motivation TEXT DEFAULT '',
                preferred_language TEXT DEFAULT 'English',
                referral_source TEXT DEFAULT '',
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (workshop_id, email)
            );

            CREATE TABLE IF NOT EXISTS workshop_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workshop_id INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
                material_id INTEGER NOT NULL REFERENCES workshop_materials(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                completed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (material_id, email)
            );
            """
        )

        count = conn.execute("SELECT COUNT(*) AS c FROM workshops").fetchone()["c"]
        if count:
            conn.execute(
                """
                UPDATE workshops
                SET workshop_date = '2026-06-16'
                WHERE title LIKE 'Foon Yew Evening School%'
                  AND workshop_date IN ('2026-05-27', '2026-05-26')
                """
            )
            return

        workshops = [
            ("Python for Beginners — One Day Bootcamp", "🐍", "A hands-on full-day Python bootcamp for absolute beginners.", "2026-05-31", "09:00", "17:00", "codencode KL", "physical", "English", "python", "none", 1),
            ("Intro to Machine Learning Workshop", "🤖", "Hands-on ML with sklearn and real Malaysian datasets.", "2026-06-14", "09:00", "17:00", "codencode JB", "physical", "English / BM", "ml", "none", 1),
            ("Vibe Coding with AI Tools", "✨", "Build full-stack apps fast using AI tools, GitHub, and modern deployment workflows.", "2026-06-28", "10:00", "16:00", "Online (Zoom)", "online", "English / 中文", "vibe", "none", 1),
            ("Python for Data Analysis", "📊", "Analyze real datasets with pandas, notebooks, and visualisation tools.", "2026-07-12", "09:00", "17:00", "codencode KL", "physical", "English", "data", "none", 1),
            ("Foon Yew Evening School — Python Night", "🌙", "Weekly 2-hour Python evening class for Foon Yew students.", "2026-06-16", "19:30", "21:30", "Foon Yew High School, JB", "physical", "中文 / EN", "eve", "weekly", 1),
        ]
        conn.executemany(
            """
            INSERT INTO workshops
            (title, emoji, description, workshop_date, time_start, time_end, location, location_type, language, color_theme, recurrence, published)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            workshops,
        )
        seed_materials = [
            (1, "Full Workshop Slide Deck", "slide", "🗂", "8.2 MB", "60 slides", "Materials", "#", 1),
            (1, "Python Basics Notes", "pdf", "📄", "1.1 MB", "12 pages", "Materials", "#", 2),
            (1, "Exercise Files (.zip)", "code", "💻", "34 KB", "5 exercises", "Materials", "#", 3),
            (2, "ML Workshop Full Slides", "slide", "🗂", "11.4 MB", "72 slides", "Materials", "#", 1),
            (2, "Jupyter Notebooks Pack (.zip)", "code", "💻", "280 KB", "6 notebooks", "Materials", "#", 2),
            (3, "Vibe Coding Workshop Slides", "slide", "🗂", "6.8 MB", "48 slides", "Materials", "#", 1),
            (3, "Starter Templates (.zip)", "code", "💻", "45 KB", "3 templates", "Materials", "#", 2),
            (4, "Data Analysis Workshop Slides", "slide", "🗂", "9.6 MB", "66 slides", "Materials", "#", 1),
            (4, "Workshop Datasets (.zip)", "code", "💻", "4.1 MB", "3 CSV files", "Materials", "#", 2),
            (5, "Week 1 — Python Basics (Slides)", "slide", "🗂", "3.2 MB", "28 slides", "Week 1", "#", 1),
            (5, "Week 1 — Notes & Exercises", "pdf", "📄", "0.8 MB", "8 pages", "Week 1", "#", 2),
        ]
        conn.executemany(
            """
            INSERT INTO workshop_materials
            (workshop_id, name, material_type, icon, file_size, duration, section, download_url, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed_materials,
        )
        seed_schedule = [
            (1, "09:00 AM", "Welcome & Setup", "Intro, icebreakers, Python install check", 1),
            (1, "10:00 AM", "Python Basics", "Variables, data types, print/input, f-strings", 2),
            (1, "02:00 PM", "Mini Project Build", "Build your own simple Python program", 3),
            (2, "09:00 AM", "Intro to AI & ML", "What is ML? Types, real-world use cases", 1),
            (3, "10:00 AM", "Intro to Vibe Coding", "AI-assisted workflow and project setup", 1),
            (4, "09:00 AM", "Pandas Deep Dive", "DataFrames, filtering, groupby, merge", 1),
            (5, "7:30 PM", "Recap & Warm-up", "Quick review of last week's content", 1),
        ]
        conn.executemany(
            "INSERT INTO workshop_schedule (workshop_id, time_slot, title, description, sort_order) VALUES (?, ?, ?, ?, ?)",
            seed_schedule,
        )
        seed_announcements = [
            (1, "📢", "Welcome!", "Bring your laptop with Python 3.11+ installed."),
            (2, "💡", "Pre-requisite", "Basic Python is helpful. Complete the pre-reading before attending."),
            (3, "🔗", "Zoom Link", "Your link will be emailed before the workshop."),
            (4, "📊", "Dataset Access", "Exercise datasets are included in the materials list."),
            (5, "🌙", "Weekly Session", "Materials update before each Tuesday class."),
        ]
        conn.executemany(
            "INSERT INTO workshop_announcements (workshop_id, icon, title, body) VALUES (?, ?, ?, ?)",
            seed_announcements,
        )


init_workshop_db()

# ── Pydantic model ───────────────────────────────────────────────
class Registration(BaseModel):
    full_name:          str
    whatsapp:           str
    email:              str
    occupation:         str
    language:           str
    experience_level:   str
    referral_source:    str = ""
    learning_goals:     str
    course:             str
    class_format:       str
    total_fee:          str
    payment_preference: str
    instalment_week1:   str = ""
    instalment_week3:   str = ""
    timing:             str


class WorkshopRegistration(BaseModel):
    workshop_id: int
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    age_range: str = ""
    occupation: str
    industry: str = ""
    experience_level: str
    motivation: str
    preferred_language: str = "English"
    referral_source: str = ""


class WorkshopPayload(BaseModel):
    title: str
    emoji: str = "📚"
    description: str = ""
    workshop_date: str
    time_start: str = "09:00"
    time_end: str = "17:00"
    location: str = ""
    location_type: str = "physical"
    language: str = "English"
    color_theme: str = "python"
    recurrence: str = "none"
    published: bool = False


class MaterialPayload(BaseModel):
    name: str
    material_type: str = "pdf"
    icon: str = "📄"
    file_size: str = ""
    duration: str = ""
    section: str = "Materials"
    download_url: str = "#"


class SchedulePayload(BaseModel):
    time_slot: str
    title: str
    description: str = ""
    sort_order: int = 1


class AnnouncementPayload(BaseModel):
    icon: str = "📢"
    title: str
    body: str


class ProgressPayload(BaseModel):
    email: str
    completed: bool = True


# ── Brand Colors ──────────────────────────────────────────────────
BG        = colors.HexColor("#080c10")
SURF      = colors.HexColor("#0d1117")
SURF2     = colors.HexColor("#0a0f14")
CYAN      = colors.HexColor("#00dcb4")
CYAN_DIM  = colors.HexColor("#003d33")
GOLD      = colors.HexColor("#f5c842")
WHITE     = colors.HexColor("#e8edf3")
MID       = colors.HexColor("#5a6a7a")
BORDER2   = colors.HexColor("#243040")
RED       = colors.HexColor("#ff4d4d")
RED_DIM   = colors.HexColor("#2a0a0a")
PINK      = colors.HexColor("#ff2d7a")
AMBER     = colors.HexColor("#ffb347")
AMBER_DIM = colors.HexColor("#2a1a00")

W, H = A4


# ── PDF Builder ───────────────────────────────────────────────────
def build_pdf(reg: Registration) -> bytes:
    buffer = io.BytesIO()
    cv = canvas.Canvas(buffer, pagesize=A4)

    now = datetime.now()
    ref = f"CCR-{now.strftime('%Y%m%d%H%M%S')}"
    submitted = now.strftime("%d %b %Y, %I:%M %p")

    # PAGE BACKGROUND
    cv.setFillColor(BG)
    cv.rect(0, 0, W, H, fill=1, stroke=0)

    # Dot grid
    cv.setFillColor(colors.HexColor("#0d1117"))
    for x in range(int(14*mm), int(W - 14*mm), 12):
        for y_dot in range(int(14*mm), int(H - 60*mm), 12):
            cv.circle(x, y_dot, 0.6, fill=1, stroke=0)

    # HEADER
    hdr_h = 50*mm
    cv.setFillColor(SURF)
    cv.rect(0, H - hdr_h, W, hdr_h, fill=1, stroke=0)
    cv.setFillColor(CYAN)
    cv.rect(0, H - 3, W, 3, fill=1, stroke=0)
    cv.setFillColor(GOLD)
    cv.rect(0, H - hdr_h, 5, hdr_h, fill=1, stroke=0)

    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 30)
    cv.drawString(16*mm, H - 21*mm, "code")
    cv.setFillColor(CYAN)
    cv.drawString(16*mm + 69, H - 21*mm, ".ncode")
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 8.5)
    cv.drawString(16*mm, H - 28*mm, "STUDENT REGISTRATION SUMMARY")

    cv.setFillColor(MID)
    cv.setFont("Helvetica", 8.5)
    cv.drawRightString(W - 16*mm, H - 17*mm, f"REF: {ref}")
    cv.setFillColor(colors.HexColor("#3a4a5a"))
    cv.setFont("Helvetica", 8)
    cv.drawRightString(W - 16*mm, H - 24*mm, submitted)

    bx, by, bw, bh = W - 68*mm, H - 42*mm, 52*mm, 10*mm
    cv.setFillColor(CYAN_DIM)
    cv.setStrokeColor(CYAN)
    cv.setLineWidth(0.6)
    cv.roundRect(bx, by, bw, bh, 2, fill=1, stroke=1)
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawCentredString(bx + bw/2, by + 3*mm, "✓  REGISTRATION RECEIVED")

    # URGENCY BANNER
    urg_y = H - hdr_h - 14*mm
    cv.setFillColor(AMBER_DIM)
    cv.setStrokeColor(AMBER)
    cv.setLineWidth(0.8)
    cv.rect(14*mm, urg_y, W - 28*mm, 11*mm, fill=1, stroke=1)
    cv.setFillColor(AMBER)
    cv.rect(14*mm, urg_y, 4, 11*mm, fill=1, stroke=0)
    cv.setFillColor(AMBER)
    cv.setFont("Helvetica-Bold", 9.5)
    cv.drawString(21*mm, urg_y + 3.5*mm,
        "⚠  Complete payment within 7 days to secure your seat — unfilled seats will be offered to others.")

    # HELPERS
    def sec(title, y):
        cv.setFillColor(CYAN)
        cv.rect(14*mm, y - 1*mm, 3, 6*mm, fill=1, stroke=0)
        cv.setFillColor(CYAN)
        cv.setFont("Helvetica-Bold", 9)
        cv.drawString(20*mm, y, title)
        cv.setStrokeColor(BORDER2)
        cv.setLineWidth(0.5)
        cv.line(14*mm, y - 2.5*mm, W - 14*mm, y - 2.5*mm)
        return y - 8*mm

    def row(label, value, y, alt=False):
        rh = 8.5*mm
        bg = SURF if alt else SURF2
        cv.setFillColor(bg)
        cv.rect(14*mm, y - rh + 1*mm, W - 28*mm, rh, fill=1, stroke=0)
        if alt:
            cv.setFillColor(CYAN_DIM)
            cv.rect(14*mm, y - rh + 1*mm, 2.5, rh, fill=1, stroke=0)
        cv.setFillColor(MID)
        cv.setFont("Helvetica-Bold", 8.5)
        cv.drawString(19*mm, y - 4*mm, label.upper())
        cv.setFillColor(WHITE)
        cv.setFont("Helvetica", 10)
        cv.drawString(72*mm, y - 4*mm, str(value))
        return y - rh

    y = urg_y - 7*mm

    # PERSONAL
    y = sec("PERSONAL DETAILS", y)
    y = row("Full Name",   reg.full_name,        y, False)
    y = row("WhatsApp",    reg.whatsapp,          y, True)
    y = row("Email",       reg.email,             y, False)
    y = row("Occupation",  reg.occupation,        y, True)
    y = row("Language",    reg.language,          y, False)
    y = row("Experience",  reg.experience_level,  y, True)
    if reg.referral_source:
        y = row("How Found Us", reg.referral_source, y, False)
    y -= 5*mm

    # GOALS
    y = sec("LEARNING GOALS", y)
    goals = reg.learning_goals
    cv.setFillColor(SURF)
    cv.setStrokeColor(BORDER2)
    cv.setLineWidth(0.4)
    cv.roundRect(14*mm, y - 14*mm, W - 28*mm, 14*mm, 2, fill=1, stroke=1)
    cv.setFillColor(CYAN_DIM)
    cv.roundRect(14*mm, y - 14*mm, 3, 14*mm, 1, fill=1, stroke=0)
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica", 10)
    cv.drawString(19*mm, y - 5.5*mm, goals[:88])
    if len(goals) > 88:
        cv.drawString(19*mm, y - 10.5*mm, goals[88:176])
    y -= 19*mm

    # COURSE
    y = sec("COURSE & CLASS DETAILS", y)
    card_h = 22*mm
    cv.setFillColor(SURF)
    cv.setStrokeColor(CYAN)
    cv.setLineWidth(0.8)
    cv.roundRect(14*mm, y - card_h, W - 28*mm, card_h, 3, fill=1, stroke=1)
    cv.setFillColor(CYAN)
    cv.roundRect(14*mm, y - card_h, 4, card_h, 2, fill=1, stroke=0)
    cv.setFillColor(MID)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawString(21*mm, y - 5.5*mm, "COURSE")
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 14)
    cv.drawString(21*mm, y - 11*mm, reg.course)
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 9)
    cv.drawString(21*mm, y - 16.5*mm, reg.class_format)
    cv.setFillColor(MID)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawRightString(W - 16*mm, y - 5.5*mm, "TIMING")
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawRightString(W - 16*mm, y - 12*mm, reg.timing)
    y -= card_h + 6*mm

    # FEES
    y = sec("FEES & PAYMENT", y)
    cv.setFillColor(SURF2)
    cv.rect(14*mm, y - 8.5*mm, W - 28*mm, 8.5*mm, fill=1, stroke=0)
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 9)
    cv.drawString(19*mm, y - 5*mm, "Payment Plan")
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawRightString(W - 16*mm, y - 5*mm, reg.payment_preference)
    y -= 8.5*mm

    if reg.instalment_week1:
        cv.setFillColor(SURF)
        cv.rect(14*mm, y - 8.5*mm, W - 28*mm, 8.5*mm, fill=1, stroke=0)
        cv.setFillColor(MID)
        cv.setFont("Helvetica", 9)
        cv.drawString(19*mm, y - 5*mm, "Week 1 — Upon Enrolment")
        cv.setFillColor(WHITE)
        cv.setFont("Helvetica-Bold", 10)
        cv.drawRightString(W - 16*mm, y - 5*mm, reg.instalment_week1)
        y -= 8.5*mm

    if reg.instalment_week3:
        cv.setFillColor(SURF2)
        cv.rect(14*mm, y - 8.5*mm, W - 28*mm, 8.5*mm, fill=1, stroke=0)
        cv.setFillColor(MID)
        cv.setFont("Helvetica", 9)
        cv.drawString(19*mm, y - 5*mm, "Week 3 — Before 3rd Session")
        cv.setFillColor(WHITE)
        cv.setFont("Helvetica-Bold", 10)
        cv.drawRightString(W - 16*mm, y - 5*mm, reg.instalment_week3)
        y -= 8.5*mm

    # Total
    cv.setFillColor(SURF)
    cv.setStrokeColor(CYAN)
    cv.setLineWidth(0.6)
    cv.roundRect(14*mm, y - 14*mm, W - 28*mm, 14*mm, 2, fill=1, stroke=1)
    cv.setFillColor(CYAN_DIM)
    cv.roundRect(14*mm, y - 14*mm, 4, 14*mm, 2, fill=1, stroke=0)
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawString(21*mm, y - 7*mm, "TOTAL  (ONE-TIME · NO RECURRING CHARGES)")
    cv.setFillColor(GOLD)
    cv.setFont("Helvetica-Bold", 18)
    cv.drawRightString(W - 16*mm, y - 8.5*mm, reg.total_fee)
    y -= 16*mm

    if reg.instalment_week3:
        cv.setFillColor(RED_DIM)
        cv.setStrokeColor(RED)
        cv.setLineWidth(0.5)
        cv.roundRect(14*mm, y - 9*mm, W - 28*mm, 9*mm, 2, fill=1, stroke=1)
        cv.setFillColor(RED)
        cv.rect(14*mm, y - 9*mm, 3, 9*mm, fill=1, stroke=0)
        cv.setFillColor(RED)
        cv.setFont("Helvetica-Bold", 8.5)
        cv.drawString(20*mm, y - 5.5*mm,
            "Week 3 payment must be received or class will not proceed until balance is settled.")
        y -= 12*mm

    y -= 4*mm

    # HOW TO PAY
    y = sec("HOW TO PAY", y)
    panel_h = 50*mm
    cv.setFillColor(SURF)
    cv.setStrokeColor(BORDER2)
    cv.setLineWidth(0.5)
    cv.roundRect(14*mm, y - panel_h, W - 28*mm, panel_h, 3, fill=1, stroke=1)

    # QR code
    qr_size = 36*mm
    qr_x = 19*mm
    qr_y = y - panel_h + 7*mm
    try:
        cv.drawImage(QR_PATH_LOCAL, qr_x, qr_y, width=qr_size, height=qr_size,
                     preserveAspectRatio=True, mask='auto')
    except Exception:
        # Draw placeholder if QR not found
        cv.setFillColor(SURF2)
        cv.setStrokeColor(BORDER2)
        cv.rect(qr_x, qr_y, qr_size, qr_size, fill=1, stroke=1)
        cv.setFillColor(MID)
        cv.setFont("Helvetica", 7)
        cv.drawCentredString(qr_x + qr_size/2, qr_y + qr_size/2, "DuitNow QR")

    cv.setFillColor(PINK)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawCentredString(qr_x + qr_size/2, qr_y - 5*mm, "DuitNow QR")

    # Divider
    div_x = 67*mm
    cv.setStrokeColor(BORDER2)
    cv.setLineWidth(0.5)
    cv.line(div_x, y - panel_h + 5*mm, div_x, y - 4*mm)

    # Bank details
    bx = div_x + 7*mm
    by = y - 9*mm
    cv.setFillColor(MID)
    cv.setFont("Helvetica-Bold", 8)
    cv.drawString(bx, by, "BANK TRANSFER")
    by -= 7*mm
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 20)
    cv.drawString(bx, by, "MAYBANK")
    by -= 8*mm
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 8.5)
    cv.drawString(bx, by, "Account Number")
    by -= 6*mm
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 16)
    cv.drawString(bx, by, "5512 7610 6077")
    by -= 8*mm
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 8.5)
    cv.drawString(bx, by, "Account Name")
    by -= 6*mm
    cv.setFillColor(WHITE)
    cv.setFont("Helvetica-Bold", 11)
    cv.drawString(bx, by, "CODE N CODE SOLUTION")
    by -= 8*mm
    cv.setFillColor(CYAN_DIM)
    cv.setStrokeColor(CYAN)
    cv.setLineWidth(0.4)
    cv.roundRect(bx, by - 2*mm, 50*mm, 7*mm, 2, fill=1, stroke=1)
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 7.5)
    cv.drawCentredString(bx + 25*mm, by + 0.8*mm, "All Banks + e-Wallets Accepted")

    # FOOTER
    ftr_h = 18*mm
    cv.setFillColor(SURF)
    cv.rect(0, 0, W, ftr_h, fill=1, stroke=0)
    cv.setFillColor(CYAN)
    cv.rect(0, ftr_h, W, 1, fill=1, stroke=0)
    cv.setFillColor(GOLD)
    cv.rect(0, 0, W, 2, fill=1, stroke=0)
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 10)
    cv.drawString(14*mm, 12*mm, "codencode.my")
    cv.setFillColor(MID)
    cv.setFont("Helvetica", 8)
    cv.drawString(14*mm, 6.5*mm, "codencodemy@gmail.com  ·  +60 11-3165 2854  ·  KL · JB · Online Zoom")
    cv.setFillColor(CYAN_DIM)
    cv.setStrokeColor(CYAN)
    cv.setLineWidth(0.4)
    cv.roundRect(W - 88*mm, 5*mm, 74*mm, 9*mm, 2, fill=1, stroke=1)
    cv.setFillColor(CYAN)
    cv.setFont("Helvetica-Bold", 7.5)
    cv.drawCentredString(W - 51*mm, 8.2*mm, "We'll confirm your spot within 24 hours via WhatsApp")

    cv.save()
    return buffer.getvalue()


# ── Brevo Email Sender ────────────────────────────────────────────
def send_email_brevo(reg: Registration, pdf_bytes: bytes):
    now_str  = datetime.now().strftime("%d %b %Y %I:%M %p")
    ref      = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    filename = f"codencode_registration_{reg.full_name.replace(' ', '_')}.pdf"
    pdf_b64  = base64.b64encode(pdf_bytes).decode("utf-8")

    headers = {
        "accept":       "application/json",
        "content-type": "application/json",
        "api-key":      BREVO_API_KEY,
    }
    attachment = [{"content": pdf_b64, "name": filename}]

    # Admin email
    payment_lines = f"  Total         : {reg.total_fee}  (one-time)\n  Payment Plan  : {reg.payment_preference}"
    if reg.instalment_week1:
        payment_lines += f"\n  Week 1        : {reg.instalment_week1}"
    if reg.instalment_week3:
        payment_lines += f"\n  Week 3        : {reg.instalment_week3}"

    admin_text = f"""New student registration received!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reference     : {ref}
Submitted     : {now_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STUDENT DETAILS
  Name          : {reg.full_name}
  WhatsApp      : {reg.whatsapp}
  Email         : {reg.email}
  Occupation    : {reg.occupation}
  Language      : {reg.language}
  Experience    : {reg.experience_level}
  Referral      : {reg.referral_source or '—'}

COURSE & CLASS
  Course        : {reg.course}
  Format        : {reg.class_format}
  Timing        : {reg.timing}

FEES
{payment_lines}

GOALS
  {reg.learning_goals}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PDF summary attached.
"""
    r = requests.post(BREVO_SEND_URL, headers=headers, json={
        "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
        "to":          [{"email": TO_EMAIL}],
        "subject":     f"[NEW REGISTRATION] {reg.full_name} – {reg.course} – {now_str}",
        "textContent": admin_text,
        "attachment":  attachment,
    })
    if r.status_code not in (200, 201):
        raise Exception(f"Brevo admin email failed: {r.status_code} {r.text}")

    # Student email
    if "Instalment" in reg.payment_preference:
        payment_section = f"""Payment Schedule (Instalment):
  Week 1 (Upon Enrolment)      : {reg.instalment_week1}
  Week 3 (Before 3rd Session)  : {reg.instalment_week3}

  ⚠ Week 3 payment must be received or class will not proceed."""
    else:
        payment_section = f"Total (full payment) : {reg.total_fee}"

    student_text = f"""Hi {reg.full_name.split()[0]},

Thank you for registering with codencode.my! 🎉

We've received your registration and will confirm your spot within 24 hours
via WhatsApp or email.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR REGISTRATION SUMMARY
  Reference     : {ref}
  Course        : {reg.course}
  Class Format  : {reg.class_format}
  Timing        : {reg.timing}
  Language      : {reg.language}

FEES
  {payment_section}

⚠  IMPORTANT: Complete payment within 7 days to secure your seat.
   Unfilled seats will be offered to other students.

HOW TO PAY
  DuitNow QR   : Scan the QR code in the attached PDF
  Bank Transfer : Maybank  |  5512 7610 6077  |  CODE N CODE SOLUTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A full PDF summary with payment QR is attached to this email.

Questions? WhatsApp us anytime:
👉 https://wa.me/601131652854

See you in class!
Sasha & the codencode team
codencode.my  |  KL · JB · Online Zoom
"""
    r2 = requests.post(BREVO_SEND_URL, headers=headers, json={
        "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
        "to":          [{"email": reg.email, "name": reg.full_name}],
        "subject":     f"Registration Received – codencode.my ({reg.course})",
        "textContent": student_text,
        "attachment":  attachment,
    })
    if r2.status_code not in (200, 201):
        raise Exception(f"Brevo student email failed: {r2.status_code} {r2.text}")

    logger.info(f"Emails sent for {reg.full_name} ({reg.email})")


# ── Workshop Portal ───────────────────────────────────────────────
@app.get("/workshop")
def workshop_page():
    return FileResponse(BASE_DIR / "workshop.html")


@app.get("/workshop/")
def workshop_page_slash():
    return RedirectResponse("/workshop")


@app.get("/workshop/admin")
def workshop_admin_page():
    return FileResponse(BASE_DIR / "workshop_admin.html")


@app.get("/materials")
def old_materials_redirect():
    return RedirectResponse("/workshop")


@app.get("/api/workshops")
def public_workshops():
    with db() as conn:
        return rows(conn.execute(
            """
            SELECT w.*,
                   (SELECT COUNT(*) FROM workshop_materials m WHERE m.workshop_id = w.id) AS material_count
            FROM workshops w
            WHERE published = 1
            ORDER BY workshop_date, time_start
            """
        ))


def registered_workshops(conn, email: str):
    return rows(conn.execute(
        """
        SELECT w.*,
               (SELECT COUNT(*) FROM workshop_materials m WHERE m.workshop_id = w.id) AS material_count,
               (SELECT COUNT(*) FROM workshop_progress p WHERE p.workshop_id = w.id AND lower(p.email) = lower(?)) AS completed_count
        FROM workshop_registrations r
        JOIN workshops w ON w.id = r.workshop_id
        WHERE lower(r.email) = lower(?)
        ORDER BY w.workshop_date, w.time_start
        """,
        (email, email),
    ))


@app.post("/api/workshop/register")
def register_workshop(reg: WorkshopRegistration):
    full_name = f"{reg.first_name.strip()} {reg.last_name.strip()}".strip()
    with db() as conn:
        workshop = row(conn.execute("SELECT * FROM workshops WHERE id = ? AND published = 1", (reg.workshop_id,)))
        if not workshop:
            raise HTTPException(status_code=404, detail="Workshop not found or not published.")
        conn.execute(
            """
            INSERT INTO workshop_registrations
            (workshop_id, student_name, email, phone, age_range, occupation, industry, experience_level, motivation, preferred_language, referral_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workshop_id, email) DO UPDATE SET
                student_name = excluded.student_name,
                phone = excluded.phone,
                age_range = excluded.age_range,
                occupation = excluded.occupation,
                industry = excluded.industry,
                experience_level = excluded.experience_level,
                motivation = excluded.motivation,
                preferred_language = excluded.preferred_language,
                referral_source = excluded.referral_source
            """,
            (
                reg.workshop_id,
                full_name,
                str(reg.email).lower(),
                reg.phone,
                reg.age_range,
                reg.occupation,
                reg.industry,
                reg.experience_level,
                reg.motivation,
                reg.preferred_language,
                reg.referral_source,
            ),
        )
        return {
            "status": "ok",
            "student_name": full_name,
            "email": str(reg.email).lower(),
            "workshops": registered_workshops(conn, str(reg.email)),
        }


@app.get("/api/workshop/my")
def my_workshops(email: str = Query(...)):
    with db() as conn:
        return registered_workshops(conn, str(email))


@app.get("/api/workshop/workshops/{workshop_id}")
def workshop_materials(workshop_id: int, email: str = Query(...)):
    with db() as conn:
        reg = row(conn.execute(
            "SELECT * FROM workshop_registrations WHERE workshop_id = ? AND lower(email) = lower(?)",
            (workshop_id, str(email)),
        ))
        if not reg:
            raise HTTPException(status_code=403, detail="Register for this workshop before accessing materials.")
        workshop = row(conn.execute("SELECT * FROM workshops WHERE id = ?", (workshop_id,)))
        progress = rows(conn.execute("SELECT material_id FROM workshop_progress WHERE workshop_id = ? AND lower(email) = lower(?)", (workshop_id, str(email))))
        return {
            "workshop": workshop,
            "materials": rows(conn.execute("SELECT * FROM workshop_materials WHERE workshop_id = ? ORDER BY section, sort_order, id", (workshop_id,))),
            "schedule": rows(conn.execute("SELECT * FROM workshop_schedule WHERE workshop_id = ? ORDER BY sort_order, id", (workshop_id,))),
            "announcements": rows(conn.execute("SELECT * FROM workshop_announcements WHERE workshop_id = ? ORDER BY created_at DESC, id DESC", (workshop_id,))),
            "progress": [p["material_id"] for p in progress],
        }


@app.post("/api/workshop/workshops/{workshop_id}/materials/{material_id}/progress")
def update_progress(workshop_id: int, material_id: int, payload: ProgressPayload):
    with db() as conn:
        if payload.completed:
            conn.execute("INSERT OR IGNORE INTO workshop_progress (workshop_id, material_id, email) VALUES (?, ?, ?)", (workshop_id, material_id, str(payload.email).lower()))
        else:
            conn.execute("DELETE FROM workshop_progress WHERE workshop_id = ? AND material_id = ? AND lower(email) = lower(?)", (workshop_id, material_id, str(payload.email)))
        return {"status": "ok"}


@app.get("/api/admin/workshops")
def admin_workshops():
    with db() as conn:
        return rows(conn.execute(
            """
            SELECT w.*,
                   (SELECT COUNT(*) FROM workshop_registrations r WHERE r.workshop_id = w.id) AS registrant_count,
                   (SELECT COUNT(*) FROM workshop_materials m WHERE m.workshop_id = w.id) AS material_count
            FROM workshops w
            ORDER BY workshop_date DESC, id DESC
            """
        ))


@app.post("/api/admin/workshops")
def admin_create_workshop(payload: WorkshopPayload):
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO workshops
            (title, emoji, description, workshop_date, time_start, time_end, location, location_type, language, color_theme, recurrence, published)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.title, payload.emoji, payload.description, payload.workshop_date, payload.time_start, payload.time_end, payload.location, payload.location_type, payload.language, payload.color_theme, payload.recurrence, int(payload.published)),
        )
        return row(conn.execute("SELECT * FROM workshops WHERE id = ?", (cur.lastrowid,)))


@app.put("/api/admin/workshops/{workshop_id}")
def admin_update_workshop(workshop_id: int, payload: WorkshopPayload):
    with db() as conn:
        conn.execute(
            """
            UPDATE workshops SET
                title = ?, emoji = ?, description = ?, workshop_date = ?, time_start = ?, time_end = ?,
                location = ?, location_type = ?, language = ?, color_theme = ?, recurrence = ?, published = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payload.title, payload.emoji, payload.description, payload.workshop_date, payload.time_start, payload.time_end, payload.location, payload.location_type, payload.language, payload.color_theme, payload.recurrence, int(payload.published), workshop_id),
        )
        item = row(conn.execute("SELECT * FROM workshops WHERE id = ?", (workshop_id,)))
        if not item:
            raise HTTPException(status_code=404, detail="Workshop not found.")
        return item


@app.delete("/api/admin/workshops/{workshop_id}")
def admin_delete_workshop(workshop_id: int):
    with db() as conn:
        conn.execute("DELETE FROM workshops WHERE id = ?", (workshop_id,))
        return {"ok": 1}


@app.get("/api/admin/workshops/{workshop_id}/materials")
def admin_get_materials(workshop_id: int):
    with db() as conn:
        return rows(conn.execute("SELECT * FROM workshop_materials WHERE workshop_id = ? ORDER BY sort_order, id", (workshop_id,)))


@app.post("/api/admin/workshops/{workshop_id}/materials")
def admin_add_material(workshop_id: int, payload: MaterialPayload):
    with db() as conn:
        sort_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM workshop_materials WHERE workshop_id = ?", (workshop_id,)).fetchone()["n"]
        cur = conn.execute(
            """
            INSERT INTO workshop_materials
            (workshop_id, name, material_type, icon, file_size, duration, section, download_url, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (workshop_id, payload.name, payload.material_type, payload.icon, payload.file_size, payload.duration, payload.section, payload.download_url, sort_order),
        )
        return row(conn.execute("SELECT * FROM workshop_materials WHERE id = ?", (cur.lastrowid,)))


@app.put("/api/admin/workshops/{workshop_id}/materials/{material_id}")
def admin_update_material(workshop_id: int, material_id: int, payload: MaterialPayload):
    with db() as conn:
        conn.execute(
            """
            UPDATE workshop_materials SET name = ?, material_type = ?, icon = ?, file_size = ?, duration = ?, section = ?, download_url = ?
            WHERE id = ? AND workshop_id = ?
            """,
            (payload.name, payload.material_type, payload.icon, payload.file_size, payload.duration, payload.section, payload.download_url, material_id, workshop_id),
        )
        return row(conn.execute("SELECT * FROM workshop_materials WHERE id = ? AND workshop_id = ?", (material_id, workshop_id)))


@app.delete("/api/admin/workshops/{workshop_id}/materials/{material_id}")
def admin_delete_material(workshop_id: int, material_id: int):
    with db() as conn:
        conn.execute("DELETE FROM workshop_materials WHERE id = ? AND workshop_id = ?", (material_id, workshop_id))
        return {"ok": 1}


@app.get("/api/admin/workshops/{workshop_id}/schedule")
def admin_get_schedule(workshop_id: int):
    with db() as conn:
        return rows(conn.execute("SELECT * FROM workshop_schedule WHERE workshop_id = ? ORDER BY sort_order, id", (workshop_id,)))


@app.put("/api/admin/workshops/{workshop_id}/schedule")
def admin_save_schedule(workshop_id: int, items: list[SchedulePayload]):
    with db() as conn:
        conn.execute("DELETE FROM workshop_schedule WHERE workshop_id = ?", (workshop_id,))
        conn.executemany(
            "INSERT INTO workshop_schedule (workshop_id, time_slot, title, description, sort_order) VALUES (?, ?, ?, ?, ?)",
            [(workshop_id, item.time_slot, item.title, item.description, item.sort_order) for item in items],
        )
        return {"updated": len(items)}


@app.get("/api/admin/workshops/{workshop_id}/announcements")
def admin_get_announcements(workshop_id: int):
    with db() as conn:
        return rows(conn.execute("SELECT * FROM workshop_announcements WHERE workshop_id = ? ORDER BY created_at DESC, id DESC", (workshop_id,)))


@app.post("/api/admin/workshops/{workshop_id}/announcements")
def admin_add_announcement(workshop_id: int, payload: AnnouncementPayload):
    with db() as conn:
        cur = conn.execute("INSERT INTO workshop_announcements (workshop_id, icon, title, body) VALUES (?, ?, ?, ?)", (workshop_id, payload.icon, payload.title, payload.body))
        return row(conn.execute("SELECT * FROM workshop_announcements WHERE id = ?", (cur.lastrowid,)))


@app.delete("/api/admin/workshops/{workshop_id}/announcements/{announcement_id}")
def admin_delete_announcement(workshop_id: int, announcement_id: int):
    with db() as conn:
        conn.execute("DELETE FROM workshop_announcements WHERE id = ? AND workshop_id = ?", (announcement_id, workshop_id))
        return {"ok": 1}


@app.get("/api/admin/workshops/{workshop_id}/registrations")
def admin_get_registrations(workshop_id: int):
    with db() as conn:
        return rows(conn.execute("SELECT * FROM workshop_registrations WHERE workshop_id = ? ORDER BY registered_at DESC", (workshop_id,)))


# ── Endpoints ─────────────────────────────────────────────────────
@app.post("/register")
async def register(reg: Registration):
    try:
        pdf_bytes = build_pdf(reg)
        send_email_brevo(reg, pdf_bytes)
        return {"status": "ok", "message": "Registration received. Check your email!"}
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def health():
    return {"status": "ok", "service": "codencode registration API"}

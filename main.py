"""
codencode.my — Registration Backend
====================================
Receives student registration JSON, generates a PDF summary,
emails it to the student + hello@codencode.my via SMTP.

Deploy on Railway (free tier works fine).
Set these environment variables in Railway:
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       e.g. 587
  SMTP_USER       your sending email address
  SMTP_PASS       your SMTP password / app password
  FROM_EMAIL      e.g. hello@codencode.my
  TO_EMAIL        e.g. hello@codencode.my   (where YOU receive all registrations)
  ALLOWED_ORIGIN  e.g. https://codencode.my (your GitHub Pages URL)
"""

import os
import io
import sqlite3
import smtplib
import logging
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────────────
app = FastAPI(title="codencode Registration API", version="1.0.0")

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN, "http://localhost", "http://127.0.0.1"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ── Config (from env vars) ────────────────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "codencodemy@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "mlas mrnc siuc adnm")
FROM_EMAIL = os.getenv("FROM_EMAIL", "codencodemy@gmail.com")
TO_EMAIL   = os.getenv("TO_EMAIL",   "codencodemy@gmail.com")
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
            return

        workshops = [
            ("Python for Beginners — One Day Bootcamp", "🐍", "A hands-on full-day Python bootcamp for absolute beginners.", "2026-05-31", "09:00", "17:00", "codencode KL", "physical", "English", "python", "none", 1),
            ("Intro to Machine Learning Workshop", "🤖", "Hands-on ML with sklearn and real Malaysian datasets.", "2026-06-14", "09:00", "17:00", "codencode JB", "physical", "English / BM", "ml", "none", 1),
            ("Vibe Coding with AI Tools", "✨", "Build full-stack apps fast using AI tools, GitHub, and modern deployment workflows.", "2026-06-28", "10:00", "16:00", "Online (Zoom)", "online", "English / 中文", "vibe", "none", 1),
            ("Python for Data Analysis", "📊", "Analyze real datasets with pandas, notebooks, and visualisation tools.", "2026-07-12", "09:00", "17:00", "codencode KL", "physical", "English", "data", "none", 1),
            ("Foon Yew Evening School — Python Night", "🌙", "Weekly 2-hour Python evening class for Foon Yew students.", "2026-05-27", "19:30", "21:30", "Foon Yew High School, JB", "physical", "中文 / EN", "eve", "weekly", 1),
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


# ── PDF Generator ─────────────────────────────────────────────────
def build_pdf(reg: Registration) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm,
    )

    # Colours
    DARK   = colors.HexColor("#080c10")
    CYAN   = colors.HexColor("#00dcb4")
    GOLD   = colors.HexColor("#f5c842")
    LIGHT  = colors.HexColor("#e8edf3")
    MID    = colors.HexColor("#5a6a7a")
    SURF   = colors.HexColor("#0d1117")
    RED    = colors.HexColor("#ff4d4d")

    styles = getSampleStyleSheet()

    def sty(name, **kw):
        return ParagraphStyle(name, **kw)

    s_title = sty("title", fontSize=22, textColor=CYAN,
                  fontName="Helvetica-Bold", spaceAfter=2,
                  alignment=TA_CENTER)
    s_sub   = sty("sub", fontSize=9, textColor=MID,
                  fontName="Helvetica", alignment=TA_CENTER, spaceAfter=6)
    s_sec   = sty("sec", fontSize=8, textColor=CYAN,
                  fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4,
                  letterSpacing=1.5)
    s_warn  = sty("warn", fontSize=8, textColor=RED,
                  fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2)
    s_small = sty("small", fontSize=7, textColor=MID,
                  fontName="Helvetica", spaceAfter=2)
    s_foot  = sty("foot", fontSize=7, textColor=MID,
                  fontName="Helvetica", alignment=TA_CENTER)

    def section(title):
        return [
            Spacer(1, 4*mm),
            Paragraph(f"// {title.upper()}", s_sec),
            HRFlowable(width="100%", thickness=0.5,
                       color=colors.HexColor("#1a2a2a"), spaceAfter=4),
        ]

    def row_table(data, col_widths=(55*mm, 105*mm)):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTNAME",    (0,0),(-1,-1), "Helvetica"),
            ("FONTSIZE",    (0,0),(-1,-1), 9),
            ("FONTNAME",    (0,0),(0,-1),  "Helvetica-Bold"),
            ("TEXTCOLOR",   (0,0),(0,-1),  MID),
            ("TEXTCOLOR",   (1,0),(1,-1),  LIGHT),
            ("TOPPADDING",  (0,0),(-1,-1), 4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[SURF, colors.HexColor("#0a0f14")]),
            ("GRID",        (0,0),(-1,-1), 0.3, colors.HexColor("#1a2a2a")),
            ("LEFTPADDING", (0,0),(-1,-1), 8),
        ]))
        return t

    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    ref = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    story = []

    # ── Header ──
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("codencode.my", s_title))
    story.append(Paragraph("Student Registration Summary", s_sub))
    story.append(Paragraph(f"Reference: {ref}  |  Submitted: {now}", s_small))
    story.append(HRFlowable(width="100%", thickness=1, color=CYAN, spaceAfter=6))

    # ── Personal ──
    story += section("Personal Details")
    story.append(row_table([
        ["Full Name",     reg.full_name],
        ["WhatsApp",      reg.whatsapp],
        ["Email",         reg.email],
        ["Occupation",    reg.occupation],
        ["Language",      reg.language],
        ["Experience",    reg.experience_level],
        ["How Found Us",  reg.referral_source or "—"],
    ]))

    # ── Goals ──
    story += section("Learning Goals")
    story.append(Paragraph(reg.learning_goals, ParagraphStyle(
        "goals", fontSize=9, textColor=LIGHT, fontName="Helvetica",
        leading=14, leftIndent=8, spaceAfter=4,
        backColor=SURF, borderPad=6,
    )))

    # ── Course & Format ──
    story += section("Course & Class Details")
    story.append(row_table([
        ["Course",        reg.course],
        ["Class Format",  reg.class_format],
        ["Timing",        reg.timing],
    ]))

    # ── Pricing ──
    story += section("Fees & Payment")
    price_data = [
        ["Total Fee",     reg.total_fee + "  (one-time, no recurring charges)"],
        ["Payment Plan",  reg.payment_preference],
    ]
    if reg.instalment_week1:
        price_data.append(["Week 1 Payment", reg.instalment_week1])
    if reg.instalment_week3:
        price_data.append(["Week 3 Payment", reg.instalment_week3])
    story.append(row_table(price_data))

    # Instalment warning
    if "Instalment" in reg.payment_preference and reg.instalment_week3:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            "⚠  Important: If Week 3 payment is not received, the class will not proceed "
            "until the balance is settled.",
            s_warn
        ))

    # ── Footer ──
    story.append(Spacer(1, 8*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=CYAN, spaceAfter=4))
    story.append(Paragraph(
        "codencode.my  |  hello@codencode.my  |  +60 11-3165 2854  |  KL · JB · Online Zoom",
        s_foot
    ))
    story.append(Paragraph(
        "This is an automatically generated registration summary. "
        "Our team will contact you within 24 hours to confirm your spot.",
        s_foot
    ))

    doc.build(story)
    return buffer.getvalue()


# ── Email Sender ─────────────────────────────────────────────────
def send_email(reg: Registration, pdf_bytes: bytes):
    now_str  = datetime.now().strftime("%d %b %Y %I:%M %p")
    ref      = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    filename = f"codencode_registration_{reg.full_name.replace(' ','_')}.pdf"

    # ── Email to YOU (admin copy) ────────────────
    admin_msg = MIMEMultipart()
    admin_msg["From"]    = FROM_EMAIL
    admin_msg["To"]      = TO_EMAIL
    admin_msg["Subject"] = f"[NEW REGISTRATION] {reg.full_name} – {reg.course} – {now_str}"

    admin_body = f"""
New student registration received!

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
  Total         : {reg.total_fee}  (one-time)
  Payment Plan  : {reg.payment_preference}
  Week 1        : {reg.instalment_week1 or '—'}
  Week 3        : {reg.instalment_week3 or '—'}

GOALS
  {reg.learning_goals}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PDF summary attached.
    """
    admin_msg.attach(MIMEText(admin_body, "plain"))

    # Attach PDF
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    admin_msg.attach(part)

    # ── Email to STUDENT (confirmation copy) ─────
    student_msg = MIMEMultipart()
    student_msg["From"]    = FROM_EMAIL
    student_msg["To"]      = reg.email
    student_msg["Subject"] = f"Registration Received – codencode.my ({reg.course})"

    payment_section = ""
    if "Instalment" in reg.payment_preference:
        payment_section = f"""
Payment Schedule (Instalment):
  Week 1 (Upon Enrolment) : {reg.instalment_week1}
  Week 3 (Before 3rd Session) : {reg.instalment_week3}

  ⚠ Important: If Week 3 payment is not received, the class will not
  proceed until the balance is settled.
"""
    else:
        payment_section = f"  Total (full payment) : {reg.total_fee}"

    student_body = f"""Hi {reg.full_name.split()[0]},

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
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A full PDF summary is attached to this email for your records.

If you have any questions, WhatsApp us anytime:
👉 https://wa.me/601131652854

See you in class!
Sasha & the codencode team
codencode.my
KL · JB · Online Zoom
    """
    student_msg.attach(MIMEText(student_body, "plain"))

    # Attach PDF to student too
    part2 = MIMEBase("application", "octet-stream")
    part2.set_payload(pdf_bytes)
    encoders.encode_base64(part2)
    part2.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    student_msg.attach(part2)

    # ── Send both via SMTP ────────────────────────
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, TO_EMAIL, admin_msg.as_string())
        server.sendmail(FROM_EMAIL, reg.email, student_msg.as_string())

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


# ── Endpoint ─────────────────────────────────────────────────────
@app.post("/register")
async def register(reg: Registration):
    try:
        pdf_bytes = build_pdf(reg)
        send_email(reg, pdf_bytes)
        return {"status": "ok", "message": "Registration received. Check your email!"}
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        raise HTTPException(status_code=500, detail=f"Email sending failed: {str(e)}")
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def health():
    return {"status": "ok", "service": "codencode registration API"}

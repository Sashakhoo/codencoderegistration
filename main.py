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
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@codencode.my")
TO_EMAIL   = os.getenv("TO_EMAIL",   "hello@codencode.my")

# ── Pydantic model ───────────────────────────────────────────────
class Registration(BaseModel):
    full_name:          str
    whatsapp:           str
    email:              EmailStr
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
hello@codencode.my | codencode.my
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

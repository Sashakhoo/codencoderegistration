"""
codencode.my — Registration Backend
====================================
Receives student registration JSON, generates a PDF summary,
emails it to the student + hello@codencode.my via Brevo API.

Deploy on Railway. Set these environment variables:
  BREVO_API_KEY   your Brevo API key (xkeysib-...)
  FROM_EMAIL      e.g. hello@codencode.my
  FROM_NAME       e.g. codencode Academy
  TO_EMAIL        e.g. hello@codencode.my  (where YOU receive registrations)
  ALLOWED_ORIGIN  e.g. https://codencode.my
"""

import os
import io
import base64
import logging
import requests
from datetime import datetime

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

# ── Config ────────────────────────────────────────────────────────
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
FROM_EMAIL    = os.getenv("FROM_EMAIL", "hello@codencode.my")
FROM_NAME     = os.getenv("FROM_NAME",  "codencode Academy")
TO_EMAIL      = os.getenv("TO_EMAIL",   "hello@codencode.my")

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"

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

    CYAN   = colors.HexColor("#00dcb4")
    GOLD   = colors.HexColor("#f5c842")
    LIGHT  = colors.HexColor("#e8edf3")
    MID    = colors.HexColor("#5a6a7a")
    SURF   = colors.HexColor("#0d1117")
    RED    = colors.HexColor("#ff4d4d")

    def sty(name, **kw):
        return ParagraphStyle(name, **kw)

    s_title = sty("title", fontSize=22, textColor=CYAN,
                  fontName="Helvetica-Bold", spaceAfter=2, alignment=TA_CENTER)
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
            ("FONTNAME",        (0,0),(-1,-1), "Helvetica"),
            ("FONTSIZE",        (0,0),(-1,-1), 9),
            ("FONTNAME",        (0,0),(0,-1),  "Helvetica-Bold"),
            ("TEXTCOLOR",       (0,0),(0,-1),  MID),
            ("TEXTCOLOR",       (1,0),(1,-1),  LIGHT),
            ("TOPPADDING",      (0,0),(-1,-1), 4),
            ("BOTTOMPADDING",   (0,0),(-1,-1), 4),
            ("ROWBACKGROUNDS",  (0,0),(-1,-1), [SURF, colors.HexColor("#0a0f14")]),
            ("GRID",            (0,0),(-1,-1), 0.3, colors.HexColor("#1a2a2a")),
            ("LEFTPADDING",     (0,0),(-1,-1), 8),
        ]))
        return t

    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    ref = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    story = []
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph("codencode.my", s_title))
    story.append(Paragraph("Student Registration Summary", s_sub))
    story.append(Paragraph(f"Reference: {ref}  |  Submitted: {now}", s_small))
    story.append(HRFlowable(width="100%", thickness=1, color=CYAN, spaceAfter=6))

    story += section("Personal Details")
    story.append(row_table([
        ["Full Name",    reg.full_name],
        ["WhatsApp",     reg.whatsapp],
        ["Email",        reg.email],
        ["Occupation",   reg.occupation],
        ["Language",     reg.language],
        ["Experience",   reg.experience_level],
        ["How Found Us", reg.referral_source or "—"],
    ]))

    story += section("Learning Goals")
    story.append(Paragraph(reg.learning_goals, ParagraphStyle(
        "goals", fontSize=9, textColor=LIGHT, fontName="Helvetica",
        leading=14, leftIndent=8, spaceAfter=4, backColor=SURF, borderPad=6,
    )))

    story += section("Course & Class Details")
    story.append(row_table([
        ["Course",       reg.course],
        ["Class Format", reg.class_format],
        ["Timing",       reg.timing],
    ]))

    story += section("Fees & Payment")
    price_data = [
        ["Total Fee",    reg.total_fee + "  (one-time, no recurring charges)"],
        ["Payment Plan", reg.payment_preference],
    ]
    if reg.instalment_week1:
        price_data.append(["Week 1 Payment", reg.instalment_week1])
    if reg.instalment_week3:
        price_data.append(["Week 3 Payment", reg.instalment_week3])
    story.append(row_table(price_data))

    if "Instalment" in reg.payment_preference and reg.instalment_week3:
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph(
            "⚠  Important: If Week 3 payment is not received, the class will not proceed "
            "until the balance is settled.", s_warn
        ))

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

    attachment = [{
        "content": pdf_b64,
        "name":    filename,
    }]

    # ── Admin email (to you) ──────────────────────
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

    admin_payload = {
        "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
        "to":          [{"email": TO_EMAIL}],
        "subject":     f"[NEW REGISTRATION] {reg.full_name} – {reg.course} – {now_str}",
        "textContent": admin_text,
        "attachment":  attachment,
    }

    r = requests.post(BREVO_SEND_URL, json=admin_payload, headers=headers)
    if r.status_code not in (200, 201):
        raise Exception(f"Brevo admin email failed: {r.status_code} {r.text}")

    # ── Student confirmation email ────────────────
    if "Instalment" in reg.payment_preference:
        payment_section = f"""Payment Schedule (Instalment):
  Week 1 (Upon Enrolment)      : {reg.instalment_week1}
  Week 3 (Before 3rd Session)  : {reg.instalment_week3}

  ⚠ Important: If Week 3 payment is not received, the class will
  not proceed until the balance is settled."""
    else:
        payment_section = f"Total (full payment) : {reg.total_fee}"

    first_name = reg.full_name.split()[0]
    student_text = f"""Hi {first_name},

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
codencode.my  |  KL · JB · Online Zoom
"""

    student_payload = {
        "sender":      {"name": FROM_NAME, "email": FROM_EMAIL},
        "to":          [{"email": reg.email, "name": reg.full_name}],
        "subject":     f"Registration Received – codencode.my ({reg.course})",
        "textContent": student_text,
        "attachment":  attachment,
    }

    r2 = requests.post(BREVO_SEND_URL, json=student_payload, headers=headers)
    if r2.status_code not in (200, 201):
        raise Exception(f"Brevo student email failed: {r2.status_code} {r2.text}")

    logger.info(f"Brevo emails sent for {reg.full_name} ({reg.email})")


# ── Endpoint ─────────────────────────────────────────────────────
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

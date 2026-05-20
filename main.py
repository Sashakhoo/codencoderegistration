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
import requests
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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

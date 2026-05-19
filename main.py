"""
codencode.my — Registration Backend
=====================================
Serves the registration page at  GET  /register
Handles form submissions at       POST /api/register

Since everything runs on codencode.my (Railway), there are
zero CORS issues — the page and the API are the same origin.

Environment variables to set in Railway → Variables:
  SMTP_HOST   e.g. smtp.gmail.com
  SMTP_PORT   e.g. 587
  SMTP_USER   your sending Gmail address
  SMTP_PASS   your Gmail App Password (not your login password)
  FROM_EMAIL  e.g. hello@codencode.my
  TO_EMAIL    e.g. hello@codencode.my
"""

import os
import io
import smtplib
import logging
from pathlib import Path
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="codencode.my", version="1.0.0")

SMTP_HOST  = os.getenv("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER  = os.getenv("SMTP_USER",  "")
SMTP_PASS  = os.getenv("SMTP_PASS",  "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@codencode.my")
TO_EMAIL   = os.getenv("TO_EMAIL",   "hello@codencode.my")

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

REGISTER_HTML = Path(__file__).parent / "register.html"

@app.get("/register", response_class=HTMLResponse)
async def register_page():
    if REGISTER_HTML.exists():
        return HTMLResponse(content=REGISTER_HTML.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="register.html not found")

@app.get("/registration", response_class=HTMLResponse)
async def registration_page():
    return await register_page()

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

def build_pdf(reg: Registration) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm,  bottomMargin=20*mm)

    CYAN  = colors.HexColor("#00dcb4")
    LIGHT = colors.HexColor("#e8edf3")
    MID   = colors.HexColor("#5a6a7a")
    SURF  = colors.HexColor("#0d1117")
    SURF2 = colors.HexColor("#0a0f14")
    RED   = colors.HexColor("#ff4d4d")

    def sty(name, **kw): return ParagraphStyle(name, **kw)
    s_title = sty("t", fontSize=22, textColor=CYAN, fontName="Helvetica-Bold", spaceAfter=2, alignment=TA_CENTER)
    s_sub   = sty("s", fontSize=9,  textColor=MID,  fontName="Helvetica", alignment=TA_CENTER, spaceAfter=4)
    s_ref   = sty("r", fontSize=7,  textColor=MID,  fontName="Helvetica", alignment=TA_CENTER, spaceAfter=6)
    s_sec   = sty("sc", fontSize=8, textColor=CYAN, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=3, letterSpacing=1.5)
    s_warn  = sty("w", fontSize=8,  textColor=RED,  fontName="Helvetica-Bold", spaceBefore=5, spaceAfter=2)
    s_foot  = sty("f", fontSize=7,  textColor=MID,  fontName="Helvetica", alignment=TA_CENTER)
    s_goals = sty("g", fontSize=9,  textColor=LIGHT, fontName="Helvetica", leading=14, leftIndent=8, spaceAfter=4, backColor=SURF, borderPad=6)

    def section(title):
        return [Spacer(1, 3*mm), Paragraph(f"// {title.upper()}", s_sec),
                HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#1a2a2a"), spaceAfter=3)]

    def row_table(data):
        t = Table(data, colWidths=[55*mm, 110*mm])
        t.setStyle(TableStyle([
            ("FONTNAME",(0,0),(-1,-1),"Helvetica"), ("FONTSIZE",(0,0),(-1,-1),9),
            ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"), ("TEXTCOLOR",(0,0),(0,-1),MID),
            ("TEXTCOLOR",(1,0),(1,-1),LIGHT), ("TOPPADDING",(0,0),(-1,-1),4),
            ("BOTTOMPADDING",(0,0),(-1,-1),4), ("LEFTPADDING",(0,0),(-1,-1),8),
            ("ROWBACKGROUNDS",(0,0),(-1,-1),[SURF,SURF2]),
            ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#1a2a2a")),
        ]))
        return t

    now = datetime.now().strftime("%d %b %Y, %I:%M %p")
    ref = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    story = [Spacer(1,2*mm), Paragraph("codencode.my", s_title),
             Paragraph("Student Registration Summary", s_sub),
             Paragraph(f"Ref: {ref}  |  {now}", s_ref),
             HRFlowable(width="100%", thickness=1, color=CYAN, spaceAfter=4)]

    story += section("Personal Details")
    story.append(row_table([
        ["Full Name",  reg.full_name], ["WhatsApp", reg.whatsapp],
        ["Email",      reg.email],     ["Occupation", reg.occupation],
        ["Language",   reg.language],  ["Experience", reg.experience_level],
        ["Referral",   reg.referral_source or "—"],
    ]))
    story += section("Learning Goals")
    story.append(Paragraph(reg.learning_goals, s_goals))
    story += section("Course & Class Details")
    story.append(row_table([["Course", reg.course], ["Class Format", reg.class_format], ["Timing", reg.timing]]))
    story += section("Fees & Payment")
    price_data = [["Total Fee", reg.total_fee + "  (one-time, no recurring charges)"], ["Payment Plan", reg.payment_preference]]
    if reg.instalment_week1: price_data.append(["Week 1 Payment", reg.instalment_week1])
    if reg.instalment_week3: price_data.append(["Week 3 Payment", reg.instalment_week3])
    story.append(row_table(price_data))
    if "Instalment" in reg.payment_preference and reg.instalment_week3:
        story.append(Spacer(1,3*mm))
        story.append(Paragraph("⚠  If Week 3 payment is not received, the class will not proceed until the balance is settled.", s_warn))
    story += [Spacer(1,8*mm), HRFlowable(width="100%",thickness=0.5,color=CYAN,spaceAfter=3),
              Paragraph("codencode.my  |  hello@codencode.my  |  +60 11-3165 2854  |  KL · JB · Online Zoom", s_foot),
              Paragraph("Auto-generated registration summary. Our team will contact you within 24 hours.", s_foot)]
    doc.build(story)
    return buffer.getvalue()

def send_emails(reg: Registration, pdf_bytes: bytes):
    now_str  = datetime.now().strftime("%d %b %Y %I:%M %p")
    ref      = f"CCR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    filename = f"codencode_reg_{reg.full_name.replace(' ','_')}.pdf"

    def attach_pdf(msg):
        part = MIMEBase("application","octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    admin = MIMEMultipart()
    admin["From"]    = FROM_EMAIL
    admin["To"]      = TO_EMAIL
    admin["Subject"] = f"[NEW REG] {reg.full_name} — {reg.course} — {now_str}"
    admin.attach(MIMEText(f"""New registration!\n\nRef: {ref}\nSubmitted: {now_str}\n\nName: {reg.full_name}\nWhatsApp: {reg.whatsapp}\nEmail: {reg.email}\nOccupation: {reg.occupation}\nLanguage: {reg.language}\nExperience: {reg.experience_level}\nReferral: {reg.referral_source or '-'}\n\nCourse: {reg.course}\nFormat: {reg.class_format}\nTiming: {reg.timing}\n\nTotal: {reg.total_fee} (one-time)\nPlan: {reg.payment_preference}\nWeek 1: {reg.instalment_week1 or '-'}\nWeek 3: {reg.instalment_week3 or '-'}\n\nGoals:\n{reg.learning_goals}\n\nPDF attached.""","plain"))
    attach_pdf(admin)

    pay_section = (f"  Week 1: {reg.instalment_week1}\n  Week 3: {reg.instalment_week3}\n\n  ⚠ If Week 3 payment is not received, class will not proceed."
                   if "Instalment" in reg.payment_preference
                   else f"  Total (full): {reg.total_fee}")
    student = MIMEMultipart()
    student["From"]    = FROM_EMAIL
    student["To"]      = reg.email
    student["Subject"] = f"Registration Confirmed — codencode.my ({reg.course})"
    student.attach(MIMEText(f"""Hi {reg.full_name.split()[0]},\n\nThank you for registering with codencode.my! 🎉\n\nWe will confirm your spot within 24 hours.\n\nSummary:\n  Ref: {ref}\n  Course: {reg.course}\n  Format: {reg.class_format}\n  Timing: {reg.timing}\n  Language: {reg.language}\n\nFees:\n{pay_section}\n\nA PDF is attached for your records.\n\nQuestions? WhatsApp: https://wa.me/601131652854\n\nSasha & the codencode team\nhello@codencode.my | codencode.my""","plain"))
    attach_pdf(student)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo(); server.starttls(); server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, TO_EMAIL,  admin.as_string())
        server.sendmail(FROM_EMAIL, reg.email, student.as_string())
    logger.info(f"Emails sent → {reg.email} + {TO_EMAIL}")

@app.post("/api/register")
async def api_register(reg: Registration):
    try:
        send_emails(reg, build_pdf(reg))
        return {"status": "ok", "message": "Registration received!"}
    except smtplib.SMTPException as e:
        logger.error(f"SMTP: {e}")
        raise HTTPException(status_code=500, detail=f"Email error: {str(e)}")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def health():
    return {"status": "ok", "service": "codencode.my"}

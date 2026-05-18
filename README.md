# codencode Registration Backend

FastAPI app that:
1. Receives student registration data as JSON
2. Generates a formatted PDF summary
3. Emails the PDF to **you** (admin) + the **student** automatically

---

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app — PDF generation + email sending |
| `requirements.txt` | Python dependencies |
| `Procfile` | Tells Railway how to start the server |

---

## Deploy on Railway (free)

### Step 1 — Push to GitHub
Create a new **private** GitHub repo called `codencode-backend` and push these 3 files:
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/YOUR_USERNAME/codencode-backend.git
git push -u origin main
```

### Step 2 — Deploy on Railway
1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select your `codencode-backend` repo
3. Railway will auto-detect Python and deploy

### Step 3 — Set Environment Variables
In Railway → your project → **Variables**, add:

| Variable | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` (or your provider) |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your sending Gmail address |
| `SMTP_PASS` | your Gmail **App Password** (not your login password!) |
| `FROM_EMAIL` | `hello@codencode.my` |
| `TO_EMAIL` | `hello@codencode.my` |
| `ALLOWED_ORIGIN` | `https://codencode.my` |

> **Gmail App Password**: Go to Google Account → Security → 2-Step Verification → App Passwords → generate one for "Mail"

### Step 4 — Get your Railway URL
Railway gives you a URL like: `https://codencode-backend-production.up.railway.app`

### Step 5 — Update register.html
Open `register.html` and find this line near the bottom:
```javascript
const API_URL = "https://YOUR_RAILWAY_APP.railway.app/register";
```
Replace it with your actual Railway URL:
```javascript
const API_URL = "https://codencode-backend-production.up.railway.app/register";
```

Push `register.html` to your GitHub Pages repo. Done! ✅

---

## What happens on each submission

1. Student fills form on `codencode.my/register.html`
2. Browser POSTs JSON to your Railway API
3. Railway generates a PDF with all student details
4. Two emails are sent:
   - **Admin email** → `hello@codencode.my` with full details + PDF attached
   - **Student email** → their address with confirmation + PDF attached
5. Student sees success screen on the website

---

## PDF Contents

- Reference number (auto-generated)
- Submission timestamp
- Personal details (name, WhatsApp, email, occupation, language, experience, referral)
- Learning goals
- Course, class format, timing
- Total fee + payment plan
- Instalment warning (if applicable)

---

## Testing locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```
Then test at `http://localhost:8000/docs` (FastAPI auto-docs).

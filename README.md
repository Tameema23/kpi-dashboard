# Sales KPI & Operations Dashboard

A production-ready, multi-user KPI management system built for insurance sales teams. Features real-time analytics, a role-based access control system, a timezone-aware appointment planner, and full audit logging — deployed as a Progressive Web App (PWA).

**Live:** [data-log.onrender.com](https://data-log.onrender.com)

---

## Features

### Authentication & Security
- JWT authentication with bcrypt password hashing and token versioning
- Per-IP rate limiting (5 login attempts/min) to prevent brute-force attacks
- Role-based access control (RBAC) with distinct **Admin** and **Assistant** permission tiers
- Input sanitization and HTML escaping on all string fields
- Audit logging on all sensitive actions (logins, password changes, deletes)
- Automated database backups with timestamped snapshots (10 most recent kept)

### Analytics Dashboard
- YTD KPI tracking: ALP, sales, presentations, closing %, show ratio, conversion ratio
- Weekly performance charts (Chart.js) with real-time data
- Lead quality metrics: bad lead ratio, referral sales, referral closing ratio
- CSV export for all report data

### Appointment Planner
- Weekly calendar UI with modal forms and hover tooltips
- Timezone-aware scheduling (Canadian timezones)
- Admin can create appointments on behalf of assistants
- Appointment type support: appointments and callbacks

### Daily Log
- Log daily metrics: appointments, presentations, sales, ALP, A&H, referrals, leads
- Edit and delete past entries from the History view
- Bulk delete with select-all support

### Quality Tracker
- Track policy retention entries with insured name, policy number, ALP, follow-up, and remarks
- Role-gated: only users with `can_quality` permission can access

### PWA Support
- Installable on iOS and Android as a standalone app
- App icons, manifest, and offline-ready structure

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python, SQLAlchemy |
| Database | SQLite (persistent disk on Render) |
| Auth | JWT (python-jose), bcrypt (passlib) |
| Rate Limiting | SlowAPI |
| Frontend | Vanilla JavaScript (ES6+), HTML5, CSS3 |
| Charts | Chart.js |
| Deployment | Render |

---

## Project Structure

```
├── backend/
│   ├── main.py          # FastAPI app, all API routes, security middleware
│   └── database.py      # SQLAlchemy ORM models (User, DailyLog, Appointment, QualityEntry, AuditLog)
├── frontend/
│   ├── index.html       # Dashboard home
│   ├── log.html         # Daily KPI entry
│   ├── reports.html     # Charts and KPI cards
│   ├── history.html     # Past log entries
│   ├── planner.html     # Appointment calendar
│   ├── quality.html     # Policy quality tracker
│   ├── settings.html    # Account and assistant management
│   ├── login.html       # Auth (login + signup)
│   ├── app.js           # All frontend logic
│   ├── style.css        # Global styles
│   └── manifest.json    # PWA manifest
```

---

## Database Models

- **User** — username, bcrypt-hashed password, role, permissions, token_version
- **DailyLog** — per-user daily KPI metrics keyed by date
- **Appointment** — scheduled appointments with lead name, type, timezone, creator
- **QualityEntry** — policy retention records with follow-up tracking
- **AuditLog** — timestamped record of sensitive actions per user

---

## Running Locally

```bash
# 1. Clone the repo
git clone https://github.com/Tameema23/kpi-dashboard.git
cd kpi-dashboard

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export SECRET_KEY=your_secret_key_here
export DATABASE_URL=sqlite:///./kpi.db

# 5. Run the server
uvicorn backend.main:app --reload
```

Then open `http://localhost:8000` in your browser.

> **Generate a secret key:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Required. Used for JWT signing. |
| `DATABASE_URL` | Optional. Defaults to `sqlite:///./kpi.db` |
| `ALLOWED_ORIGINS` | Optional. Comma-separated list of allowed CORS origins. |

---

## Authors

Tameem Aboueldahab

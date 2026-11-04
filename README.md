# FreshFirst AI

**A smart food inventory and waste-reduction web app.** Track what is in your kitchen, see what is about to expire, record what you eat or throw away, and let AI suggest recipes and explain your waste patterns.

- **Live demo:** (https://fresh-first-ai.vercel.app/)
- **Demo login:** username `demo`, password `FreshFirst-Demo-2026` (a public demo account with sample data)

## Screenshots

_Screenshots will be added here._

## Features

- **Accounts:** register, log in and log out. Every user only ever sees their own data.
- **Food inventory:** items with category, quantity, unit, purchase and expiry dates, and storage notes. Search, filters, and clear validation messages.
- **Expiry dashboard:** food sorted into Expired, Expiring soon (within 3 days) and Everything else, using Python date calculations.
- **Consumption and waste records:** log what you used or threw away, with quantity, reason and estimated cost in rupees. Using everything removes the item but keeps its history.
- **Waste analytics:** waste rate, money wasted, top wasted item and top reason, calculated with **Pandas**. Four **Chart.js** charts: consumed vs wasted, money by category, reasons, and a 30-day trend.
- **AI recipe suggestions:** recipes built from the food you have, using the items that expire soonest first. Choose diet, cuisine, cooking time, number of recipes, and foods to avoid.
- **Weekly meal planner:** a Monday-to-Sunday plan. Add meals by hand or straight from an AI recipe, with its ingredients and steps saved.
- **Shopping list:** built from your meal plan, minus what you already have. Plurals and capital letters match ("Onions" equals "onion"), and stock that expires before a meal does not count.
- **AI waste insights:** the AI reads your waste statistics and writes a short summary, patterns, and practical tips.
- **REST API:** JSON endpoints for inventory, records and analytics (see below).
- **Automated tests:** 249 tests, none of which use the real AI.

## Tech stack

| Area | Tools |
|---|---|
| Backend | Python 3.14, Django 5.2 LTS, Django REST Framework |
| Data analysis | Pandas |
| Database | SQLite for local development, PostgreSQL (Neon) for the public site |
| Frontend | HTML, CSS, JavaScript, Bootstrap 5, Chart.js |
| AI | Google Gemini API (free tier), called from the server |
| Hosting | Vercel (free Hobby plan) |
| Tools | Git and GitHub, Django's test framework |

## How the AI features work

- **Genuine AI:** recipes and insights are written by Google's Gemini models, not pre-written text.
- **Called from the server only.** The API key lives in an environment variable and never reaches the browser or Git.
- **Structured answers:** the AI must reply in a fixed JSON shape, which is validated with Pydantic. Anything malformed is rejected.
- **Model fallback:** if one model is busy, slow or unavailable, the next one is tried, and the page shows a friendly message only if all of them fail.
- **Fair-use limits:** a daily limit per user, a site-wide daily limit, and a short cooldown protect the free quota. Failed requests do not count.
- **Privacy:** only food names, quantities and expiry timing are sent, never usernames or emails. The free Gemini tier may use prompts to improve Google's products, so nothing personal is included.
- **Expired food is never sent** to the recipe AI.
- **The AI can make mistakes.** The app says so on every AI result, and recipes are checked against your inventory afterwards.

## REST API

Everything needs a logged-in session. Users only ever see their own data, and results are paginated (20 per page) and rate-limited.

| Endpoint | Methods | Description |
|---|---|---|
| `/api/inventory/` | GET, POST | List or create food items. Supports `?search=`, `?category=`, `?status=`, `?ordering=`. |
| `/api/inventory/<id>/` | GET, PUT, PATCH, DELETE | Read, change or delete one item. |
| `/api/inventory/expiring/` | GET | Items expiring within 3 days. |
| `/api/logs/` | GET | Consumption and waste records (read-only). Supports `?action=wasted` or `consumed`. |
| `/api/analytics/summary/` | GET | The same statistics and chart data as the Analytics page. |

Locally, `/api/` opens a clickable test page. On a public server the API returns plain JSON only.

## Run it locally

You need Python 3.12 or newer (developed on 3.14) and Git.

**1. Get the code and create a virtual environment** (Windows PowerShell):

```powershell
git clone https://github.com/YOUR-USERNAME/FreshFirstAI.git
cd FreshFirstAI
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On macOS or Linux:

```bash
git clone https://github.com/YOUR-USERNAME/FreshFirstAI.git
cd FreshFirstAI
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**2. Create your private settings file.** Copy `.env.example` to `.env` (PowerShell: `Copy-Item .env.example .env`), then open `.env` and fill it in. Keep `DJANGO_DEBUG=True` for local use.

| Variable | Purpose |
|---|---|
| `DJANGO_DEBUG` | `True` on your own computer only. Defaults to off. |
| `DJANGO_SECRET_KEY` | Required on a public server. Optional locally. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names for a public server. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated `https://...` origins for a public server. |
| `GEMINI_API_KEY` | Free key from [Google AI Studio](https://aistudio.google.com). Without it, everything works except the AI features. |
| `GEMINI_MODELS` | Models to try, in order. |
| `AI_DAILY_LIMIT_PER_USER`, `AI_GLOBAL_DAILY_LIMIT`, `AI_COOLDOWN_SECONDS` | Fair-use limits for the AI features. |
| `DATABASE_URL` | PostgreSQL address for a public server. Leave empty to use SQLite. |

**3. Create the database and start the app:**

```powershell
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000/ and log in as `demo` / `FreshFirst-Demo-2026`, or register your own account. `seed_demo` creates the demo account with sample data, and running it again resets that account.

## Run the tests

```powershell
python manage.py test
```

The tests use a temporary database and a fixed "today", so results never change. The AI is replaced with a fake answer, so they cost nothing and need no API key or internet connection.

## Project structure

```
FreshFirstAI/
├── config/       Django settings, URLs, database-URL parser
├── core/         Home page, dashboard, seed_demo command
├── accounts/     Registration, login, logout
├── inventory/    Food items, consumption and waste records
├── analytics/    Pandas statistics, Chart.js charts, AI insights
├── recipes/      AI recipe suggestions
├── planner/      Weekly meal plan
├── shopping/     Shopping list from the plan and inventory
├── assistant/    Gemini client, model fallback, usage limits
├── api/          Django REST Framework endpoints
├── templates/    HTML templates (Bootstrap 5)
├── scripts/      Helper scripts for checking the Gemini connection
└── requirements.txt
```

## Design decisions

- **Per-user data everywhere.** Every query starts from the logged-in user's own records, so one user can never reach another's. This is covered by tests on every page and API endpoint.
- **History survives deletion.** Records copy the item's name, category and unit, so analytics stay correct after an item is used up.
- **One place talks to the AI.** The Gemini code lives in `assistant/client.py`, so changing provider means changing one file.
- **Safe by default.** Debug is off unless switched on, secrets come from the environment, and secure cookies, HTTPS redirect and HSTS apply on a public server.
- **Testable dates.** Tests fix "today", so expiry logic is checked at its exact boundaries.

## Limitations

- The AI uses a free tier: quotas can run out, and a model can be busy. The app then shows a clear message instead of failing.
- On the free database plan, the first visit after a quiet period can be slower while the database wakes up.
- There is no email verification or password reset yet.
- Barcode and product lookup is not included.

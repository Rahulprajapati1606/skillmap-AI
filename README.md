# SkillMap — AI Skill Assessment & Personalised Learning Plan Agent

> A resume tells you what someone *claims* to know — not how well they actually know it. SkillMap fixes that.

SkillMap is an AI agent that takes a Job Description and a candidate's resume, **conversationally assesses real proficiency** on each required skill through targeted questions, identifies gaps, and generates a **personalised learning plan** with curated free resources and realistic time estimates.

---

## Live Demo

**Frontend:** Open `frontend/index.html` in your browser (or serve with any static server)  
**Backend:** `http://localhost:8000`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (HTML/JS)                       │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ JD + Resume │  │  Chat Interface  │  │ Results Dashboard │   │
│  │   Input     │  │  (Assessment)    │  │ (Scores + Plan)  │   │
│  └──────┬──────┘  └────────┬─────────┘  └────────┬─────────┘   │
└─────────┼──────────────────┼──────────────────────┼─────────────┘
          │ POST /start       │ POST /chat            │ Results in response
          ▼                   ▼                       │
┌─────────────────────────────────────────────────────────────────┐
│                      BACKEND (FastAPI / Python)                   │
│                                                                   │
│  ┌─────────────────┐   ┌─────────────────┐  ┌────────────────┐  │
│  │ Skill Extractor │   │  Assessment     │  │ Learning Plan  │  │
│  │                 │   │  Engine         │  │ Generator      │  │
│  │ • Parses JD     │   │ • 2 Qs/skill   │  │ • Gap analysis │  │
│  │ • Extracts 5-7  │   │ • Adaptive Qs   │  │ • Resources    │  │
│  │   key skills    │   │ • Scores 1-5    │  │ • Timeline     │  │
│  └────────┬────────┘   └────────┬────────┘  └───────┬────────┘  │
└───────────┼─────────────────────┼────────────────────┼───────────┘
            │                     │                    │
            └─────────────────────┼────────────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │   Google Gemini 1.5     │
                    │   Flash API (FREE)      │
                    │                         │
                    │  • Skill extraction     │
                    │  • Question generation  │
                    │  • Answer scoring       │
                    │  • Plan generation      │
                    └─────────────────────────┘
```

---

## Scoring Logic

Each skill goes through a **2-question adaptive assessment**:

| Question | Type | Purpose |
|---|---|---|
| Q1 | Conceptual | Tests fundamental understanding |
| Q2 | Applied / Problem-solving | Tests practical depth, based on Q1 answer |

**Scoring rubric (1–5):**

| Score | Level | Meaning |
|---|---|---|
| 1 | No knowledge | Cannot answer basic questions |
| 2 | Basic awareness | Knows terminology but not application |
| 3 | Working knowledge | Can apply with guidance |
| 4 | Proficient | Applies independently in real scenarios |
| 5 | Expert | Deep knowledge, can mentor others |

The Gemini model evaluates **both answers together** with a structured prompt that enforces this rubric, then returns a score + feedback sentence + level label.

**Gap threshold:** Skills scoring ≤ 3 are flagged as gaps and included in the learning plan.

**Overall score:** Weighted average of all skill scores (equal weight per skill currently).

---

## Tech Stack

| Layer | Technology | Cost |
|---|---|---|
| AI Engine | Google Gemini 1.5 Flash | **Free** (15 RPM, 1M tokens/day) |
| Backend | Python 3.10+ + FastAPI | Free |
| Frontend | Vanilla HTML/CSS/JS | Free |
| Hosting (backend) | Render.com | Free tier |
| Hosting (frontend) | GitHub Pages / Vercel | Free |

---

## Local Setup

### Prerequisites
- Python 3.10+
- A **free** Gemini API key from [aistudio.google.com](https://aistudio.google.com)

### Step 1 — Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/skillmap-agent
cd skillmap-agent
```

### Step 2 — Backend setup
```bash
cd backend
pip install -r requirements.txt
```

Set your API key:
```bash
# Linux/Mac
export GEMINI_API_KEY=your_key_here

# Windows (PowerShell)
$env:GEMINI_API_KEY="your_key_here"
```

Start the server:
```bash
uvicorn main:app --reload --port 8000
```

The API will be live at `http://localhost:8000`  
Docs available at `http://localhost:8000/docs`

### Step 3 — Frontend
Just open `frontend/index.html` in your browser. No build step needed.

> If you see CORS errors, make sure the backend is running on port 8000.

---

## Deployment (Free)

### Backend → Render.com
1. Push code to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your repo, select `backend/` as root
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn main:app --host 0.0.0.0 --port 10000`
6. Add environment variable: `GEMINI_API_KEY=your_key`

### Frontend → GitHub Pages
1. Go to repo Settings → Pages
2. Set source to `frontend/` folder or root
3. Update the `API` variable in `index.html` to your Render URL

---

## API Endpoints

### `POST /start`
Begins a new assessment session.

**Request:**
```json
{
  "job_description": "We are looking for a Data Analyst...",
  "resume": "John Doe, B.Tech Computer Science..."
}
```

**Response:**
```json
{
  "session_id": "uuid-string",
  "skills": ["Python", "SQL", "Data Visualization", "Statistics", "Communication"],
  "message": "Hi! I've analysed the job description... Here's your first question: ...",
  "progress": {"current": 1, "total": 5, "skill": "Python"}
}
```

### `POST /chat`
Sends a candidate's answer and gets the next question or results.

**Request:**
```json
{
  "session_id": "uuid-string",
  "message": "I use Python for data analysis, mainly pandas and matplotlib..."
}
```

**Response (mid-assessment):**
```json
{
  "message": "Got it! Follow-up on Python: ...",
  "phase": "assessment",
  "progress": {"current": 1, "total": 5, "skill": "Python", "question": 2}
}
```

**Response (complete):**
```json
{
  "message": "Generating your personalised learning plan...",
  "phase": "complete",
  "skill_scores": { "Python": {"score": 4, "level": "Proficient", "feedback": "..."} },
  "learning_plan": {
    "overall_score": 3.2,
    "summary": "...",
    "strengths": ["Python", "SQL"],
    "gaps": [{"skill": "Statistics", "priority": "High", "weeks_to_close": 3, "resources": [...]}],
    "learning_roadmap": [{"week": "Week 1-2", "focus": "...", "goal": "..."}],
    "total_weeks_estimate": 6
  }
}
```

---

## Sample Input

**Job Description:**
```
Data Analyst — FinTech Startup

We're looking for a Data Analyst to join our growth team. You will:
- Build dashboards and reports using SQL and Python
- Run A/B tests and interpret statistical results
- Work with the product team to define KPIs
- Present findings to non-technical stakeholders

Required: Python (pandas, matplotlib), SQL, Statistics, Data Visualization, Communication skills
Nice to have: Power BI, Tableau, Excel
```

**Resume:**
```
Rahul Sharma | B.Tech Biotechnology, DTU 2026
Experience:
- Business Analyst Intern, Unified Mentor (Python, SQL, Power BI, Excel)
- Research Intern, AIIMS Delhi (data collection, analysis, report writing)
- Freelance AI Data Annotator

Skills: Python, SQL, Power BI, Excel, basic statistics
Projects: Sales dashboard (Power BI), COVID data analysis (Python/pandas)
```

**Sample Output:** Skills assessed: Python, SQL, Statistics, Data Visualization, Communication  
Overall score: 3.4/5 | Gaps: Statistics (score 2), Data Visualization (score 3)  
Learning plan: 6 weeks | Resources: Khan Academy Statistics, Tableau Public, Coursera

---

## Project Structure

```
skillmap-agent/
├── backend/
│   ├── main.py           # FastAPI app — all routes and AI logic
│   └── requirements.txt
├── frontend/
│   └── index.html        # Complete single-file frontend
└── README.md
```

---

## Limitations & Future Work

- Sessions are stored in-memory (lost on restart — use Redis for production)
- Currently 2 questions per skill (configurable via `max_questions_per_skill`)
- No PDF resume upload yet (text paste only)
- No user authentication

---

## Built With

- [FastAPI](https://fastapi.tiangolo.com/)
- [Google Gemini API](https://aistudio.google.com/)
- [Render](https://render.com/) for hosting

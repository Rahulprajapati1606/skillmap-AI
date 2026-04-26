from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import re
import uuid
import traceback
import urllib.request
import urllib.error

app = FastAPI(title="Skill Assessment Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def call_ai(prompt: str) -> str:
    import time
    models = [
        "google/gemma-3-27b-it:free",
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
    last_error = None
    for model in models:
        for attempt in range(2):
            try:
                data = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1000
                }).encode("utf-8")
                req = urllib.request.Request(
                    OPENROUTER_URL,
                    data=data,
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://skillmap-ai-1vmm.onrender.com",
                        "X-Title": "SkillMap AI"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    return result["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code} for model {model}"
                print(f"Error with model {model}, attempt {attempt+1}: {e.code}")
                if e.code == 429:
                    time.sleep(15)
                else:
                    break
            except Exception as e:
                last_error = str(e)
                print(f"Error with model {model}: {e}")
                break
    raise Exception(f"All models failed. Last error: {last_error}")

sessions = {}

class StartRequest(BaseModel):
    job_description: str
    resume: str

class ChatRequest(BaseModel):
    session_id: str
    message: str

class Session:
    def __init__(self, jd, resume, skills, session_id):
        self.session_id = session_id
        self.jd = jd
        self.resume = resume
        self.skills = skills
        self.current_skill_idx = 0
        self.questions_asked = 0
        self.max_questions_per_skill = 2
        self.skill_scores = {}
        self.phase = "assessment"
        self.history = []

    def current_skill(self):
        if self.current_skill_idx < len(self.skills):
            return self.skills[self.current_skill_idx]
        return None

    def advance_skill(self):
        self.current_skill_idx += 1
        self.questions_asked = 0

    def add_message(self, role, content):
        self.history.append({"role": role, "content": content})

def extract_skills(jd, resume):
    prompt = f"""You are an expert recruiter. Extract the top 5 specific technical and professional skills required from this Job Description.
Return ONLY a JSON array of skill strings, nothing else. No markdown, no explanation.
Example: ["Python", "SQL", "Machine Learning", "Data Visualization", "Communication"]

Job Description:
{jd}"""
    text = call_ai(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)[:5]

def generate_question(skill, resume, question_num, previous_answers):
    prev_context = f"\nTheir previous answer: {previous_answers[-1]}" if previous_answers else ""
    depth = "basic conceptual" if question_num == 1 else "practical application"
    prompt = f"""You are a friendly technical interviewer assessing proficiency in: {skill}
{prev_context}
Ask ONE {depth} question about {skill}. Keep it to 2 sentences max.
Return ONLY the question, nothing else."""
    return call_ai(prompt).strip()

def score_answer(skill, answers):
    answers_text = "\n".join([f"Q{i+1}: {a}" for i, a in enumerate(answers)])
    prompt = f"""Score this candidate's proficiency in "{skill}" based on their answers.
Answers:
{answers_text}
Return ONLY this JSON (no markdown, no extra text):
{{"score": 3, "feedback": "one sentence", "level": "Intermediate"}}
Score 1-5: 1=No knowledge, 2=Basic, 3=Working, 4=Proficient, 5=Expert"""
    text = call_ai(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)

def generate_learning_plan(jd, resume, skill_scores):
    scores_summary = json.dumps(skill_scores, indent=2)
    prompt = f"""You are a career coach. Generate a learning plan based on this assessment.
Job Description: {jd[:400]}
Skill Scores (1-5): {scores_summary}

Return ONLY this JSON (no markdown):
{{
  "overall_score": 3.2,
  "summary": "2 sentence summary",
  "strengths": ["skill1"],
  "gaps": [
    {{
      "skill": "Python",
      "current_level": "Beginner",
      "target_level": "Intermediate",
      "priority": "High",
      "weeks_to_close": 4,
      "resources": [
        {{"title": "Python for Everybody", "url": "https://www.coursera.org/specializations/python", "free": true}}
      ]
    }}
  ],
  "learning_roadmap": [
    {{"week": "Week 1-2", "focus": "what to do", "goal": "measurable outcome"}}
  ],
  "total_weeks_estimate": 8
}}
Only include skills with score <= 3 in gaps. Use real URLs."""
    text = call_ai(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)

@app.post("/start")
async def start_session(req: StartRequest):
    try:
        skills = extract_skills(req.job_description, req.resume)
    except Exception as e:
        print("EXTRACT ERROR:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Skill extraction failed: {str(e)}")
    session_id = str(uuid.uuid4())
    session = Session(req.job_description, req.resume, skills, session_id)
    sessions[session_id] = session
    first_skill = session.current_skill()
    intro = f"Hi! I've analysed the job description. I'll assess your proficiency across {len(skills)} skills: **{', '.join(skills)}**.\n\nLet's start with **{first_skill}**. Answer naturally — 2 questions per skill.\n\nHere's your first question:"
    first_question = generate_question(first_skill, req.resume, 1, [])
    session.questions_asked = 1
    session.add_message("assistant", intro + "\n\n" + first_question)
    return {
        "session_id": session_id,
        "skills": skills,
        "message": intro + "\n\n" + first_question,
        "progress": {"current": 1, "total": len(skills), "skill": first_skill}
    }

@app.post("/chat")
async def chat(req: ChatRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.phase == "complete":
        return {"message": "Assessment already complete.", "phase": "complete"}
    session.add_message("user", req.message)
    skill = session.current_skill()
    if skill not in session.skill_scores:
        session.skill_scores[skill] = {"answers": [], "score": None}
    session.skill_scores[skill]["answers"].append(req.message)
    if session.questions_asked < session.max_questions_per_skill:
        try:
            q = generate_question(skill, session.resume, session.questions_asked + 1, session.skill_scores[skill]["answers"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        session.questions_asked += 1
        msg = f"Got it! Follow-up on **{skill}**:\n\n{q}"
        session.add_message("assistant", msg)
        return {"message": msg, "phase": "assessment", "progress": {"current": session.current_skill_idx + 1, "total": len(session.skills), "skill": skill, "question": session.questions_asked}}
    else:
        try:
            result = score_answer(skill, session.skill_scores[skill]["answers"])
        except Exception as e:
            result = {"score": 3, "feedback": "Assessment recorded.", "level": "Intermediate"}
        session.skill_scores[skill].update(result)
        session.advance_skill()
        next_skill = session.current_skill()
        if next_skill is None:
            session.phase = "complete"
            try:
                plan = generate_learning_plan(session.jd, session.resume, {s: {"score": v["score"], "level": v.get("level", ""), "feedback": v.get("feedback", "")} for s, v in session.skill_scores.items()})
            except Exception as e:
                print("PLAN ERROR:", traceback.format_exc())
                plan = {"overall_score": 3.0, "summary": "Assessment complete.", "strengths": [], "gaps": [], "learning_roadmap": [], "total_weeks_estimate": 0}
            msg = "Assessment complete! Generating your personalised learning plan..."
            return {"message": msg, "phase": "complete", "skill_scores": session.skill_scores, "learning_plan": plan, "progress": {"current": len(session.skills), "total": len(session.skills)}}
        else:
            try:
                q = generate_question(next_skill, session.resume, 1, [])
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
            session.questions_asked = 1
            msg = f"Nice work on **{skill}**! Moving on to **{next_skill}**.\n\n{q}"
            session.add_message("assistant", msg)
            return {"message": msg, "phase": "assessment", "progress": {"current": session.current_skill_idx + 1, "total": len(session.skills), "skill": next_skill, "question": 1}}

@app.get("/health")
async def health():
    return {"status": "ok"}

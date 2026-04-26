from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os
import re
import urllib.request

app = FastAPI(title="Skill Assessment Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENROUTER_API_KEY = "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"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def call_groq(prompt: str) -> str:
    import time
    for attempt in range(3):
        try:
            data = json.dumps({
                "model": "mistralai/mistral-small-3.1-24b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1000
            }).encode("utf-8")
            req = urllib.request.Request(
                OPENROUTER_URL,
                data=data,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < 2:
                time.sleep(30)
            else:
                raise e
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
    prompt = f"""You are an expert recruiter. Extract the top 5-7 specific technical and professional skills required from this Job Description.
Return ONLY a JSON array of skill strings, nothing else. No markdown, no explanation.
Example: ["Python", "SQL", "Machine Learning", "Data Visualization", "Communication"]

Job Description:
{jd}

Resume (for context):
{resume}"""
    text = call_groq(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)[:7]

def generate_question(skill, resume, question_num, previous_answers):
    prev_context = f"\nTheir previous answer: {previous_answers[-1]}" if previous_answers else ""
    depth = "basic conceptual" if question_num == 1 else "practical application or problem-solving"
    prompt = f"""You are a friendly but rigorous technical interviewer assessing proficiency in: {skill}
Resume context: {resume[:500]}
{prev_context}
Ask ONE {depth} question about {skill}. Question {question_num} of 2.
Be conversational. Keep it to 2-3 sentences. Do NOT reveal you are scoring them.
Return ONLY the question, nothing else."""
    return call_groq(prompt).strip()

def score_answer(skill, answers):
    answers_text = "\n".join([f"Q{i+1}: {a}" for i, a in enumerate(answers)])
    prompt = f"""You are an expert evaluator. Score this candidate's proficiency in "{skill}".
Answers:
{answers_text}
Return ONLY a JSON object (no markdown):
{{"score": 3, "feedback": "one sentence feedback", "level": "Intermediate"}}
Score 1-5: 1=No knowledge, 2=Basic awareness, 3=Working knowledge, 4=Proficient, 5=Expert"""
    text = call_groq(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

def generate_learning_plan(jd, resume, skill_scores):
    scores_summary = json.dumps(skill_scores, indent=2)
    prompt = f"""You are a career coach. Generate a personalised learning plan based on this assessment.
Job Description: {jd[:600]}
Resume: {resume[:400]}
Skill Scores (1-5): {scores_summary}

Return ONLY this JSON structure (no markdown):
{{
  "overall_score": 3.2,
  "summary": "2-3 sentence honest summary",
  "strengths": ["skill1", "skill2"],
  "gaps": [
    {{
      "skill": "Python",
      "current_level": "Beginner",
      "target_level": "Intermediate",
      "priority": "High",
      "weeks_to_close": 4,
      "resources": [
        {{"title": "Python for Everybody", "type": "Course", "url": "https://www.coursera.org/specializations/python", "free": true}}
      ]
    }}
  ],
  "learning_roadmap": [
    {{"week": "Week 1-2", "focus": "what to do", "goal": "measurable outcome"}}
  ],
  "total_weeks_estimate": 8
}}
Only include skills with score <= 3 in gaps. Use real URLs. Prefer free resources."""
    text = call_groq(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    return json.loads(text)

@app.post("/start")
async def start_session(req: StartRequest):
    try:
        skills = extract_skills(req.job_description, req.resume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Skill extraction failed: {str(e)}")
    import uuid
    session_id = str(uuid.uuid4())
    session = Session(req.job_description, req.resume, skills, session_id)
    sessions[session_id] = session
    first_skill = session.current_skill()
    intro = f"Hi! I've analysed the job description and your resume. I'll now assess your proficiency across {len(skills)} skills: **{', '.join(skills)}**.\n\nLet's start with **{first_skill}**. I'll ask you 2 questions per skill — just answer naturally, like you would in a real interview.\n\nReady? Here's your first question:"
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
        q = generate_question(skill, session.resume, session.questions_asked + 1, session.skill_scores[skill]["answers"])
        session.questions_asked += 1
        msg = f"Got it! Follow-up on **{skill}**:\n\n{q}"
        session.add_message("assistant", msg)
        return {"message": msg, "phase": "assessment", "progress": {"current": session.current_skill_idx + 1, "total": len(session.skills), "skill": skill, "question": session.questions_asked}}
    else:
        result = score_answer(skill, session.skill_scores[skill]["answers"])
        session.skill_scores[skill].update(result)
        session.advance_skill()
        next_skill = session.current_skill()
        if next_skill is None:
            session.phase = "complete"
            try:
                plan = generate_learning_plan(session.jd, session.resume, {s: {"score": v["score"], "level": v.get("level", ""), "feedback": v.get("feedback", "")} for s, v in session.skill_scores.items()})
            except Exception as e:
                plan = {"error": str(e)}
            msg = "That's all the skills covered! Generating your personalised learning plan now..."
            session.add_message("assistant", msg)
            return {"message": msg, "phase": "complete", "skill_scores": session.skill_scores, "learning_plan": plan, "progress": {"current": len(session.skills), "total": len(session.skills)}}
        else:
            q = generate_question(next_skill, session.resume, 1, [])
            session.questions_asked = 1
            msg = f"Nice work on **{skill}**! Moving on to **{next_skill}**.\n\n{q}"
            session.add_message("assistant", msg)
            return {"message": msg, "phase": "assessment", "progress": {"current": session.current_skill_idx + 1, "total": len(session.skills), "skill": next_skill, "question": 1}}

@app.get("/health")
async def health():
    return {"status": "ok"}

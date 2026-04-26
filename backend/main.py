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

HF_API_KEY = "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"
HF_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"

def call_ai(prompt: str) -> str:
    import time
    for attempt in range(3):
        try:
            data = json.dumps({
                "inputs": prompt,
                "parameters": {"max_new_tokens": 500, "return_full_text": False}
            }).encode("utf-8")
            req = urllib.request.Request(
                HF_URL,
                data=data,
                headers={
                    "Authorization": f"Bearer {HF_API_KEY}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                if isinstance(result, list):
                    return result[0]["generated_text"]
                elif isinstance(result, dict) and "error" in result:
                    if "loading" in result["error"].lower():
                        print("Model loading, waiting 20s...")
                        time.sleep(20)
                        continue
                    raise Exception(result["error"])
                return str(result)
        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                raise Exception(f"AI call failed: {str(e)}")

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
    prompt = f"""Extract the top 5 technical skills required from this Job Description.
Return ONLY a JSON array like this: ["Python", "SQL", "Data Visualization", "Statistics", "Communication"]
No explanation, no markdown, just the JSON array.

Job Description:
{jd[:1000]}

JSON array:"""
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
    prompt = f"""You are a technical interviewer. Ask ONE {depth} question about {skill}.
{prev_context}
Keep the question to 2 sentences max. Return ONLY the question.

Question:"""
    return call_ai(prompt).strip()

def score_answer(skill, answers):
    answers_text = "\n".join([f"Q{i+1}: {a}" for i, a in enumerate(answers)])
    prompt = f"""Score this candidate's proficiency in "{skill}".
Answers: {answers_text}

Return ONLY this JSON (no markdown):
{{"score": 3, "feedback": "one sentence", "level": "Intermediate"}}

JSON:"""
    text = call_ai(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except:
        return {"score": 3, "feedback": "Assessment recorded.", "level": "Intermediate"}

def generate_learning_plan(jd, resume, skill_scores):
    scores_summary = json.dumps(skill_scores, indent=2)
    prompt = f"""You are a career coach. Generate a learning plan.
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

JSON:"""
    text = call_ai(prompt).strip()
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except:
        return {"overall_score": 3.0, "summary": "Assessment complete.", "strengths": [], "gaps": [], "learning_roadmap": [], "total_weeks_estimate": 0}

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
        except:
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

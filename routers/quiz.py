"""
GET  /quiz           — quiz home page
GET  /quiz/card      — HTMX: serve a random card (question side)
POST /quiz/check     — HTMX: check answer, return result + next card button
"""

import json
import random
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_path = Path(__file__).parent.parent / "data" / "quiz_parts.json"
_PARTS: list[dict] = json.loads(_path.read_text())

def _load_parts() -> list[dict]:
    return _PARTS


def _random_part(exclude_id: str = None) -> dict:
    parts = _load_parts()
    choices = [p for p in parts if p["part_id"] != exclude_id] if exclude_id else parts
    return random.choice(choices)


def _normalise(s: str) -> str:
    return s.strip().lower()


# ── Pages ──────────────────────────────────────────────────────────────────────

@router.get("/quiz/stats/{level}")
async def quiz_stats_get(level: str):
    conn = get_db()
    try:
        row = conn.execute("SELECT high_streak FROM quiz_stats WHERE level = ?", (level,)).fetchone()
        return JSONResponse({"high_streak": row["high_streak"] if row else 0})
    finally:
        conn.close()


@router.post("/quiz/stats/{level}")
async def quiz_stats_save(level: str, high_streak: int = Form(...)):
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO quiz_stats (level, high_streak) VALUES (?, ?)
            ON CONFLICT(level) DO UPDATE SET high_streak = excluded.high_streak
            WHERE excluded.high_streak > quiz_stats.high_streak
        """, (level, high_streak))
        conn.commit()
        row = conn.execute("SELECT high_streak FROM quiz_stats WHERE level = ?", (level,)).fetchone()
        return JSONResponse({"high_streak": row["high_streak"]})
    finally:
        conn.close()


@router.get("/quiz", response_class=HTMLResponse)
async def quiz_home(request: Request):
    parts = _load_parts()
    categories = sorted({p["cat_l1"] for p in parts})
    return templates.TemplateResponse("quiz.html", {
        "request": request,
        "total_parts": len(parts),
        "categories": categories,
    })


@router.get("/quiz/card", response_class=HTMLResponse)
async def quiz_card(request: Request, level: str = "easy", exclude: str = ""):
    part = _random_part(exclude_id=exclude or None)
    return templates.TemplateResponse("partials/quiz_card.html", {
        "request": request,
        "part": part,
        "level": level,
    })


@router.get("/quiz/reveal", response_class=HTMLResponse)
async def quiz_reveal(request: Request, part_id: str, level: str = "easy"):
    part = next((p for p in _PARTS if p["part_id"] == part_id), None)
    if not part:
        return HTMLResponse("<p>Part not found.</p>", status_code=404)
    correct_map = {"easy": part["cat_l1"], "medium": part["cat_l2"], "hard": part["cat_l3"]}
    correct = correct_map.get(level, part["cat_l1"])
    return templates.TemplateResponse("partials/quiz_reveal.html", {
        "request": request,
        "part": part,
        "correct": correct,
        "level": level,
    })


@router.post("/quiz/check", response_class=HTMLResponse)
async def quiz_check(
    request: Request,
    part_id: str = Form(...),
    answer: str = Form(...),
    level: str = Form("easy"),
):
    parts = _load_parts()
    part = next((p for p in parts if p["part_id"] == part_id), None)
    if not part:
        return HTMLResponse("<p>Part not found.</p>", status_code=404)

    correct_map = {
        "easy":   part["cat_l1"],
        "medium": part["cat_l2"],
        "hard":   part["cat_l3"],
    }
    correct = correct_map.get(level, part["cat_l1"])
    is_correct = _normalise(answer) == _normalise(correct)

    return templates.TemplateResponse("partials/quiz_result.html", {
        "request": request,
        "part": part,
        "answer": answer.strip(),
        "correct": correct,
        "is_correct": is_correct,
        "level": level,
    })

"""
Storage type management routes.

GET  /storage                  — management page
POST /storage/add              — add a new storage type
POST /storage/{id}/edit        — update name/notes/purchase_url
POST /storage/{id}/delete      — remove (only if no parts use it)
POST /storage/{id}/photo       — upload a photo
"""

import shutil
from pathlib import Path
from fastapi import APIRouter, Form, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional

from database import get_db

router = APIRouter(prefix="/storage")
templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = Path("static/uploads/storage")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _all_storage_types(conn):
    return conn.execute(
        "SELECT * FROM storage_types ORDER BY sort_order, name"
    ).fetchall()


def _storage_page(request: Request, conn, message: str = "", error: str = ""):
    types = _all_storage_types(conn)
    return templates.TemplateResponse("storage.html", {
        "request": request,
        "storage_types": types,
        "message": message,
        "error": error,
    })


@router.get("", response_class=HTMLResponse)
async def storage_page(request: Request):
    conn = get_db()
    try:
        return _storage_page(request, conn)
    finally:
        conn.close()


@router.post("/add", response_class=HTMLResponse)
async def add_storage_type(
    request: Request,
    name:         str = Form(...),
    code:         str = Form(""),
    purchase_url: str = Form(""),
    notes:        str = Form(""),
):
    name = name.strip()
    if not name:
        conn = get_db()
        try:
            return _storage_page(request, conn, error="Name is required.")
        finally:
            conn.close()

    conn = get_db()
    try:
        max_order = conn.execute("SELECT MAX(sort_order) FROM storage_types").fetchone()[0] or 0
        conn.execute(
            "INSERT OR IGNORE INTO storage_types (name, code, purchase_url, notes, sort_order) VALUES (?, ?, ?, ?, ?)",
            (name, code.strip().upper() or None, purchase_url.strip() or None, notes.strip() or None, max_order + 1),
        )
        conn.commit()
        return _storage_page(request, conn, message=f'"{name}" added.')
    finally:
        conn.close()


@router.post("/{st_id}/edit", response_class=HTMLResponse)
async def edit_storage_type(
    request: Request,
    st_id:        int,
    name:         str = Form(...),
    code:         str = Form(""),
    purchase_url: str = Form(""),
    notes:        str = Form(""),
):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE storage_types SET name=?, code=?, purchase_url=?, notes=? WHERE id=?",
            (name.strip(), code.strip().upper() or None, purchase_url.strip() or None, notes.strip() or None, st_id),
        )
        conn.commit()
        return _storage_page(request, conn, message="Storage type updated.")
    finally:
        conn.close()


@router.post("/{st_id}/delete", response_class=HTMLResponse)
async def delete_storage_type(request: Request, st_id: int):
    conn = get_db()
    try:
        in_use = conn.execute(
            "SELECT COUNT(*) FROM locations WHERE storage_type_id = ?", (st_id,)
        ).fetchone()[0]
        if in_use:
            return _storage_page(request, conn,
                error="Can't delete — parts are assigned to this storage type.")

        row = conn.execute("SELECT photo_path FROM storage_types WHERE id=?", (st_id,)).fetchone()
        if row and row["photo_path"]:
            Path(row["photo_path"]).unlink(missing_ok=True)

        conn.execute("DELETE FROM storage_types WHERE id=?", (st_id,))
        conn.commit()
        return _storage_page(request, conn, message="Storage type deleted.")
    finally:
        conn.close()


@router.post("/{st_id}/photo", response_class=HTMLResponse)
async def upload_photo(
    request: Request,
    st_id:  int,
    photo:  UploadFile = File(...),
):
    if not photo or not photo.filename:
        conn = get_db()
        try:
            return _storage_page(request, conn, error="No file selected.")
        finally:
            conn.close()

    suffix = Path(photo.filename).suffix.lower() or ".jpg"
    dest = UPLOAD_DIR / f"{st_id}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(photo.file, f)

    conn = get_db()
    try:
        conn.execute(
            "UPDATE storage_types SET photo_path=? WHERE id=?",
            (str(dest), st_id),
        )
        conn.commit()
        return _storage_page(request, conn, message="Photo saved.")
    finally:
        conn.close()

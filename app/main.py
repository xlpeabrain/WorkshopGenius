"""WorkshopGenius — FastAPI application."""

import json
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.ai import analyze_challenges, UpstreamAPIError
from app.assembler import assemble_deck, build_output_path
from app.catalog import load_or_rebuild_catalog
from app.config import settings
from app.parser import extract_text_from_upload
from app import settings_store

BASE_DIR = Path(__file__).parent

app = FastAPI(title="WorkshopGenius")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _claude_cli_info() -> tuple[bool, str]:
    from app.ai import _find_claude, _subprocess_env
    cli_path = _find_claude()
    if not cli_path:
        return False, ""
    try:
        result = subprocess.run(
            [cli_path, "--version"],
            capture_output=True, text=True, timeout=5,
            env=_subprocess_env(),
        )
        version = result.stdout.strip().split()[0] if result.stdout.strip() else "unknown"
        return True, version
    except Exception:
        return False, ""


@app.on_event("startup")
async def startup() -> None:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_or_rebuild_catalog(settings.slides_dir, settings.catalog_path)
    app.state.catalog = catalog
    app.state.app_settings = settings_store.load()
    cli_available, cli_version = _claude_cli_info()
    app.state.cli_available = cli_available
    app.state.cli_version = cli_version


def _settings_ctx(request: Request, extra: dict = None) -> dict:
    ctx = {
        "request": request,
        "app_settings": request.app.state.app_settings,
        "cli_available": request.app.state.cli_available,
        "cli_version": request.app.state.cli_version,
    }
    if extra:
        ctx.update(extra)
    return ctx


# ── Main page ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            **_settings_ctx(request),
            "is_configured": settings_store.is_configured(),
        },
    )


# ── Settings ───────────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def get_settings(request: Request):
    return templates.TemplateResponse(
        "partials/settings.html", _settings_ctx(request)
    )


@app.post("/settings", response_class=HTMLResponse)
async def post_settings(
    request: Request,
    claude_model: str = Form(default="claude-sonnet-4-6"),
):
    updated = settings_store.save({"claude_model": claude_model.strip()})
    request.app.state.app_settings = updated
    return templates.TemplateResponse(
        "partials/settings.html",
        _settings_ctx(request, {"saved": True}),
    )


# ── Analyze ────────────────────────────────────────────────────────────────────

@app.post("/analyze", response_class=HTMLResponse)
async def analyze(
    request: Request,
    challenge_text: str = Form(default=""),
    file: UploadFile = File(default=None),
):
    catalog = request.app.state.catalog
    app_settings = request.app.state.app_settings

    if not settings_store.is_configured():
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "error": "The claude CLI was not found. Install Claude Code and ensure it is on your PATH.",
            },
            status_code=400,
        )

    try:
        if file and file.filename:
            raw = await file.read()
            if len(raw) > settings.max_upload_bytes:
                raise ValueError("File exceeds 10 MB limit.")
            challenge_text = extract_text_from_upload(file.filename, raw)
        elif not challenge_text.strip():
            raise ValueError("Please enter a challenge description or upload a file.")

        result = await analyze_challenges(challenge_text, catalog, app_settings)
    except UpstreamAPIError as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)},
            status_code=502,
        )
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )

    deck_map = {d["id"]: d for d in catalog["decks"]}
    for sel in result.get("selections", []):
        deck = deck_map.get(sel["deck_id"], {})
        sel["deck_topic"] = deck.get("topic", sel["deck_id"])
        sel["deck_filename"] = deck.get("filename", "")
        slide_lookup = {s["index"]: s["title"] for s in deck.get("slides", [])}
        sel["slides_detail"] = [
            {"index": idx, "title": slide_lookup.get(idx, f"Slide {idx + 1}")}
            for idx in sel.get("slide_indices", [])
        ]

    return templates.TemplateResponse(
        "partials/slide_preview.html",
        {"request": request, "result": result, "challenge_text": challenge_text},
    )


# ── Generate & Download ────────────────────────────────────────────────────────

@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    selections_json: str = Form(...),
    workshop_title: str = Form(default="Workshop"),
):
    catalog = request.app.state.catalog

    try:
        selections = json.loads(selections_json)
        if not selections:
            raise ValueError("No slides selected.")
        output_path = build_output_path(workshop_title, settings.output_dir)
        assemble_deck(selections, catalog, settings.slides_dir, output_path)
    except Exception as e:
        return templates.TemplateResponse(
            "partials/error.html",
            {"request": request, "error": str(e)},
            status_code=500,
        )

    return templates.TemplateResponse(
        "partials/download.html",
        {
            "request": request,
            "filename": output_path.name,
            "workshop_title": workshop_title,
            "slide_count": sum(len(s.get("slide_indices", [])) for s in selections),
        },
    )


@app.get("/download/{filename}")
async def download(filename: str):
    safe_path = (settings.output_dir / filename).resolve()
    if not str(safe_path).startswith(str(settings.output_dir.resolve())):
        return JSONResponse({"error": "Invalid filename"}, status_code=400)
    if not safe_path.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)
    return FileResponse(
        path=str(safe_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


# ── Admin ──────────────────────────────────────────────────────────────────────

@app.post("/admin/reindex", response_class=HTMLResponse)
async def reindex(request: Request):
    try:
        if settings.catalog_path.exists():
            settings.catalog_path.unlink()
        catalog = load_or_rebuild_catalog(settings.slides_dir, settings.catalog_path)
        request.app.state.catalog = catalog
        msg = f"Reindexed {len(catalog['decks'])} decks successfully."
    except Exception as e:
        msg = f"Reindex failed: {e}"
    return HTMLResponse(f'<span style="color:var(--kong-green);font-size:0.85rem;font-weight:600;">{msg}</span>')

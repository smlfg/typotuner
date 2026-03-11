"""TypoTuner Web Dashboard — FastAPI + Jinja2 + htmx."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from typotuner.storage import Storage
from typotuner.recommender import generate_recommendations
from typotuner import qwertz

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if _storage is not None:
        _storage.close()


app = FastAPI(title="TypoTuner", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = get_storage()
    all_stats = db.get_key_stats()
    finger_stats = db.get_finger_stats()
    sessions = db.get_sessions(limit=5)
    typo_summary = db.get_typo_summary()

    total_presses = sum(s["total_presses"] for s in all_stats)
    total_errors = sum(s["total_errors"] for s in all_stats)
    error_rate = total_errors / total_presses if total_presses > 0 else 0

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_presses": total_presses,
        "total_errors": total_errors,
        "error_rate": error_rate,
        "finger_stats": finger_stats,
        "finger_names": qwertz.FINGER_NAMES,
        "sessions": sessions,
        "typo_summary": typo_summary,
        "top_errors": sorted(all_stats, key=lambda x: x["error_rate_ema"], reverse=True)[:10],
    })


@app.get("/heatmap", response_class=HTMLResponse)
async def heatmap(request: Request):
    db = get_storage()
    all_stats = db.get_key_stats()
    rates = {s["key_code"]: s for s in all_stats}
    return templates.TemplateResponse("heatmap.html", {
        "request": request,
        "rates": rates,
        "finger_map": qwertz.FINGER_MAP,
    })


@app.get("/fingers", response_class=HTMLResponse)
async def fingers(request: Request):
    db = get_storage()
    finger_stats = db.get_finger_stats()
    all_stats = db.get_key_stats()
    return templates.TemplateResponse("fingers.html", {
        "request": request,
        "finger_stats": finger_stats,
        "finger_names": qwertz.FINGER_NAMES,
        "all_stats": all_stats,
    })


@app.get("/recommendations", response_class=HTMLResponse)
async def recommendations(request: Request):
    db = get_storage()
    recs = generate_recommendations(db)
    return templates.TemplateResponse("recommendations.html", {
        "request": request,
        "recommendations": recs,
    })


# JSON API for Chart.js
@app.get("/api/finger-stats")
async def api_finger_stats():
    db = get_storage()
    finger_stats = db.get_finger_stats()
    result = {}
    for name in qwertz.FINGER_NAMES:
        fs = finger_stats.get(name)
        if fs:
            total = fs["total_presses"]
            errors = fs["total_errors"]
            result[name] = {
                "presses": total,
                "errors": errors,
                "error_rate": errors / total if total > 0 else 0,
            }
        else:
            result[name] = {"presses": 0, "errors": 0, "error_rate": 0}
    return result


@app.get("/api/heatmap-data")
async def api_heatmap_data():
    """Return per-key stats for the heatmap visualization."""
    db = get_storage()
    all_stats = db.get_key_stats()
    result = {}
    for s in all_stats:
        result[s["key_code"]] = {
            "key_name": s["key_name"],
            "finger": s["finger"],
            "error_rate_ema": s["error_rate_ema"],
            "total_presses": s["total_presses"],
            "dwell_ema": s["dwell_ema"],
        }
    return result

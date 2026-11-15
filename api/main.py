"""FastAPI app: the backend for the team's custom UI.

Run from the repo root:
    .venv/Scripts/python -m uvicorn api.main:app --reload --port 8000
Live, clickable docs: http://localhost:8000/docs  (OpenAPI JSON: /openapi.json)

Conventions the UI can rely on:
- Numbers come as {value, unit, trust, range?, source?, note?}. See /api/options -> trust_labels.
- Bad input returns 422 with {"errors": [{"field": ..., "message": ...}]} so each message can sit under its control.
- Model endpoints return {"available": false, "reason": ...} instead of a number when the input is untested.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import core
from .agent import ChatUnavailable, chat, model_name, provider

app = FastAPI(
    title="AstraBuilders Flame API",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(core.InputError)
async def _input_error(_: Request, exc: core.InputError):
    return JSONResponse(status_code=422, content={"errors": exc.errors})


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]) or None, "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"errors": errors})


@app.exception_handler(ChatUnavailable)
async def _chat_unavailable(_: Request, exc: ChatUnavailable):
    return JSONResponse(status_code=503, content={"errors": [{"field": None, "message": str(exc)}]})


# ------------------------------------------------------------------ request bodies

class FlexInput(BaseModel):
    fuel: Literal["Methanol", "Heptane"] = Field(examples=["Methanol"])
    oxygen_pct: float = Field(examples=[21.0], description="Oxygen mole percent")
    pressure_kpa: float = Field(examples=[101.3], description="Absolute pressure, kPa")
    co2_fraction: float = Field(0.0, description="CO2 mole fraction 0-1")
    helium_fraction: float = Field(0.0, description="Helium mole fraction 0-1")
    droplet_diameter_mm: Optional[float] = Field(None, examples=[2.5], description="Omit to use the typical tested size")


class WhatIfInput(FlexInput):
    model: Literal["extinction", "burn_time"] = "extinction"
    vary: Literal["pressure_kpa", "oxygen_pct", "co2_fraction", "helium_fraction", "droplet_diameter_mm"] = "oxygen_pct"
    points: int = Field(30, ge=5, le=100)


class SimilarSolidInput(BaseModel):
    oxygen_pct: float = Field(examples=[21.0])
    airflow_cm_s: Optional[float] = Field(None, examples=[10.0])
    material: Optional[str] = None
    geometry: Optional[str] = None
    k: int = Field(8, ge=1, le=50)


class AdvisorInput(BaseModel):
    mode: Literal["discover", "analyze"] = "discover"
    oxygen_pct: float = Field(examples=[21.0])
    airflow_cm_s: Optional[float] = Field(None, examples=[10.0])
    material: Optional[str] = Field(None, description="Required in analyze mode")
    mission: Literal["space_station", "moon_base", "mars_habitat"] = "space_station"
    pressure_kpa: Optional[float] = None
    geometry: Optional[str] = None
    max_thickness_mm: Optional[float] = None
    constraints: list[str] = Field(default_factory=list, description="Free-text constraints such as 'max mass 2 kg'; reported as cannot_check")
    priority: Literal["evidence_strength", "fewest_sustained_flames"] = "evidence_strength"


class CompareInput(BaseModel):
    experiment_a: str
    experiment_b: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatInput(BaseModel):
    messages: list[ChatMessage]
    context: Optional[dict] = Field(None, description="Optional dashboard state, e.g. the current advisor inputs or a selected experiment")


# ------------------------------------------------------------------ routes

@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/docs")


@app.get("/api/health", tags=["meta"])
def health():
    m = core.metrics()
    return {"ok": True, "models": {"extinction": m["extinction"]["prediction_enabled"], "burn_time": m["burn_time"]["prediction_enabled"]},
            "chat_configured": provider() is not None, "chat_provider": provider(),
            "chat_model": model_name(provider()) if provider() else None}


@app.get("/api/options", tags=["meta"], summary="Everything needed to build the forms")
def options():
    return core.get_options()


@app.get("/api/investigations", tags=["explore"])
def investigations(fuel_phase: Optional[str] = None, q: Optional[str] = None):
    return core.list_investigations(fuel_phase, q)


@app.get("/api/investigations/{source_record}", tags=["explore"])
def investigation(source_record: str):
    return core.get_investigation(source_record)


@app.get("/api/experiments", tags=["explore"])
def experiments(dataset: Literal["solid", "flex"] = "solid", source_record: Optional[str] = None, material: Optional[str] = None,
                fuel: Optional[str] = None, outcome: Optional[str] = None, geometry: Optional[str] = None,
                oxygen_min: Optional[float] = None, oxygen_max: Optional[float] = None,
                airflow_min: Optional[float] = None, airflow_max: Optional[float] = None, q: Optional[str] = None,
                sort: str = "test", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200)):
    return core.list_experiments(dataset, source_record, material, fuel, outcome, geometry, oxygen_min, oxygen_max,
                                 airflow_min, airflow_max, q, sort, page, page_size)


@app.get("/api/experiments/{experiment_id:path}", tags=["explore"])
def experiment(experiment_id: str):
    return core.get_experiment(experiment_id)


@app.post("/api/compare", tags=["explore"])
def compare(body: CompareInput):
    return core.compare_experiments(body.experiment_a, body.experiment_b)


@app.get("/api/search", tags=["explore"], summary="Search NASA report text")
def search(q: str, source_record: Optional[str] = None, k: int = Query(5, ge=1, le=25), include_plans: bool = True):
    return core.search_evidence(q, source_record, k, include_plans)


@app.get("/api/coverage", tags=["explore"], summary="Every real test as a chart point")
def coverage(dataset: Literal["solid", "flex"] = "solid", fuel: Optional[str] = None):
    return core.coverage_points(dataset, fuel)


@app.post("/api/similar/solid", tags=["advisor"])
def similar_solid(body: SimilarSolidInput):
    return core.find_similar_solid(body.oxygen_pct, body.airflow_cm_s, body.material, body.geometry, body.k)


@app.post("/api/similar/flex", tags=["predict"])
def similar_flex(body: FlexInput, k: int = Query(6, ge=1, le=50)):
    return core.find_similar_flex(**body.model_dump(), k=k)


@app.post("/api/advisor", tags=["advisor"], summary="Material Advisor (analyze or discover)")
def advisor(body: AdvisorInput):
    return core.advisor(**body.model_dump())


@app.get("/api/ground/{material}", tags=["advisor"], summary="Earth-gravity limits beside orbital tests")
def ground(material: str):
    return core.ground_comparison(material)


@app.post("/api/predict/extinction", tags=["predict"])
def predict_extinction(body: FlexInput):
    return core.predict_extinction(**body.model_dump())


@app.post("/api/predict/burn-time", tags=["predict"])
def predict_burn_time(body: FlexInput):
    return core.predict_burn_time(**body.model_dump())


@app.post("/api/what-if", tags=["predict"], summary="Curve for one slider")
def what_if(body: WhatIfInput):
    d = body.model_dump()
    return core.what_if(d.pop("model"), d.pop("vary"), points=d.pop("points"), **d)


@app.get("/api/model", tags=["predict"], summary="Validation metrics and out-of-fold predictions")
def model():
    return core.model_info()


@app.post("/api/chat", tags=["chat"], summary="Research assistant (needs DEEPSEEK_API_KEY or ANTHROPIC_API_KEY)")
def chat_endpoint(body: ChatInput):
    return chat([m.model_dump() for m in body.messages], body.context)

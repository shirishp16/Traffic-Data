# backend/app/main.py
from datetime import datetime, timedelta, timezone
from typing import Optional, List


from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, desc


from .settings import TOMTOM_API_KEY
from .tomtom import get_flow_by_point
from .db import SessionLocal
from .models import FlowObservation, Intersection


app = FastAPI(title="City Congestion API", version="0.2")

# CORS for local dev / future frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    with SessionLocal() as s:
        i_count = s.scalar(select(func.count()).select_from(Intersection))
        o_count = s.scalar(select(func.count()).select_from(FlowObservation))
    return {"ok": True, "intersections": i_count, "observations": o_count}

@app.get("/probe")
def probe(lat: float, lon: float):
    if not TOMTOM_API_KEY:
        raise HTTPException(status_code=500, detail="Missing TOMTOM_API_KEY")
    try:
        data = get_flow_by_point(lat, lon, TOMTOM_API_KEY)
        seg = data.get("flowSegmentData", {})
        return {
            "currentSpeed": seg.get("currentSpeed"),
            "freeFlowSpeed": seg.get("freeFlowSpeed"),
            "currentTravelTime": seg.get("currentTravelTime"),
            "freeFlowTravelTime": seg.get("freeFlowTravelTime"),
            "confidence": seg.get("confidence"),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    

@app.get("/latest", summary="Latest N observations across all intersections")
def latest(limit: int = Query(100, ge=1, le=2000)):
    with SessionLocal() as s:
        q = (
            select(
                FlowObservation.id,
                FlowObservation.ts_utc,
                FlowObservation.current_speed,
                FlowObservation.freeflow_speed,
                FlowObservation.confidence,
                Intersection.id.label("intersection_id"),
                Intersection.name,
                Intersection.lat,
                Intersection.lon,
            )
            .join(Intersection, Intersection.id == FlowObservation.intersection_id)
            .order_by(desc(FlowObservation.ts_utc))
            .limit(limit)
        )
        rows = s.execute(q).mappings().all()
    return {"rows": rows}

@app.get("/latest_snapshot", summary="All observations at the latest timestamp")
def latest_snapshot():
    with SessionLocal() as s:
        latest_ts = s.scalar(select(func.max(FlowObservation.ts_utc)))
        if not latest_ts:
            return {"rows": []}
        q = (
            select(
                FlowObservation.id,
                FlowObservation.ts_utc,
                FlowObservation.current_speed,
                FlowObservation.freeflow_speed,
                FlowObservation.confidence,
                Intersection.id.label("intersection_id"),
                Intersection.name,
                Intersection.lat,
                Intersection.lon,
            )
            .join(Intersection, Intersection.id == FlowObservation.intersection_id)
            .where(FlowObservation.ts_utc == latest_ts)
            .order_by(Intersection.id)
        )
        rows = s.execute(q).mappings().all()
    return {"ts": latest_ts, "rows": rows}

def _nearest_intersection(s, lat: float, lon: float):
    # Simple Python-side nearest search (fine for tens/hundreds of points)
    all_i = s.execute(
        select(Intersection.id, Intersection.lat, Intersection.lon, Intersection.name)
    ).all()
    if not all_i:
        return None
    best = min(
        all_i,
        key=lambda r: (r.lat - lat) ** 2 + (r.lon - lon) ** 2,
    )
    return best

@app.get("/series", summary="Time series for an intersection (by id or nearest to lat/lon)")
def series(
    intersection_id: Optional[int] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    hours: int = Query(6, ge=1, le=168),
):
    with SessionLocal() as s:
        if intersection_id is None:
            if lat is None or lon is None:
                raise HTTPException(
                    status_code=400,
                    detail="Provide intersection_id or lat+lon",
                )
            nearest = _nearest_intersection(s, lat, lon)
            if nearest is None:
                return {"rows": []}
            intersection_id = nearest.id


        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = (
            select(
                FlowObservation.ts_utc,
                FlowObservation.current_speed,
                FlowObservation.freeflow_speed,
                FlowObservation.confidence,
            )
            .where(FlowObservation.intersection_id == intersection_id)
            .where(FlowObservation.ts_utc >= since)
            .order_by(FlowObservation.ts_utc)
        )
        rows = s.execute(q).all()
    return {
        "intersection_id": intersection_id,
        "rows": [
            {
                "ts": r.ts_utc,
                "current_speed": r.current_speed,
                "freeflow_speed": r.freeflow_speed,
                "confidence": r.confidence,
                "ratio": (r.current_speed / r.freeflow_speed) if r.freeflow_speed else None,
            }
            for r in rows
        ],
    }

@app.get("/stats", summary="Basic stats over the last N hours")
def stats(hours: int = Query(6, ge=1, le=168)):
    with SessionLocal() as s:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Aggregate per intersection
        q = (
            select(
                Intersection.id.label("intersection_id"),
                Intersection.name,
                Intersection.lat,
                Intersection.lon,
                func.count(FlowObservation.id).label("n"),
                func.avg(FlowObservation.current_speed).label("avg_current"),
                func.avg(FlowObservation.freeflow_speed).label("avg_freeflow"),
            )
            .join(Intersection, Intersection.id == FlowObservation.intersection_id)
            .where(FlowObservation.ts_utc >= since)
            .group_by(Intersection.id)
        )
        rows = s.execute(q).mappings().all()

    # Compute ratios and pick worst
    for r in rows:
        avg_c = r["avg_current"] or 0.0
        avg_f = r["avg_freeflow"] or 0.0
        r["avg_ratio"] = (avg_c / avg_f) if avg_f else None
        r["avg_deficit"] = (avg_f - avg_c) if (avg_f and avg_c is not None) else None


    # Worst = lowest avg_ratio (most congested)
    worst = None
    rows_with_ratio = [r for r in rows if r.get("avg_ratio") is not None]
    if rows_with_ratio:
        worst = min(rows_with_ratio, key=lambda r: r["avg_ratio"]) # smallest ratio


    return {"hours": hours, "per_intersection": rows, "worst": worst}




# To run: uvicorn app.main:app --reload --port 8000
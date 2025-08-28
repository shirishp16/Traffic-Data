from __future__ import annotations
import argparse
from datetime import datetime, timezone
import time
from typing import Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .tomtom import get_flow_by_point
from .settings import (
    TOMTOM_API_KEY, BBOX_SW, BBOX_NE, DEFAULT_CITY, INGEST_ROWS, INGEST_COLS
)
from .db import SessionLocal, engine
from .models import Base, Intersection, FlowObservation


# --- Utilities ---


def parse_latlon(s: str) -> Tuple[float, float]:
    lat_str, lon_str = s.split(",")
    return float(lat_str), float(lon_str)



def generate_grid(sw: str, ne: str, rows: int, cols: int) -> List[Tuple[float, float, str]]:
    """Return a list of (lat, lon, name) across a bbox grid."""
    sw_lat, sw_lon = parse_latlon(sw)
    ne_lat, ne_lon = parse_latlon(ne)


    lat_step = (ne_lat - sw_lat) / max(rows - 1, 1)
    lon_step = (ne_lon - sw_lon) / max(cols - 1, 1)


    points = []
    for r in range(rows):
        for c in range(cols):
            lat = sw_lat + r * lat_step
            lon = sw_lon + c * lon_step
            name = f"grid_r{r}_c{c}"
            points.append((lat, lon, name))
    return points




def upsert_intersection(session, lat: float, lon: float, name: str | None) -> int:
    """Create if missing; return intersection id."""
    stmt = select(Intersection).where(Intersection.lat == lat, Intersection.lon == lon)
    row = session.execute(stmt).scalar_one_or_none()
    if row:
        return row.id
    new = Intersection(lat=lat, lon=lon, name=name)
    session.add(new)
    session.commit()
    return new.id


def store_observation(session, intersection_id: int, payload: dict) -> None:
    seg = payload.get("flowSegmentData", {}) if isinstance(payload, dict) else {}
    ts = datetime.now(timezone.utc).replace(microsecond=0)


    ins = sqlite_insert(FlowObservation.__table__).values(
        intersection_id=intersection_id,
        ts_utc=ts,
        current_speed=seg.get("currentSpeed"),
        freeflow_speed=seg.get("freeFlowSpeed"),
        current_travel_time=seg.get("currentTravelTime"),
        freeflow_travel_time=seg.get("freeFlowTravelTime"),
        confidence=seg.get("confidence"),
    )
    # Deduplicate on (intersection_id, ts_utc)
    do_nothing = ins.on_conflict_do_nothing(
        index_elements=["intersection_id", "ts_utc"]
    )
    session.execute(do_nothing)
    session.commit()


# --- Main ingest loop ---


def ingest_once(points: Iterable[Tuple[float, float, str]]):
    if not TOMTOM_API_KEY:
        raise RuntimeError("TOMTOM_API_KEY missing — set it in backend/.env")


    with SessionLocal() as session:
        for lat, lon, name in points:
            try:
                iid = upsert_intersection(session, lat, lon, name)
                data = get_flow_by_point(lat, lon, TOMTOM_API_KEY)
                store_observation(session, iid, data)
                print(f"✓ {name or iid}: {lat:.5f},{lon:.5f} stored")
            except Exception as e:
                print(f"! Failed for {lat:.5f},{lon:.5f}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Ingest TomTom flow data into SQLite")
    parser.add_argument("--mode", choices=["grid"], default="grid")
    parser.add_argument("--rows", type=int, default=INGEST_ROWS)
    parser.add_argument("--cols", type=int, default=INGEST_COLS)
    parser.add_argument("--interval", type=int, default=0, help="Minutes between runs; 0 = once")
    parser.add_argument("--iterations", type=int, default=1, help="How many cycles to run if interval > 0")
    args = parser.parse_args()

    # DEBUG PRINTS
    print("Ingest starting…")
    from .settings import DB_PATH
    print("DB_PATH:", DB_PATH)

    # Create tables if not present
    Base.metadata.create_all(bind=engine)

    # Build target points
    points = generate_grid(BBOX_SW, BBOX_NE, args.rows, args.cols)

    # Run once or on an interval
    if args.interval <= 0:
        ingest_once(points)
    else:
        iters = max(args.iterations, 1)
        for i in range(iters):
            print(f"— Ingest cycle {i+1}/{iters} —")
            ingest_once(points)
            if i < iters - 1:
                time.sleep(args.interval * 60)



if __name__ == "__main__":
    main()
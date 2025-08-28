from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Float, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index


class Base(DeclarativeBase):
    pass


class Intersection(Base):
    __tablename__ = "intersections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    __table_args__ = (
        UniqueConstraint("lat", "lon", name="uq_intersection_lat_lon"),
        Index("idx_intersection_lat_lon", "lat", "lon"),
    )


class FlowObservation(Base):
    __tablename__ = "flow_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intersection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("intersections.id"), nullable=False
    )
    ts_utc: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    current_speed: Mapped[float | None] = mapped_column(Float)
    freeflow_speed: Mapped[float | None] = mapped_column(Float)
    current_travel_time: Mapped[float | None] = mapped_column(Float)
    freeflow_travel_time: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint("intersection_id", "ts_utc", name="uq_obs_intersection_ts"),
        Index("idx_obs_intersection_ts", "intersection_id", "ts_utc"),
    )
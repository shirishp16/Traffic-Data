from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from .settings import DB_PATH

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
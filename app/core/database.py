# app/core/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# --- MEJORA DE CONEXIÓN PARA LA NUBE (Neon/Postgres) ---
engine = create_engine(
    settings.DATABASE_URL,
    # pool_recycle: Cierra conexiones después de 30 minutos (1800s) 
    # para evitar que el servidor las corte de golpe.
    pool_recycle=1800,
    # pool_pre_ping: Comprueba si la conexión está viva antes de cada consulta. 
    # Si está muerta, la reconecta automáticamente.
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
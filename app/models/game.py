from sqlalchemy import Column, String, DateTime, Integer
from app.core.database import Base

class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, index=True) # El ID raro (6B00...)
    date = Column(String)                             # Fecha (24/01/2026)
    home_team = Column(String)                        # Equipo Local (Oviedo CB)
    visitor_team = Column(String)                     # Equipo Visitante (Pumarin)
    score_local = Column(Integer, nullable=True)      # Puntos Local (si los tenemos)
    score_visitor = Column(Integer, nullable=True)    # Puntos Visitante
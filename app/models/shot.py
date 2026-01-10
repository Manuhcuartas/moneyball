from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Float, Boolean, BigInteger, Integer
from app.core.database import Base

class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # IDs externos
    game_id: Mapped[str] = mapped_column(String, index=True)
    team_id: Mapped[int] = mapped_column(BigInteger, index=True)
    player_id: Mapped[str] = mapped_column(String, index=True)
    
    # Datos del tiro
    dorsal: Mapped[str] = mapped_column(String(10))
    period: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(50))
    
    # Coordenadas
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    zone: Mapped[str] = mapped_column(String(20))
    is_made: Mapped[bool] = mapped_column(Boolean, default=False)
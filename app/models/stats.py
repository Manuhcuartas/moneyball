from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from app.core.database import Base # Asumo que tu Base viene de aquí

class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, index=True) # Este será el HASH del partido
    jornada = Column(String, nullable=True)
    fecha = Column(String, nullable=True)
    equipo_local = Column(String)
    equipo_visitante = Column(String)
    puntos_local = Column(Integer)
    puntos_visitante = Column(Integer)
    estado = Column(String) # "FINALIZADO"
    
    # Relación con las stats
    stats = relationship("PlayerStat", back_populates="game", cascade="all, delete-orphan")

class PlayerStat(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, ForeignKey("games.id")) # Relación con el partido
    
    equipo = Column(String) # Nombre del equipo del jugador
    nombre = Column(String)
    dorsal = Column(String)
    es_titular = Column(Boolean, default=False)
    
    minutos = Column(String) # "24:36"
    puntos = Column(Integer)
    valoracion = Column(Integer)
    mas_menos = Column(Integer)
    
    # Rebotes
    rebotes_total = Column(Integer)
    rebotes_def = Column(Integer)
    rebotes_of = Column(Integer)
    
    # Asistencias y perdidas
    asistencias = Column(Integer)
    perdidas = Column(Integer)
    recuperaciones = Column(Integer)
    
    # Tiros (Anotados / Intentados)
    t1_anotados = Column(Integer)
    t1_intentados = Column(Integer)
    t2_anotados = Column(Integer)
    t2_intentados = Column(Integer)
    t3_anotados = Column(Integer)
    t3_intentados = Column(Integer)
    
    # Faltas
    faltas_cometidas = Column(Integer)
    faltas_recibidas = Column(Integer)

    game = relationship("Game", back_populates="stats")
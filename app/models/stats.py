from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from app.core.database import Base

# 1. TABLA MAESTRA DE EQUIPOS
class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True) # Nombre Normalizado (ej: "C.B. Pumarín")
    
    # Relaciones
    players = relationship("Player", back_populates="team")
    # Para partidos, necesitamos diferenciar local y visitante
    home_games = relationship("Game", foreign_keys="[Game.home_team_id]", back_populates="home_team")
    visitor_games = relationship("Game", foreign_keys="[Game.visitor_team_id]", back_populates="visitor_team")

# 2. TABLA MAESTRA DE JUGADORES
class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True) # Nombre limpio (ej: "Manuel Cuartas")
    
    # Equipo actual (se actualiza con el último partido procesado)
    team_id = Column(Integer, ForeignKey("teams.id"))
    
    team = relationship("Team", back_populates="players")
    stats = relationship("PlayerStat", back_populates="player")

# 3. PARTIDOS (Refactorizado con FKs)
class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, index=True) # Hash del partido
    jornada = Column(String)
    fecha = Column(String)
    
    # RELACIONES CLAVE
    home_team_id = Column(Integer, ForeignKey("teams.id"))
    visitor_team_id = Column(Integer, ForeignKey("teams.id"))
    
    puntos_local = Column(Integer)
    puntos_visitante = Column(Integer)
    estado = Column(String)

    # Propiedades de navegación
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    visitor_team = relationship("Team", foreign_keys=[visitor_team_id], back_populates="visitor_games")
    stats = relationship("PlayerStat", back_populates="game", cascade="all, delete-orphan")

# 4. ESTADÍSTICAS (Ahora vinculadas a Player, no solo texto)
class PlayerStat(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, index=True)
    
    # Vínculos
    game_id = Column(String, ForeignKey("games.id"))
    player_id = Column(Integer, ForeignKey("players.id")) # <--- ESTO ES LO IMPORTANTE
    
    # Mantenemos redundancia útil para queries rápidas sin joins complejos
    dorsal = Column(String)
    es_titular = Column(Boolean, default=False)
    
    # Stats numéricas
    minutos = Column(String)
    puntos = Column(Integer)
    valoracion = Column(Integer)
    mas_menos = Column(Integer)
    rebotes_total = Column(Integer)
    rebotes_def = Column(Integer)
    rebotes_of = Column(Integer)
    asistencias = Column(Integer)
    perdidas = Column(Integer)
    recuperaciones = Column(Integer)
    t1_anotados = Column(Integer)
    t1_intentados = Column(Integer)
    t2_anotados = Column(Integer)
    t2_intentados = Column(Integer)
    t3_anotados = Column(Integer)
    t3_intentados = Column(Integer)
    faltas_cometidas = Column(Integer)
    faltas_recibidas = Column(Integer)

    # Relaciones
    game = relationship("Game", back_populates="stats")
    player = relationship("Player", back_populates="stats")

# 5. EVOLUCION DEL MARCADOR (Game Flow)
class GameFlow(Base):
    __tablename__ = "game_flow"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, ForeignKey("games.id"))
    
    minute = Column(String) # "Q1 08:30" or incrementing "1", "2"... 
    sequence_order = Column(Integer) # To sort chronologically
    puntos_local = Column(Integer)
    puntos_visitante = Column(Integer)
    diff = Column(Integer) # local - visitante

    game = relationship("Game", back_populates="flow")

# Add relationship to Game
Game.flow = relationship("GameFlow", back_populates="game", cascade="all, delete-orphan")
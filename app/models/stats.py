from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from app.core.database import Base


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    logo_url = Column(String, default=None)

    players = relationship("Player", back_populates="team")
    home_games = relationship("Game", foreign_keys="[Game.home_team_id]", back_populates="home_team")
    visitor_games = relationship("Game", foreign_keys="[Game.visitor_team_id]", back_populates="visitor_team")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"))

    team = relationship("Team", back_populates="players")
    stats = relationship("PlayerStat", back_populates="player")


class Game(Base):
    __tablename__ = "games"

    id = Column(String, primary_key=True, index=True)
    jornada = Column(String)
    fecha = Column(String)

    home_team_id = Column(Integer, ForeignKey("teams.id"))
    visitor_team_id = Column(Integer, ForeignKey("teams.id"))

    puntos_local = Column(Integer)
    puntos_visitante = Column(Integer)
    estado = Column(String)

    time = Column(String)
    venue = Column(String)
    address = Column(String)
    video_url = Column(String)

    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_games")
    visitor_team = relationship("Team", foreign_keys=[visitor_team_id], back_populates="visitor_games")
    stats = relationship("PlayerStat", back_populates="game", cascade="all, delete-orphan")


class PlayerStat(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, ForeignKey("games.id"))
    player_id = Column(Integer, ForeignKey("players.id"))

    dorsal = Column(String)
    es_titular = Column(Boolean, default=False)

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

    game = relationship("Game", back_populates="stats")
    player = relationship("Player", back_populates="stats")


class GameFlow(Base):
    __tablename__ = "game_flow"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(String, ForeignKey("games.id"))

    minute = Column(String)
    sequence_order = Column(Integer)
    puntos_local = Column(Integer)
    puntos_visitante = Column(Integer)
    diff = Column(Integer)

    game = relationship("Game", back_populates="flow")


Game.flow = relationship("GameFlow", back_populates="game", cascade="all, delete-orphan")


class TeamStanding(Base):
    __tablename__ = "team_standings"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"))

    season = Column(String, index=True)
    position = Column(Integer)
    played = Column(Integer)
    won = Column(Integer)
    lost = Column(Integer)
    points = Column(Integer)
    win_rate = Column(Float)
    updated_at = Column(DateTime, default=None)

    team = relationship("Team", back_populates="standing")


Team.standing = relationship("TeamStanding", back_populates="team", uselist=False, cascade="all, delete-orphan")
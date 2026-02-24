from pydantic import BaseModel
from typing import List, Optional


class PlayerBoxScore(BaseModel):
    player_id: int
    player_name: str
    photo_url: Optional[str] = None
    dorsal: str
    minutos: str
    puntos: int
    valoracion: int
    mas_menos: int
    rebotes: int
    asistencias: int
    es_titular: bool


class TeamBoxScore(BaseModel):
    team_id: int
    team_name: str
    players: List[PlayerBoxScore]


class GameResponse(BaseModel):
    id: str
    jornada: Optional[str]
    fecha: Optional[str]
    estado: Optional[str]
    home_team: Optional[str]
    visitor_team: Optional[str]
    puntos_local: Optional[int]
    puntos_visitante: Optional[int]
    time: Optional[str] = None
    venue: Optional[str] = None
    address: Optional[str] = None
    video_url: Optional[str] = None
    home_team_logo: Optional[str] = None
    visitor_team_logo: Optional[str] = None

    class Config:
        orm_mode = True


class GameFlowPoint(BaseModel):
    minute: str
    diff: int
    puntos_local: int
    puntos_visitante: int


class GameDetailResponse(GameResponse):
    home_boxscore: List[PlayerBoxScore]
    visitor_boxscore: List[PlayerBoxScore]
    game_flow: List[GameFlowPoint]

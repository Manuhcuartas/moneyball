from pydantic import BaseModel
from typing import List, Optional

# --- BLOQUE ANTIGUO (Tiros y Zonas) ---
class ZoneStat(BaseModel):
    zone: str
    total_shots: int
    made_shots: int
    efficiency: float 

class GameStats(BaseModel):
    game_id: str
    team_stats: dict[int, list[ZoneStat]] 

class PlayerAdvancedStats(BaseModel):
    # Este era tu esquema antiguo basado en proxies.
    # Lo mantenemos por si usas el endpoint antiguo, pero el nuevo es mejor.
    player_id: str
    dorsal: str
    minutes_proxy: int
    points: int
    # ... resto de campos antiguos ...

class GameAdvancedStats(BaseModel):
    game_id: str
    players: list[PlayerAdvancedStats]


# --- BLOQUE NUEVO (Moneyball / Boxscore Real) ---
class MoneyballPlayerSchema(BaseModel):
    Jugador: str
    Equipo: str
    PJ: int         # Partidos Jugados
    MPP: float      # Minutos por partido (Real)
    PPP: float      # Puntos por partido
    RPP: float      # Rebotes por partido
    APP: float      # Asistencias por partido
    
    # Métricas Avanzadas Reales
    USG_pct: float  # Usage Rate real
    TS_pct: float   # True Shooting real (con Tiros Libres)
    eFG_pct: float  # Effective Field Goal
    GmSc: float     # Game Score (Impacto total)

class MoneyballResponse(BaseModel):
    total_jugadores: int
    filtros_aplicados: dict
    data: List[MoneyballPlayerSchema]
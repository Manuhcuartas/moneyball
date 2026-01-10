from pydantic import BaseModel
from typing import List

# --- BLOQUE NUEVO (Moneyball / Boxscore Real) ---
class MoneyballPlayerSchema(BaseModel):
    Jugador: str
    Equipo: str
    PJ: int         
    MPP: float      
    PPP: float      
    RPP: float      
    APP: float      
    
    # Métricas Avanzadas
    USG_pct: float  
    TS_pct: float   
    eFG_pct: float  
    GmSc: float     

    # --- CAMPOS NUEVOS IMPRESCINDIBLES ---
    Posicion: str
    Rol_Tactical: str  # Con guion bajo
    
    # Percentiles para el Radar
    P_USG: float
    P_AST: float
    P_REB: float
    P_3PA: float
    P_EFF: float
    P_DEF: float

class MoneyballResponse(BaseModel):
    total_jugadores: int
    filtros_aplicados: dict
    data: List[MoneyballPlayerSchema]

# DTO Maestro para el perfil individual (Stats + Mapa de Tiros)
from app.schemas.shot import ShotResponse # Asegúrate de tener este import
class PlayerProfileResponse(BaseModel):
    profile: MoneyballPlayerSchema
    shots: List[ShotResponse]

# --- BLOQUE ANTIGUO (Déjalo si quieres compatibilidad con código viejo) ---
class ZoneStat(BaseModel):
    zone: str
    total_shots: int
    made_shots: int
    efficiency: float 
class GameStats(BaseModel):
    game_id: str
    team_stats: dict[int, list[ZoneStat]] 
class PlayerAdvancedStats(BaseModel):
    player_id: str
    dorsal: str
    minutes_proxy: int
    points: int
    fg2_made: int
    fg2_attempted: int
    fg3_made: int
    fg3_attempted: int
    efg_percentage: float
    ts_proxy: float
    shot_distribution_2p: float
    shot_distribution_3p: float
class GameAdvancedStats(BaseModel):
    game_id: str
    players: list[PlayerAdvancedStats]
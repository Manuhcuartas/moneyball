from pydantic import BaseModel
from typing import List


class MoneyballPlayerSchema(BaseModel):
    Jugador: str
    Equipo: str
    PJ: int
    MPP: float
    PPP: float
    RPP: float
    APP: float

    # Advanced metrics
    USG_pct: float
    TS_pct: float
    eFG_pct: float
    GmSc: float

    # Tactical role
    Rol_Tactical: str

    # Percentiles for radar chart (0–1 range)
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


from app.schemas.shot import ShotResponse


class PlayerProfileResponse(BaseModel):
    """Combined profile: advanced stats + shot chart data."""
    profile: MoneyballPlayerSchema
    shots: List[ShotResponse]
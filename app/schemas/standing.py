from pydantic import BaseModel
from typing import List, Optional


class StandingBase(BaseModel):
    position: int
    team_name: str
    played: int
    won: int
    lost: int
    points: int
    win_rate: float
    streak: Optional[str] = None


class StandingResponse(StandingBase):
    team_id: int
    season: str
    team_logo: Optional[str] = None


class StandingsListResponse(BaseModel):
    season: str
    standings: List[StandingResponse]

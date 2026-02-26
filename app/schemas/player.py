from pydantic import BaseModel
from typing import Optional, List


class PlayerSeasonStats(BaseModel):
    """Player season averages compared to league averages"""
    # Player averages
    minutes_avg: float = 0
    points_avg: float = 0
    valoracion_avg: float = 0
    mas_menos_avg: float = 0
    rebounds_avg: float = 0
    assists_avg: float = 0
    steals_avg: float = 0
    turnovers_avg: float = 0
    blocks_avg: float = 0
    fouls_drawn_avg: float = 0
    fouls_committed_avg: float = 0

    # League averages
    league_minutes_avg: float = 0
    league_points_avg: float = 0
    league_valoracion_avg: float = 0
    league_mas_menos_avg: float = 0
    league_rebounds_avg: float = 0
    league_assists_avg: float = 0
    league_steals_avg: float = 0
    league_turnovers_avg: float = 0
    league_blocks_avg: float = 0
    league_fouls_drawn_avg: float = 0
    league_fouls_committed_avg: float = 0

    # Percentiles
    points_pctile: int = 0
    rebounds_pctile: int = 0
    assists_pctile: int = 0
    steals_pctile: int = 0
    blocks_pctile: int = 0
    valoracion_pctile: int = 0
    mas_menos_pctile: int = 0

    # Shooting splits (player)
    ft_pct: float = 0
    fg_pct: float = 0
    two_pct: float = 0
    three_pct: float = 0

    # Shooting splits (league)
    league_ft_pct: float = 0
    league_fg_pct: float = 0
    league_two_pct: float = 0
    league_three_pct: float = 0

    # Season totals
    games_played: int = 0
    total_points: int = 0
    total_minutes: float = 0
    total_valoracion: int = 0
    total_rebounds: int = 0
    total_assists: int = 0
    total_steals: int = 0
    total_turnovers: int = 0
    total_blocks: int = 0

    # Advanced Stats
    ts_pct: float = 0.0
    efg_pct: float = 0.0
    usg_pct: float = 0.0


class PlayerGameLogEntry(BaseModel):
    """Single game stats for a player"""
    date: str
    opponent: str
    is_home: bool = False
    game_id: Optional[str] = None
    minutes: str
    points: int
    valoracion: int
    mas_menos: int
    rebounds: int
    assists: int
    steals: int
    turnovers: int
    ft_made: int
    ft_attempted: int
    fg_made: int
    fg_attempted: int
    three_made: int
    three_attempted: int

    # Advanced Stats
    ts_pct: float = 0.0
    efg_pct: float = 0.0
    usg_pct: float = 0.0


class PlayerProfileResponse(BaseModel):
    """Complete player profile"""
    player_id: int
    player_name: str
    team_name: str
    photo_url: Optional[str] = None
    ppg: Optional[float] = None
    mpg: Optional[float] = None
    season_stats: Optional[PlayerSeasonStats] = None
    game_log: List[PlayerGameLogEntry] = []

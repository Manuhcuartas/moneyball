from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.stats import TeamStanding, Team
from app.schemas.standing import StandingsListResponse, StandingResponse

router = APIRouter()


@router.get("/standings", response_model=StandingsListResponse)
def get_standings(
    season: str = Query(None, description="Season identifier, e.g. '25/26'"),
    db: Session = Depends(get_db),
):
    """Return current standings for the league, defaulting to the most recent season."""
    query = db.query(TeamStanding).join(Team)

    if season:
        query = query.filter(TeamStanding.season == season)
    else:
        latest = db.query(TeamStanding.season).order_by(TeamStanding.id.desc()).first()
        if latest:
            query = query.filter(TeamStanding.season == latest[0])

    standings = query.order_by(TeamStanding.position.asc()).all()

    if not standings:
        return {"season": season or "Unknown", "standings": []}

    current_season = standings[0].season

    return {
        "season": current_season,
        "standings": [
            StandingResponse(
                team_id=s.team_id,
                team_name=s.team.name,
                season=s.season,
                position=s.position,
                played=s.played,
                won=s.won,
                lost=s.lost,
                points=s.points,
                win_rate=s.win_rate,
                streak=None,
                team_logo=s.team.logo_url if s.team else None,
            )
            for s in standings
        ],
    }

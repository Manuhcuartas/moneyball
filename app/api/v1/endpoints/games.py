from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.stats import Game, PlayerStat, Player, Team, GameFlow
from app.schemas.game import GameResponse, GameDetailResponse, PlayerBoxScore, GameFlowPoint

router = APIRouter()

@router.get("/", response_model=List[GameResponse])
def get_games(
    jornada: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Game)
    if jornada:
        query = query.filter(Game.jornada == jornada)
    
    # Order by date descending tentatively, or jornada
    games = query.order_by(Game.fecha.desc()).limit(500).all()
    
    # Map to schema manually if needed, or let Pydantic handle it via orm_mode
    # We need team names. The model has relationships.
    results = []
    for g in games:
        results.append(GameResponse(
            id=g.id,
            jornada=g.jornada,
            fecha=g.fecha,
            estado=g.estado,
            home_team=g.home_team.name if g.home_team else "Unknown",
            visitor_team=g.visitor_team.name if g.visitor_team else "Unknown",
            puntos_local=g.puntos_local,
            puntos_visitante=g.puntos_visitante
        ))
    return results

@router.get("/{game_id}", response_model=GameDetailResponse)
def get_game_detail(game_id: str, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
        
    stats = db.query(PlayerStat).filter(PlayerStat.game_id == game_id).all()
    
    home_stats = []
    visitor_stats = []
    
    for s in stats:
        # Determine team via Player
        p = s.player
        box = PlayerBoxScore(
            player_id=p.id,
            player_name=p.name,
            dorsal=s.dorsal,
            minutos=s.minutos,
            puntos=s.puntos,
            valoracion=s.valoracion,
            mas_menos=s.mas_menos,
            rebotes=s.rebotes_total,
            asistencias=s.asistencias,
            es_titular=s.es_titular
        )
        
        if p.team_id == game.home_team_id:
            home_stats.append(box)
        else:
            visitor_stats.append(box)
            
    # Sort by minutes desc or points? usually minutes or valuation
    # Let's sort by dorsal as string for now
    
    # Fetch Flow
    flow_data = db.query(GameFlow).filter(GameFlow.game_id == game_id).order_by(GameFlow.sequence_order).all()
    flow_points = [
        GameFlowPoint(
            minute=f.minute, 
            diff=f.diff, 
            puntos_local=f.puntos_local, 
            puntos_visitante=f.puntos_visitante
        ) for f in flow_data
    ]

    return GameDetailResponse(
        id=game.id,
        jornada=game.jornada,
        fecha=game.fecha,
        estado=game.estado,
        home_team=game.home_team.name if game.home_team else "Unknown",
        visitor_team=game.visitor_team.name if game.visitor_team else "Unknown",
        puntos_local=game.puntos_local,
        puntos_visitante=game.puntos_visitante,
        home_boxscore=home_stats,
        visitor_boxscore=visitor_stats,
        game_flow=flow_points
    )

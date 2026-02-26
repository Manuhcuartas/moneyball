from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.stats import Player, PlayerSeasonStat
from app.schemas.player import PlayerProfileResponse, PlayerSeasonStats, PlayerGameLogEntry
from typing import List

router = APIRouter()


@router.get("/{player_id}/profile", response_model=PlayerProfileResponse)
def get_player_profile(player_id: int, db: Session = Depends(get_db)):
    """Return player profile with season stats and game log from federation API."""
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    photo_url = None
    if player.componente_id:
        photo_url = f"https://appaficionfbpa.gesdeportiva.es/imagenes.ashx?tipo=jugadorclub&id={player.componente_id}"

    team_name = player.team.name if player.team else "Unknown"

    response = PlayerProfileResponse(
        player_id=player.id,
        player_name=player.name,
        team_name=team_name,
        photo_url=photo_url,
        ppg=player.ppg,
        mpg=player.mpg,
    )

    # The DB now locally holds stats, so we proceed for all players.

    # Fetch season stats from local DB
    # Fetch season stats from local DB
    from app.models.stats import PlayerSeasonStat, LeagueAverage
    stat = db.query(PlayerSeasonStat).filter(PlayerSeasonStat.player_id == player_id).first()
    league_stat = db.query(LeagueAverage).first()
    
    if stat:
        # Convert total_minutes string "280:15" to a float if possible, or 0
        try:
            total_minutes = float(stat.total_minutes.split(':')[0]) + float(stat.total_minutes.split(':')[1])/60.0 if ':' in stat.total_minutes else float(stat.total_minutes)
        except:
            total_minutes = 0.0
            
        response.season_stats = PlayerSeasonStats(
            minutes_avg=stat.minutes_avg,
            points_avg=stat.points_avg,
            valoracion_avg=stat.valoracion_avg,
            mas_menos_avg=stat.mas_menos_avg,
            rebounds_avg=stat.rebounds_avg,
            assists_avg=stat.assists_avg,
            steals_avg=stat.steals_avg,
            turnovers_avg=stat.turnovers_avg,
            blocks_avg=stat.blocks_avg,
            fouls_drawn_avg=stat.fouls_drawn_avg,
            fouls_committed_avg=stat.fouls_committed_avg,
            
            points_pctile=stat.points_pctile,
            rebounds_pctile=stat.rebounds_pctile,
            assists_pctile=stat.assists_pctile,
            steals_pctile=stat.steals_pctile,
            blocks_pctile=stat.blocks_pctile,
            valoracion_pctile=stat.valoracion_pctile,
            mas_menos_pctile=stat.mas_menos_pctile,
            
            ts_pct=stat.ts_pct,
            efg_pct=stat.efg_pct,
            usg_pct=stat.usg_pct,

            league_minutes_avg=league_stat.minutes_avg if league_stat else 0.0,
            league_points_avg=league_stat.points_avg if league_stat else 0.0,
            league_valoracion_avg=league_stat.valoracion_avg if league_stat else 0.0,
            league_mas_menos_avg=league_stat.mas_menos_avg if league_stat else 0.0,
            league_rebounds_avg=league_stat.rebounds_avg if league_stat else 0.0,
            league_assists_avg=league_stat.assists_avg if league_stat else 0.0,
            league_steals_avg=league_stat.steals_avg if league_stat else 0.0,
            league_turnovers_avg=league_stat.turnovers_avg if league_stat else 0.0,
            league_blocks_avg=league_stat.blocks_avg if league_stat else 0.0,
            league_fouls_drawn_avg=league_stat.fouls_drawn_avg if league_stat else 0.0,
            league_fouls_committed_avg=league_stat.fouls_committed_avg if league_stat else 0.0,

            ft_pct=stat.ft_pct,
            fg_pct=stat.fg_pct,
            two_pct=stat.two_pct,
            three_pct=stat.three_pct,

            league_ft_pct=league_stat.ft_pct if league_stat else 0.0,
            league_fg_pct=league_stat.fg_pct if league_stat else 0.0,
            league_two_pct=league_stat.two_pct if league_stat else 0.0,
            league_three_pct=league_stat.three_pct if league_stat else 0.0,

            games_played=stat.games_played,
            total_points=stat.total_points,
            total_minutes=total_minutes,
            total_valoracion=stat.total_valoracion,
            total_rebounds=stat.total_rebounds,
            total_assists=stat.total_assists,
            total_steals=stat.total_steals,
            total_turnovers=stat.total_turnovers,
            total_blocks=stat.total_blocks,
        )

    # Fetch game log from local DB, parse date strings and sort them chronologically (newest first)
    from app.models.stats import PlayerStat, Game, Player as DBPlayer
    from datetime import datetime
    from app.services.analytics import _parse_minutes as parse_minutes
    
    logs = db.query(PlayerStat).join(Game, PlayerStat.game_id == Game.id).filter(PlayerStat.player_id == player_id).all()
    
    def parse_date(date_str):
        try:
            return datetime.strptime(date_str, "%d/%m/%Y")
        except:
            return datetime.min

    logs = sorted(logs, key=lambda x: parse_date(x.game.fecha) if x.game and x.game.fecha else datetime.min, reverse=True)
    
    # Pre-fetch team totals for USG%
    game_ids = [entry.game_id for entry in logs if entry.game_id]
    all_game_stats = []
    if game_ids:
        all_game_stats = db.query(PlayerStat).join(DBPlayer, PlayerStat.player_id == DBPlayer.id).filter(PlayerStat.game_id.in_(game_ids)).all()
        
    game_team_totals = {}
    for s in all_game_stats:
        if s.player.team_id == player.team_id:
            gid = s.game_id
            if gid not in game_team_totals:
                game_team_totals[gid] = {"fga": 0, "fta": 0, "tov": 0, "mp": 0.0}
            game_team_totals[gid]["fga"] += (s.t2_intentados or 0) + (s.t3_intentados or 0)
            game_team_totals[gid]["fta"] += (s.t1_intentados or 0)
            game_team_totals[gid]["tov"] += (s.perdidas or 0)
            game_team_totals[gid]["mp"] += parse_minutes(s.minutos)

    for entry in logs:
        # Determine opponent and home status
        is_home = (entry.game.home_team_id == player.team_id)
        opponent = entry.game.visitor_team.name if is_home and entry.game.visitor_team else (entry.game.home_team.name if entry.game.home_team else "Unknown")

        pts = entry.puntos or 0
        fga = (entry.t2_intentados or 0) + (entry.t3_intentados or 0)
        fgm = (entry.t2_anotados or 0) + (entry.t3_anotados or 0)
        t3m = entry.t3_anotados or 0
        fta = entry.t1_intentados or 0
        tov = entry.perdidas or 0
        mp = parse_minutes(entry.minutos)

        ts = (pts / (2 * (fga + 0.44 * fta)) * 100.0) if fga + fta > 0 else 0.0
        efg = ((fgm + 0.5 * t3m) / fga * 100.0) if fga > 0 else 0.0
        
        usg = 0.0
        tt = game_team_totals.get(entry.game_id)
        if tt and tt["mp"] > 0 and (tt["fga"] + tt["fta"] + tt["tov"]) > 0:
            player_poss = fga + 0.44 * fta + tov
            team_poss = tt["fga"] + 0.44 * tt["fta"] + tt["tov"]
            usg = (100 * player_poss * (tt["mp"] / 5.0)) / (mp * team_poss) if mp > 0 else 0.0

        response.game_log.append(PlayerGameLogEntry(
            date=entry.game.fecha or "",
            opponent=opponent,
            is_home=is_home,
            minutes=entry.minutos or "00:00",
            points=pts,
            valoracion=entry.valoracion or 0,
            mas_menos=entry.mas_menos or 0,
            rebounds=entry.rebotes_total or 0,
            assists=entry.asistencias or 0,
            steals=entry.recuperaciones or 0,
            turnovers=tov,
            ft_made=entry.t1_anotados or 0,
            ft_attempted=fta,
            fg_made=fgm,
            fg_attempted=fga,
            three_made=t3m,
            three_attempted=entry.t3_intentados or 0,
            ts_pct=ts,
            efg_pct=efg,
            usg_pct=usg,
        ))

    return response


@router.get("/team/{team_name}", response_model=List[dict])
def get_team_players(team_name: str, db: Session = Depends(get_db)):
    """Return basic player list for a team (used for roster page)."""
    from app.models.stats import Team
    team = db.query(Team).filter(Team.name == team_name).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    players = db.query(Player).filter(Player.team_id == team.id).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "photo_url": f"https://appaficionfbpa.gesdeportiva.es/imagenes.ashx?tipo=jugadorclub&id={p.componente_id}" if p.componente_id else None,
            "ppg": p.ppg,
            "mpg": p.mpg,
        }
        for p in players
    ]


@router.get("/by-name/{name}")
def get_player_by_name(name: str, db: Session = Depends(get_db)):
    """Lookup player ID by name (case-insensitive). Used for name-based URL resolution."""
    from sqlalchemy import func
    player = db.query(Player).filter(func.lower(Player.name) == name.lower()).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"id": player.id, "name": player.name}


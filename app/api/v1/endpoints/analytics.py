from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.shot import Shot
from app.models.stats import PlayerStat, Player, Team
from app.services.analytics import get_advanced_stats
from app.schemas.stats import MoneyballResponse, PlayerProfileResponse, MoneyballPlayerSchema

router = APIRouter()


@router.get("/player/profile", response_model=PlayerProfileResponse)
def get_player_profile(
    name: str = Query(...),
    team: str = Query(None),
    db: Session = Depends(get_db),
):
    """Return a player's advanced stats profile and shot chart data."""
    df = get_advanced_stats(db, min_games=1, min_minutes=5)

    if df.empty:
        raise HTTPException(404, "No hay datos procesados disponibles.")

    player_row = df[df["Jugador"].str.lower() == name.lower()]

    if team:
        player_row = player_row[player_row["Equipo"].str.contains(team, case=False)]

    if player_row.empty:
        raise HTTPException(404, f"Jugador '{name}' no encontrado en las estadísticas procesadas.")

    # Keep only fields defined in the schema
    schema_fields = set(MoneyballPlayerSchema.model_fields.keys())
    raw = player_row.to_dict(orient="records")[0]
    profile_data = {k: v for k, v in raw.items() if k in schema_fields}

    # Fetch shots via PlayerStat → Player linkage
    stats_jugador = (
        db.query(PlayerStat)
        .join(Player, PlayerStat.player_id == Player.id)
        .filter(Player.name == profile_data["Jugador"])
        .all()
    )

    if not stats_jugador:
        return {"profile": profile_data, "shots": []}

    game_ids = [s.game_id for s in stats_jugador]
    dorsal = stats_jugador[0].dorsal

    shots = db.query(Shot).filter(
        Shot.dorsal == dorsal,
        Shot.game_id.in_(game_ids),
    ).all()

    return {"profile": profile_data, "shots": shots}


@router.get("/season/advanced", response_model=MoneyballResponse)
def get_moneyball_stats(
    min_games: int = Query(3, description="Mínimo de partidos jugados para calificar"),
    min_minutes: int = Query(10, description="Mínimo de minutos por partido"),
    team: str = Query(None, description="Filtrar por nombre de equipo (ej: 'Pumarin')"),
    sort_by: str = Query("GmSc", description="Ordenar por: GmSc, TS%, USG%, PPP"),
    db: Session = Depends(get_db),
):
    """Return Moneyball season ranking using real box-score data (USG%, TS%, eFG%, GmSc)."""
    df = get_advanced_stats(db, min_games=min_games, min_minutes=min_minutes)

    if df.empty:
        return {"total_jugadores": 0, "filtros_aplicados": {}, "data": []}

    if team:
        df = df[df["Equipo"].str.contains(team, case=False, na=False)]

    sort_map = {
        "gmsc": "GmSc", "ts": "TS_pct", "usg": "USG_pct", "eff": "eFG_pct",
        "pts": "PPP", "reb": "RPP", "ast": "APP",
    }
    col_name = sort_map.get(sort_by.lower(), "GmSc")

    if col_name in df.columns:
        df = df.sort_values(by=col_name, ascending=False)

    df = df.fillna(0)

    return {
        "total_jugadores": len(df),
        "filtros_aplicados": {"min_games": min_games, "min_minutes": min_minutes, "team": team},
        "data": df.to_dict(orient="records"),
    }


# --- Phase 2 endpoints ---


@router.get("/teams")
def get_teams(db: Session = Depends(get_db)):
    """Return all teams with player counts (eager-loaded)."""
    teams = db.query(Team).all()
    result = []
    for team in teams:
        player_count = db.query(Player).filter(Player.team_id == team.id).count()
        result.append({
            "id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
            "player_count": player_count,
        })
    return sorted(result, key=lambda t: t["name"])


@router.get("/teams/{team_name}/roster")
def get_team_roster(
    team_name: str,
    db: Session = Depends(get_db),
):
    """Return all players for a team with their advanced stats."""
    df = get_advanced_stats(db, min_games=1, min_minutes=1)
    if df.empty:
        raise HTTPException(404, "No hay datos procesados disponibles.")

    team_df = df[df["Equipo"].str.contains(team_name, case=False, na=False)]
    if team_df.empty:
        raise HTTPException(404, f"Equipo '{team_name}' no encontrado.")

    team_df = team_df.fillna(0)

    return {
        "team": team_name,
        "total_players": len(team_df),
        "roster": team_df.to_dict(orient="records"),
    }


@router.get("/leaderboards")
def get_leaderboards(
    category: str = Query("GmSc", description="Category: GmSc, PPP, RPP, APP, TS_pct, USG_pct, eFG_pct"),
    limit: int = Query(10, description="Number of leaders to return"),
    min_games: int = Query(3),
    min_minutes: int = Query(10),
    db: Session = Depends(get_db),
):
    """Return top N players in a given statistical category."""
    df = get_advanced_stats(db, min_games=min_games, min_minutes=min_minutes)
    if df.empty:
        return {"category": category, "leaders": []}

    col_map = {
        "gmsc": "GmSc", "ppp": "PPP", "rpp": "RPP", "app": "APP",
        "ts_pct": "TS_pct", "usg_pct": "USG_pct", "efg_pct": "eFG_pct",
        "ts": "TS_pct", "usg": "USG_pct", "efg": "eFG_pct",
    }
    col = col_map.get(category.lower(), category)

    if col not in df.columns:
        raise HTTPException(400, f"Categoría '{category}' no válida. Opciones: {list(col_map.keys())}")

    top = df.nlargest(limit, col).fillna(0)
    safe_cat = col.replace("%", "_pct")

    return {
        "category": safe_cat,
        "limit": limit,
        "leaders": top.to_dict(orient="records"),
    }

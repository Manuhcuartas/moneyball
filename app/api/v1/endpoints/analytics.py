from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db

# Importamos los repositorios antiguos
from app.models.shot import Shot
from app.schemas.shot import ShotResponse
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.stats import GameStats, GameAdvancedStats, MoneyballResponse
from app.models.stats import PlayerStat

# IMPORTAMOS EL NUEVO SERVICIO DE PANDAS
from app.services.analytics import get_advanced_stats 

from app.schemas.stats import MoneyballResponse, PlayerProfileResponse

router = APIRouter()

@router.get("/player/profile", response_model=PlayerProfileResponse)
def get_player_profile(
    name: str = Query(...),
    team: str = Query(None),
    db: Session = Depends(get_db)
):
    # 1. Obtenemos Stats de TODOS (para tener los percentiles y datos procesados)
    df = get_advanced_stats(db, min_games=1, min_minutes=5)
    
    if df.empty: 
        raise HTTPException(404, "No hay datos procesados disponibles.")

    # 2. Filtramos al jugador en el DataFrame
    # Usamos lower() para evitar problemas de mayúsculas/minúsculas
    player_row = df[df['Jugador'].str.lower() == name.lower()]
    
    if team: 
        player_row = player_row[player_row['Equipo'].str.contains(team, case=False)]
        
    if player_row.empty: 
        raise HTTPException(404, f"Jugador '{name}' no encontrado en las estadísticas procesadas.")
        
    profile_data = player_row.to_dict(orient="records")[0]

    # 3. Obtenemos Tiros (LOGICA SEGURA)
    # Buscamos en la tabla raw PlayerStat por el nombre exacto que viene del DF
    stats_jugador = db.query(PlayerStat).filter(PlayerStat.nombre == profile_data['Jugador']).all()
    
    # --- CORRECCIÓN CRÍTICA ---
    # Si no encontramos filas en PlayerStat, devolvemos el perfil sin tiros
    # en lugar de dejar que el servidor explote con un IndexError.
    if not stats_jugador:
        return {"profile": profile_data, "shots": []}

    game_ids = [s.game_id for s in stats_jugador]
    
    # Asumimos el dorsal del primer registro encontrado (ahora es seguro acceder a [0])
    dorsal = stats_jugador[0].dorsal 

    # Buscamos los tiros que coincidan con dorsal y partidos de este jugador
    shots = db.query(Shot).filter(
        Shot.dorsal == dorsal,
        Shot.game_id.in_(game_ids)
    ).all()

    return {"profile": profile_data, "shots": shots}

# --- ENDPOINT NUEVO: MONEYBALL REAL (TEMPORADA COMPLETA) ---
@router.get("/season/advanced", response_model=MoneyballResponse)
def get_moneyball_stats(
    min_games: int = Query(3, description="Mínimo de partidos jugados para calificar"),
    min_minutes: int = Query(10, description="Mínimo de minutos por partido"),
    team: str = Query(None, description="Filtrar por nombre de equipo (ej: 'Pumarin')"),
    sort_by: str = Query("GmSc", description="Ordenar por: GmSc, TS%, USG%, PPP"),
    db: Session = Depends(get_db)
):
    """
    Devuelve el ranking 'Moneyball' de toda la temporada usando datos reales (Actas).
    Calcula USG%, TS%, eFG% y Game Score.
    """
    # 1. Llamamos a Pandas para que haga los cálculos matemáticos
    df = get_advanced_stats(db, min_games=min_games, min_minutes=min_minutes)
    
    if df.empty:
        return {"total_jugadores": 0, "filtros_aplicados": {}, "data": []}

    # 2. Filtrado por equipo (si el usuario lo pide)
    if team:
        # Filtro case-insensitive
        df = df[df['Equipo'].str.contains(team, case=False, na=False)]

    # 3. Ordenación dinámica
    sort_map = {
        "gmsc": "GmSc",
        "ts": "TS%",  # Pandas usa 'TS%', el Schema espera 'TS_pct' (lo renombramos abajo)
        "usg": "USG%",
        "eff": "eFG%",
        "pts": "PPP",
        "reb": "RPP",
        "ast": "APP"
    }
    col_name = sort_map.get(sort_by.lower(), "GmSc")
    
    if col_name in df.columns:
        df = df.sort_values(by=col_name, ascending=False)

    # 4. Mapeo de nombres para coincidir con el Schema de Pydantic
    # Pandas tiene '%' en el nombre, Pydantic prefiere no tenerlo.
    df = df.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct"
    })
    
    # Limpieza de NaNs (nulos)
    df = df.fillna(0)

    # 5. Retorno
    return {
        "total_jugadores": len(df),
        "filtros_aplicados": {
            "min_games": min_games,
            "min_minutes": min_minutes,
            "team": team
        },
        "data": df.to_dict(orient="records")
    }

# --- ENDPOINTS ANTIGUOS (Shot Chart / Proxies) ---
# Se mantienen igual, pero ten en cuenta que dependen de tener datos en la tabla 'Shot'
# Si solo usas el nuevo crawler, estos devolverán 404 o vacíos.

@router.get("/games/{game_id}/stats/players-advanced", response_model=GameAdvancedStats)
def get_game_player_advanced_stats(game_id: str, db: Session = Depends(get_db)):
    repo = AnalyticsRepository(db)
    stats = repo.get_advanced_player_stats(game_id)
    if not stats:
        # Si no hay datos antiguos, lanzamos 404
        raise HTTPException(status_code=404, detail="No se encontraron datos de tracking de tiro")
    return GameAdvancedStats(game_id=game_id, players=stats)

@router.get("/games/{game_id}/stats/zones", response_model=GameStats)
def get_game_zone_stats(game_id: str, db: Session = Depends(get_db)):
    repo = AnalyticsRepository(db)
    team_stats = repo.get_shooting_stats_by_game(game_id)
    if not team_stats:
        raise HTTPException(status_code=404, detail="No se encontraron estadísticas de zona")
    return GameStats(game_id=game_id, team_stats=team_stats)

@router.get("/games/{game_id}/shots", response_model=list[ShotResponse])
def get_game_shots(game_id: str, db: Session = Depends(get_db)):
    shots = db.query(Shot).filter(Shot.game_id == game_id).all()
    if not shots:
        raise HTTPException(status_code=404, detail="No se encontraron eventos de tiro")
    return shots


# --- PHASE 2 ENDPOINTS ---

from app.models.stats import Team, Player

@router.get("/teams")
def get_teams(db: Session = Depends(get_db)):
    """
    Returns all teams with their player count.
    """
    teams = db.query(Team).all()
    result = []
    for team in teams:
        player_count = db.query(Player).filter(Player.team_id == team.id).count()
        result.append({
            "id": team.id,
            "name": team.name,
            "player_count": player_count,
        })
    return sorted(result, key=lambda t: t["name"])


@router.get("/teams/{team_name}/roster")
def get_team_roster(
    team_name: str,
    db: Session = Depends(get_db),
):
    """
    Returns all players for a team, with their advanced stats.
    """
    df = get_advanced_stats(db, min_games=1, min_minutes=1)
    if df.empty:
        raise HTTPException(404, "No hay datos procesados disponibles.")

    team_df = df[df['Equipo'].str.contains(team_name, case=False, na=False)]
    if team_df.empty:
        raise HTTPException(404, f"Equipo '{team_name}' no encontrado.")

    team_df = team_df.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct"
    }).fillna(0)

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
    """
    Returns top N players in a given statistical category.
    """
    df = get_advanced_stats(db, min_games=min_games, min_minutes=min_minutes)
    if df.empty:
        return {"category": category, "leaders": []}

    # Map API names to Pandas column names (after get_advanced_stats renames them)
    col_map = {
        "gmsc": "GmSc", "ppp": "PPP", "rpp": "RPP", "app": "APP",
        "ts_pct": "TS_pct", "usg_pct": "USG_pct", "efg_pct": "eFG_pct",
        # Also accept without _pct
        "ts": "TS_pct", "usg": "USG_pct", "efg": "eFG_pct",
    }
    col = col_map.get(category.lower(), category)

    if col not in df.columns:
        raise HTTPException(400, f"Categoría '{category}' no válida. Opciones: {list(col_map.keys())}")

    top = df.nlargest(limit, col).fillna(0)

    # Remap category name to pydantic-safe name for response
    safe_cat = col.replace("%", "_pct")

    return {
        "category": safe_cat,
        "limit": limit,
        "leaders": top.to_dict(orient="records"),
    }

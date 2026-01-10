from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db

# Importamos los repositorios antiguos
from app.repositories.shot_repository import ShotRepository
from app.models.shot import Shot
from app.schemas.shot import ShotResponse
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.stats import GameStats, GameAdvancedStats, MoneyballResponse

# IMPORTAMOS EL NUEVO SERVICIO DE PANDAS
from app.services.analytics import get_advanced_stats 

router = APIRouter()

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
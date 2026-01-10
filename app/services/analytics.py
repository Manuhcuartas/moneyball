import pandas as pd
from sqlalchemy.orm import Session
from app.models.stats import PlayerStat, Game
from app.models.shot import Shot
from app.core.normalization import normalize_team_name

def get_advanced_stats(db: Session, min_games=3, min_minutes=10):
    # 1. CARGA DE DATOS
    df = pd.read_sql(db.query(PlayerStat).statement, db.bind)
    df_shots = pd.read_sql(db.query(Shot).statement, db.bind)
    
    if df.empty:
        return pd.DataFrame()

    # 2. PRE-PROCESAMIENTO Y NORMALIZACIÓN
    df['equipo'] = df['equipo'].apply(normalize_team_name)

    def parse_minutos(val):
        try:
            if not isinstance(val, str) or ":" not in val: return 0.0
            m, s = map(int, val.split(":"))
            return m + s/60
        except: return 0.0

    df['MP'] = df['minutos'].apply(parse_minutos)
    df['FGA'] = df['t2_intentados'] + df['t3_intentados']
    df['FG'] = df['t2_anotados'] + df['t3_anotados']
    df['FTA'] = df['t1_intentados']
    
    # Totales de equipo para métricas de posesión
    team_stats = df.groupby(['game_id', 'equipo'])[['MP', 'FGA', 'FTA', 'perdidas']].sum().reset_index()
    team_stats.columns = ['game_id', 'equipo', 'Team_MP', 'Team_FGA', 'Team_FTA', 'Team_TOV']
    df = pd.merge(df, team_stats, on=['game_id', 'equipo'])

    # 3. CÁLCULO DE MÉTRICAS AVANZADAS (Nivel Fila)
    df['eFG%'] = (df['FG'] + 0.5 * df['t3_anotados']) / df['FGA'].replace(0, 1)
    df['TS%'] = df['puntos'] / (2 * (df['FGA'] + 0.44 * df['FTA'])).replace(0, 1)
    
    player_poss = df['FGA'] + 0.44 * df['FTA'] + df['perdidas']
    team_poss = df['Team_FGA'] + 0.44 * df['Team_FTA'] + df['Team_TOV']
    df['USG%'] = 100 * (player_poss * (df['Team_MP'] / 5)) / (df['MP'].replace(0, 9999) * team_poss)
    
    df['GmSc'] = (
        df['puntos'] + 0.4 * df['FG'] - 0.7 * df['FGA'] - 0.4 * (df['t1_intentados'] - df['t1_anotados']) + 
        0.7 * df['rebotes_of'] + 0.3 * df['rebotes_def'] + df['recuperaciones'] + 
        0.7 * df['asistencias'] - 0.4 * df['faltas_cometidas'] - df['perdidas']
    )

    # 4. AGREGACIÓN ÚNICA POR JUGADOR
    final_stats = df.groupby(['nombre', 'equipo']).agg({
        'game_id': 'count',
        'MP': 'mean',
        'puntos': 'mean',
        'rebotes_total': 'mean',
        'asistencias': 'mean',
        'perdidas': 'mean',
        't3_intentados': 'mean',
        'FGA': 'mean',
        'USG%': 'mean',
        'TS%': 'mean',
        'eFG%': 'mean',
        'GmSc': 'mean'
    }).reset_index()

    final_stats.columns = [
        'Jugador', 'Equipo', 'PJ', 'MPP', 'PPP', 'RPP', 'APP', 
        'perdidas_mean', 't3_intentados_mean', 'fga_mean', 
        'USG%', 'TS%', 'eFG%', 'GmSc'
    ]

    # 5. FILTRADO SEGURO (Evita Warnings)
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & (final_stats['MPP'] >= min_minutes)
    ].copy()

    # 6. CLASIFICACIÓN DE POSICIONES Y ROLES
    def estimar_posicion(row):
        t3_rate = (row['t3_intentados_mean'] / row['fga_mean'] * 100) if row['fga_mean'] > 0 else 0
        if row['RPP'] > 7 and t3_rate < 15: return "Pívot (C/PF)"
        elif row['APP'] > 3 and t3_rate > 25: return "Base (PG/SG)"
        elif t3_rate > 40: return "Escolta/Alero (SG/SF)"
        else: return "Interior/Alero"

    def definir_rol_moneyball(row):
        if row['RPP'] > 7: return "Protector de Aro / Interior"
        elif row['APP'] > 4 and row['PPP'] > 10: return "Generador Primario (Playmaker)"
        elif row['USG%'] > 25: return "Referencia Ofensiva (Scorer)"
        else: return "Jugador de Rotación"

    final_stats['Posicion'] = final_stats.apply(estimar_posicion, axis=1)
    final_stats['Rol Tactical'] = final_stats.apply(definir_rol_moneyball, axis=1)

    # 7. REDONDEOS Y RENOMBRADO (Al final para no romper las funciones anteriores)
    final_stats['USG%'] = final_stats['USG%'].round(1)
    final_stats['TS%'] = (final_stats['TS%'] * 100).round(1)
    final_stats['eFG%'] = (final_stats['eFG%'] * 100).round(1)
    final_stats.update(final_stats[['GmSc', 'MPP', 'PPP']].round(1))

    return final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct"
    })
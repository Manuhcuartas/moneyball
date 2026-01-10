import pandas as pd
from sqlalchemy.orm import Session
from app.models.stats import PlayerStat, Game
from app.core.normalization import normalize_team_name

def get_advanced_stats(db: Session, min_games=3, min_minutes=10):
    query = db.query(PlayerStat)
    df = pd.read_sql(query.statement, db.bind)
    
    if df.empty:
        return pd.DataFrame()

    # --- 1. NORMALIZACIÓN (LA MAGIA) ---
    # Aplicamos la función a toda la columna de equipos
    df['equipo'] = df['equipo'].apply(normalize_team_name)

    # --- 2. PRE-PROCESAMIENTO ---
    def parse_minutos(val):
        try:
            if not isinstance(val, str): return 0.0
            if ":" in val:
                m, s = map(int, val.split(":"))
                return m + s/60
            return 0.0
        except:
            return 0.0

    df['MP'] = df['minutos'].apply(parse_minutos)
    
    # Cálculos básicos
    df['FGA'] = df['t2_intentados'] + df['t3_intentados']
    df['FG'] = df['t2_anotados'] + df['t3_anotados']
    df['FTA'] = df['t1_intentados']
    
    # --- 3. TOTALES DE EQUIPO ---
    # Agrupamos por Partido y Equipo NORMALIZADO
    team_cols = ['game_id', 'equipo', 'MP', 'FGA', 'FTA', 'perdidas']
    df_team = df[team_cols].groupby(['game_id', 'equipo']).sum().reset_index()
    
    df_team = df_team.rename(columns={
        'MP': 'Team_MP', 
        'FGA': 'Team_FGA', 
        'FTA': 'Team_FTA', 
        'perdidas': 'Team_TOV'
    })
    
    df = pd.merge(df, df_team, on=['game_id', 'equipo'])

    # --- 4. MÉTRICAS AVANZADAS ---
    df['eFG%'] = (df['FG'] + 0.5 * df['t3_anotados']) / df['FGA'].replace(0, 1)
    
    ts_denom = 2 * (df['FGA'] + 0.44 * df['FTA'])
    df['TS%'] = df['puntos'] / ts_denom.replace(0, 1)

    player_poss = df['FGA'] + 0.44 * df['FTA'] + df['perdidas']
    team_poss = df['Team_FGA'] + 0.44 * df['Team_FTA'] + df['Team_TOV']
    
    # USG%
    term1 = player_poss * (df['Team_MP'] / 5)
    term2 = df['MP'].replace(0, 9999) * team_poss
    df['USG%'] = 100 * (term1 / term2)
    df.loc[df['MP'] == 0, 'USG%'] = 0

    # Game Score
    df['GmSc'] = (
        df['puntos'] + 0.4 * df['FG'] - 0.7 * df['FGA'] - 0.4 * (df['t1_intentados'] - df['t1_anotados']) + 
        0.7 * df['rebotes_of'] + 0.3 * df['rebotes_def'] + df['recuperaciones'] + 
        0.7 * df['asistencias'] - 0.4 * df['faltas_cometidas'] - df['perdidas']
    )

    # --- 5. AGREGACIÓN FINAL ---
    final_stats = df.groupby(['nombre', 'equipo']).agg({
        'game_id': 'count',
        'MP': 'mean',
        'puntos': 'mean',
        'rebotes_total': 'mean',
        'asistencias': 'mean',
        'USG%': 'mean',
        'TS%': 'mean',
        'eFG%': 'mean',
        'GmSc': 'mean'
    }).reset_index()

    final_stats.columns = ['Jugador', 'Equipo', 'PJ', 'MPP', 'PPP', 'RPP', 'APP', 'USG%', 'TS%', 'eFG%', 'GmSc']

    # Filtros
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & 
        (final_stats['MPP'] >= min_minutes)
    ]

    def estimar_posicion(row):
        # Calculamos ratios clave
        ast_tov_ratio = row['APP'] / (row['perdidas_mean'] if row['perdidas_mean'] > 0 else 1)
        reb_total = row['RPP']
        # Porcentaje de sus tiros que son triples
        t3_rate = (row['t3_intentados_mean'] / (row['fga_mean'] if row['fga_mean'] > 0 else 1)) * 100
        
        if reb_total > 7 and t3_rate < 15:
            return "Pívot (C/PF)"
        elif row['APP'] > 3 and t3_rate > 25:
            return "Base (PG/SG)"
        elif t3_rate > 40:
            return "Escolta/Alero (SG/SF)"
        else:
            return "Interior/Alero"

    # Necesitamos las medias de pérdidas y tipos de tiro para el algoritmo
    # Modifica tu agregación (.agg) para incluir estos campos temporales
    stats_raw = df.groupby(['nombre', 'equipo']).agg({
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

    # Renombramos columnas internas para el cálculo
    stats_raw.columns = ['Jugador', 'Equipo', 'PJ', 'MPP', 'PPP', 'RPP', 'APP', 
                        'perdidas_mean', 't3_intentados_mean', 'fga_mean', 
                        'USG%', 'TS%', 'eFG%', 'GmSc']

    # Aplicamos la estimación
    stats_raw['Posicion'] = stats_raw.apply(estimar_posicion, axis=1)

    # Limpiamos las columnas temporales antes de devolver el DataFrame
    final_stats = stats_raw[['Jugador', 'Equipo', 'PJ', 'MPP', 'PPP', 'RPP', 'APP', 
                            'USG%', 'TS%', 'eFG%', 'GmSc', 'Posicion']]

    # Redondeos
    final_stats['USG%'] = final_stats['USG%'].round(1)
    final_stats['TS%'] = (final_stats['TS%'] * 100).round(1)
    final_stats['eFG%'] = (final_stats['eFG%'] * 100).round(1)
    final_stats['GmSc'] = final_stats['GmSc'].round(1)
    final_stats['MPP'] = final_stats['MPP'].round(1)
    final_stats['PPP'] = final_stats['PPP'].round(1)

    final_stats = final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct"
    })

    return final_stats
import pandas as pd
from sqlalchemy.orm import Session
from app.models.stats import PlayerStat
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
    
    # Cálculos de volumen de tiro
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
    
    # USG% (Usage Rate)
    df['USG%'] = 100 * (player_poss * (df['Team_MP'] / 5)) / (df['MP'].replace(0, 9999) * team_poss)
    
    # Game Score (GmSc)
    df['GmSc'] = (
        df['puntos'] + 0.4 * df['FG'] - 0.7 * df['FGA'] - 0.4 * (df['t1_intentados'] - df['t1_anotados']) + 
        0.7 * df['rebotes_of'] + 0.3 * df['rebotes_def'] + df['recuperaciones'] + 
        0.7 * df['asistencias'] - 0.4 * df['faltas_cometidas'] - df['perdidas']
    )

    # 4. PROCESAMIENTO DE PERFILES DE TIRO (MAPA DE CALOR)
    shot_profiles = pd.DataFrame()
    if not df_shots.empty:
        # Zonas de la API (Z11/Z13 son esquinas/laterales)
        df_shots['is_corner'] = df_shots['zone'].isin(['Z11-IZ', 'Z11-DE', 'Z13-IZ', 'Z13-DE'])
        # Z1 suele ser la zona restringida/bajo el aro
        df_shots['is_rim'] = df_shots['zone'].str.contains('Z1-', na=False) & ~df_shots['zone'].str.contains('Z11|Z12|Z13', na=False)

        # Agrupamos por dorsal (Usamos dorsal como proxy para unir con stats)
        shot_profiles = df_shots.groupby('dorsal').agg(
            total_mapped=('id', 'count'),
            corner_3s=('is_corner', 'sum'),
            rim_shots=('is_rim', 'sum')
        ).reset_index()
        
        # Calculamos % de frecuencia
        shot_profiles['corner_freq'] = (shot_profiles['corner_3s'] / shot_profiles['total_mapped']).fillna(0)
        shot_profiles['rim_freq'] = (shot_profiles['rim_shots'] / shot_profiles['total_mapped']).fillna(0)

    # 5. AGREGACIÓN ÚNICA POR JUGADOR
    final_stats = df.groupby(['nombre', 'equipo', 'dorsal']).agg({
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

    # Unimos con los datos de tiro (Left merge para no perder jugadores sin datos)
    if not shot_profiles.empty:
        final_stats = pd.merge(final_stats, shot_profiles[['dorsal', 'corner_freq', 'rim_freq']], on='dorsal', how='left')
        final_stats[['corner_freq', 'rim_freq']] = final_stats[['corner_freq', 'rim_freq']].fillna(0)
    else:
        final_stats['corner_freq'] = 0
        final_stats['rim_freq'] = 0

    final_stats.columns = [
        'Jugador', 'Equipo', 'Dorsal', 'PJ', 'MPP', 'PPP', 'RPP', 'APP', 
        'perdidas_mean', 't3_intentados_mean', 'fga_mean', 
        'USG%', 'TS%', 'eFG%', 'GmSc', 'Corner_Freq', 'Rim_Freq'
    ]

    # 6. FILTRADO SEGURO
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & (final_stats['MPP'] >= min_minutes)
    ].copy()

    # 7. CLASIFICACIÓN DE POSICIONES Y ROLES (TACTICAL ROLE 2.0)
    def estimar_posicion(row):
        t3_rate = (row['t3_intentados_mean'] / row['fga_mean'] * 100) if row['fga_mean'] > 0 else 0
        if row['RPP'] > 7 and t3_rate < 15: return "Pívot (C)"
        elif row['APP'] > 3.5: return "Base (PG)"
        elif t3_rate > 45: return "Alero (SF)"
        else: return "Guard/Forward"

    def definir_rol_moneyball(row):
        # Algoritmo avanzado usando datos de tracking
        usage = row['USG%']
        eff = row['eFG%']
        rim_freq = row['Rim_Freq']
        corner_freq = row['Corner_Freq']
        
        # 1. ESTRELLAS
        if usage > 28 and eff > 50: return "Estrella Ofensiva (Alpha)"
        if usage > 28: return "Amasador de Balón (High Volume)"
        
        # 2. INTERIORES
        if row['RPP'] > 8:
            if row['t3_intentados_mean'] > 2: return "Interior Abierto (Stretch Big)"
            return "Protector de Aro (Rim Runner)"
        
        # 3. PERÍMETRO / ESPECIALISTAS
        if corner_freq > 0.25: return "Especialista de Esquina (3&D)"
        if rim_freq > 0.40 and eff > 55: return "Penetrador / Slasher"
        if row['APP'] > 4.5: return "Director de Juego (Floor General)"
        if row['t3_intentados_mean'] > 5 and eff > 52: return "Francotirador (Sniper)"
        
        return "Jugador de Rotación"

    final_stats['Posicion'] = final_stats.apply(estimar_posicion, axis=1)
    final_stats['Rol Tactical'] = final_stats.apply(definir_rol_moneyball, axis=1)

    # 8. REDONDEOS Y RENOMBRADO FINAL
    final_stats['USG%'] = final_stats['USG%'].round(1)
    final_stats['TS%'] = (final_stats['TS%'] * 100).round(1)
    final_stats['eFG%'] = (final_stats['eFG%'] * 100).round(1)
    final_stats.update(final_stats[['GmSc', 'MPP', 'PPP']].round(1))

    return final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct"
    })
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from app.models.stats import PlayerStat, Player, Team
from app.models.shot import Shot

def get_advanced_stats(db: Session, min_games=3, min_minutes=10):
    """
    Genera el DataFrame maestro de Moneyball uniendo las tablas relacionales:
    PlayerStat -> Player -> Team
    """
    
    # 1. CARGA DE DATOS RELACIONAL (JOIN)
    # Seleccionamos explícitamente las columnas para aplanar el resultado
    stmt = db.query(
        PlayerStat.game_id,
        PlayerStat.dorsal,
        PlayerStat.minutos,
        PlayerStat.puntos,
        PlayerStat.valoracion,
        PlayerStat.mas_menos,
        PlayerStat.rebotes_total,
        PlayerStat.rebotes_of,
        PlayerStat.rebotes_def,
        PlayerStat.asistencias,
        PlayerStat.recuperaciones,
        PlayerStat.perdidas,
        PlayerStat.faltas_cometidas,
        PlayerStat.t1_anotados, PlayerStat.t1_intentados,
        PlayerStat.t2_anotados, PlayerStat.t2_intentados,
        PlayerStat.t3_anotados, PlayerStat.t3_intentados,
        # Traemos el nombre y equipo de las tablas maestras
        Player.name.label("nombre"),
        Team.name.label("equipo")
    ).join(Player, PlayerStat.player_id == Player.id)\
     .join(Team, Player.team_id == Team.id)\
     .statement

    df = pd.read_sql(stmt, db.bind)
    
    # Cargamos tiros
    df_shots = pd.read_sql(db.query(Shot).statement, db.bind)
    
    if df.empty:
        return pd.DataFrame()

    # 2. PRE-PROCESAMIENTO
    # Nota: Como los nombres de equipos vienen de la tabla Team (ya normalizados), 
    # no necesitamos llamar a normalize_team_name de nuevo.

    def parse_minutos(val):
        try:
            if not isinstance(val, str) or ":" not in val: return 0.0
            m, s = map(int, val.split(":"))
            return m + s/60
        except: return 0.0

    df['MP'] = df['minutos'].apply(parse_minutos)
    
    # Cálculos básicos de volumen
    df['FGA'] = df['t2_intentados'] + df['t3_intentados']
    df['FG'] = df['t2_anotados'] + df['t3_anotados']
    df['FTA'] = df['t1_intentados']
    
    # Porcentajes Reales
    df['3P%'] = (df['t3_anotados'] / df['t3_intentados'].replace(0, 1)) * 100
    df['2P%'] = (df['t2_anotados'] / df['t2_intentados'].replace(0, 1)) * 100

    # Totales de equipo (para USG%)
    team_stats = df.groupby(['game_id', 'equipo'])[['MP', 'FGA', 'FTA', 'perdidas']].sum().reset_index()
    team_stats.columns = ['game_id', 'equipo', 'Team_MP', 'Team_FGA', 'Team_FTA', 'Team_TOV']
    df = pd.merge(df, team_stats, on=['game_id', 'equipo'])

    # 3. MÉTRICAS AVANZADAS (Nivel Fila/Partido)
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

    # 4. MAPA DE CALOR (Tiros)
    shot_profiles = pd.DataFrame()
    if not df_shots.empty:
        df_shots['is_corner'] = df_shots['zone'].isin(['Z11-IZ', 'Z11-DE', 'Z13-IZ', 'Z13-DE'])
        df_shots['is_rim'] = df_shots['zone'].str.contains('Z1-', na=False) & ~df_shots['zone'].str.contains('Z11|Z12|Z13', na=False)

        # Agrupamos por dorsal
        # (Nota: En el futuro podríamos enlazar Shots con PlayerID real si mejoramos el crawler)
        shot_profiles = df_shots.groupby('dorsal').agg(
            total_mapped=('id', 'count'),
            corner_3s=('is_corner', 'sum'),
            rim_shots=('is_rim', 'sum')
        ).reset_index()
        
        shot_profiles['corner_freq'] = (shot_profiles['corner_3s'] / shot_profiles['total_mapped']).fillna(0)
        shot_profiles['rim_freq'] = (shot_profiles['rim_shots'] / shot_profiles['total_mapped']).fillna(0)

    # 5. AGREGACIÓN (MEDIAS DE TEMPORADA)
    def get_mode(x): return x.mode().iloc[0] if not x.mode().empty else x.iloc[0]

    final_stats = df.groupby(['nombre', 'equipo']).agg({
        'dorsal': get_mode,
        'game_id': 'count',
        'MP': 'mean',
        'puntos': 'mean',
        'rebotes_total': 'mean',
        'rebotes_of': 'mean',
        'rebotes_def': 'mean',
        'recuperaciones': 'mean',
        'asistencias': 'mean',
        'perdidas': 'mean',
        't3_intentados': 'mean',
        '3P%': 'mean',
        'FGA': 'mean',
        'USG%': 'mean',
        'TS%': 'mean',
        'eFG%': 'mean',
        'GmSc': 'mean'
    }).reset_index()

    if not shot_profiles.empty:
        final_stats = pd.merge(final_stats, shot_profiles[['dorsal', 'corner_freq', 'rim_freq']], on='dorsal', how='left')
        final_stats[['corner_freq', 'rim_freq']] = final_stats[['corner_freq', 'rim_freq']].fillna(0)
    else:
        final_stats['corner_freq'] = 0
        final_stats['rim_freq'] = 0

    # 6. FILTRADO (Minutos y Partidos)
    pool_stats = final_stats[
        (final_stats['game_id'] >= min_games) & (final_stats['MP'] >= min_minutes)
    ].copy()

    if pool_stats.empty:
        return pd.DataFrame()

    # --- CÁLCULO DE PERCENTILES (Contexto de la Liga) ---
    pool_stats['P_USG'] = pool_stats['USG%'].rank(pct=True)
    pool_stats['P_AST'] = pool_stats['asistencias'].rank(pct=True)
    pool_stats['P_REB'] = pool_stats['rebotes_total'].rank(pct=True)
    pool_stats['P_3PA'] = pool_stats['t3_intentados'].rank(pct=True)
    pool_stats['P_EFF'] = pool_stats['eFG%'].rank(pct=True)
    
    pool_stats['Def_Score'] = pool_stats['rebotes_def'] + (pool_stats['recuperaciones'] * 1.5)
    pool_stats['P_DEF'] = pool_stats['Def_Score'].rank(pct=True)

    final_stats = pd.merge(final_stats, pool_stats[['nombre', 'equipo', 'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF']], on=['nombre', 'equipo'], how='left')
    
    # ==============================================================================
    # 7. ROL TÁCTICO (position-independent)
    # ==============================================================================

    def definir_rol(row):
        """
        Role classification based purely on statistical profile.
        Each role is mutually exclusive; first match wins.
        """
        if pd.isna(row.get('P_USG')):
            return "Rotación"

        p_usg = row['P_USG']
        p_eff = row['P_EFF']
        p_def = row['P_DEF']
        p_3pa = row['P_3PA']
        p_ast = row['P_AST']
        p_reb = row['P_REB']
        pct_3pt = row.get('3P%', 0)
        rim_freq = row.get('rim_freq', 0)

        # --- TIER 1: HIGH-IMPACT ---
        if p_usg > 0.80 and p_eff > 0.65:
            return "Anotador"
        if p_ast > 0.85 and p_usg > 0.60:
            return "Director de Juego"

        # --- TIER 2: SPECIALIST ---
        if p_3pa > 0.65 and pct_3pt > 32.0:
            return "Tirador"
        if p_ast > 0.70:
            return "Organizador"
        if rim_freq > 0.40 and p_reb > 0.60:
            return "Finalizador Interior"
        if rim_freq > 0.30 and p_usg > 0.50:
            return "Penetrador"
        if p_3pa > 0.55 and pct_3pt > 30.0 and p_def > 0.60:
            return "3&D Wing"

        # --- TIER 3: GENERAL ---
        if p_def > 0.75:
            return "Especialista Defensivo"
        if p_eff > 0.70:
            return "Finalizador"
        if p_usg > 0.75:
            return "Alto Volumen"
        if p_ast > 0.60:
            return "Creador"

        return "Rotación"

    final_stats['Rol Tactical'] = final_stats.apply(definir_rol, axis=1)

    # 8. LIMPIEZA FINAL
    final_stats.columns = [
        'Jugador', 'Equipo', 'Dorsal', 'PJ', 'MPP', 'PPP', 'RPP', 'ROf', 'RDef', 'Rec', 'APP', 
        'perdidas_mean', 't3_intentados_mean', '3P_pct_real', 'fga_mean', 
        'USG%', 'TS%', 'eFG%', 'GmSc', 'Corner_Freq', 'Rim_Freq',
        'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF', 'Rol Tactical'
    ]
    
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & (final_stats['MPP'] >= min_minutes)
    ].copy()

    # Redondeos para visualización
    cols_round_1 = ['USG%', 'GmSc', 'PPP', 'RPP', 'APP', 'MPP']
    for c in cols_round_1: 
        if c in final_stats.columns: final_stats[c] = final_stats[c].round(1)
        
    cols_round_100 = ['TS%', 'eFG%']
    for c in cols_round_100:
        if c in final_stats.columns: final_stats[c] = (final_stats[c] * 100).round(1)

    # Round percentiles to 2 decimals (0-1 range)
    cols_round_2 = ['P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF']
    for c in cols_round_2:
        if c in final_stats.columns: final_stats[c] = final_stats[c].round(2)
    
    # Renombrado para compatibilidad con Schema Pydantic
    return final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct",
        "Rol Tactical": "Rol_Tactical"
    })
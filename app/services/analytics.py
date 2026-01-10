import pandas as pd
import numpy as np
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
        df_shots['is_corner'] = df_shots['zone'].isin(['Z11-IZ', 'Z11-DE', 'Z13-IZ', 'Z13-DE'])
        df_shots['is_rim'] = df_shots['zone'].str.contains('Z1-', na=False) & ~df_shots['zone'].str.contains('Z11|Z12|Z13', na=False)

        # Agrupamos por dorsal
        shot_profiles = df_shots.groupby('dorsal').agg(
            total_mapped=('id', 'count'),
            corner_3s=('is_corner', 'sum'),
            rim_shots=('is_rim', 'sum')
        ).reset_index()
        
        shot_profiles['corner_freq'] = (shot_profiles['corner_3s'] / shot_profiles['total_mapped']).fillna(0)
        shot_profiles['rim_freq'] = (shot_profiles['rim_shots'] / shot_profiles['total_mapped']).fillna(0)

    # 5. AGREGACIÓN ÚNICA POR JUGADOR (MEDIAS DE TEMPORADA)
    # CORRECCIÓN: Quitamos 'dorsal' del groupby para unificar duplicados
    
    # Función auxiliar para obtener el dorsal más frecuente (moda)
    def get_mode(x):
        return x.mode().iloc[0] if not x.mode().empty else x.iloc[0]

    final_stats = df.groupby(['nombre', 'equipo']).agg({
        'dorsal': get_mode, # Usamos el dorsal más frecuente
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
        'FGA': 'mean',
        'USG%': 'mean',
        'TS%': 'mean',
        'eFG%': 'mean',
        'GmSc': 'mean'
    }).reset_index()

    # Unimos con los datos de tiro (usando el dorsal principal)
    # Nota: Si el jugador cambió de número, solo veremos el mapa de tiros de su número principal.
    if not shot_profiles.empty:
        final_stats = pd.merge(final_stats, shot_profiles[['dorsal', 'corner_freq', 'rim_freq']], on='dorsal', how='left')
        final_stats[['corner_freq', 'rim_freq']] = final_stats[['corner_freq', 'rim_freq']].fillna(0)
    else:
        final_stats['corner_freq'] = 0
        final_stats['rim_freq'] = 0

    # 6. FILTRADO PARA PERCENTILES
    pool_stats = final_stats[
        (final_stats['game_id'] >= min_games) & (final_stats['MP'] >= min_minutes)
    ].copy()

    if pool_stats.empty:
        return pd.DataFrame()

    # --- CÁLCULO DE PERCENTILES ---
    pool_stats['P_USG'] = pool_stats['USG%'].rank(pct=True)
    pool_stats['P_AST'] = pool_stats['asistencias'].rank(pct=True)
    pool_stats['P_REB'] = pool_stats['rebotes_total'].rank(pct=True)
    pool_stats['P_3PA'] = pool_stats['t3_intentados'].rank(pct=True)
    pool_stats['P_EFF'] = pool_stats['eFG%'].rank(pct=True)
    
    pool_stats['Def_Score'] = pool_stats['rebotes_def'] + (pool_stats['recuperaciones'] * 1.5)
    pool_stats['P_DEF'] = pool_stats['Def_Score'].rank(pct=True)

    # Devolvemos los percentiles al DataFrame principal
    final_stats = pd.merge(final_stats, pool_stats[['nombre', 'equipo', 'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF']], on=['nombre', 'equipo'], how='left')
    
    # 7. DEFINICIÓN DE ROLES DINÁMICA
    def definir_rol_dinamico(row):
        if pd.isna(row['P_USG']): return "Jugador de Rotación"
        
        rim_freq_val = row.get('rim_freq', 0)
        corner_freq_val = row.get('corner_freq', 0)

        # --- ARQUETIPOS DE ÉLITE ---
        if row['P_USG'] > 0.80 and row['P_EFF'] > 0.70: return "Estrella Ofensiva (Alpha)"
        if row['P_USG'] > 0.85: return "Amasador de Balón (High Volume)"
        if row['P_AST'] > 0.90: return "Generador Primario (Playmaker)"

        # --- INTERIORES ---
        if row['P_REB'] > 0.80:
            if row['P_3PA'] > 0.60: return "Interior Abierto (Stretch Big)"
            return "Protector de Aro (Rim Runner)"

        # --- PERÍMETRO / ESPECIALISTAS ---
        if row['P_3PA'] > 0.70 and row['P_DEF'] > 0.60 and row['P_USG'] < 0.60:
            if corner_freq_val > 0.20: return "Especialista de Esquina (3&D)"
            return "Tirador (Spot-up)"
        
        if row['P_3PA'] > 0.80 and row['P_EFF'] > 0.60: return "Francotirador (Sniper)"
        
        if rim_freq_val > 0.40 and row['P_USG'] > 0.60: return "Penetrador (Slasher)"

        if row['P_DEF'] > 0.70 and row['P_USG'] < 0.40: return "Pegamento (Glue Guy)"

        return "Jugador de Rotación"

    def estimar_posicion(row):
        if pd.isna(row.get('P_3PA')): return "Rotación"

        p_reb = row.get('P_REB', 0)      
        p_ast = row.get('P_AST', 0)      
        p_3pa = row.get('P_3PA', 0)      
        rim_freq = row.get('rim_freq', 0)

        # 1. BASE (PG) - EL FILTRO
        # Antes: Si p_ast > 0.90 entraba cualquiera.
        # Ahora: Incluso si eres el mejor pasador (0.90), si rebotas como un pívot (>0.80),
        # el sistema te bloquea aquí para que caigas en "Point Forward" más abajo.
        if (p_ast > 0.90 and p_reb < 0.80) or (p_ast > 0.75 and p_reb < 0.70):
            return "Base (PG)"

        # 2. INTERIORES Y POINT FORWARDS
        # Aquí caerán los "altos que asisten" que hemos rechazado arriba.
        if p_reb > 0.75 or (p_reb > 0.60 and rim_freq > 0.45):
            # Si asistes mucho, eres el Point Forward
            if p_ast > 0.65: return "Alero/Generador (Point Fwd)"
            
            if p_3pa > 0.55: return "Ala-Pívot (PF)"
            return "Pívot (C)"

        # 3. EXTERIORES (Wings/Guards)
        if p_ast > 0.60: return "Combo Guard (CG)" 
        if p_reb > 0.60: return "Alero (SF)"
        if p_3pa > 0.60: return "Escolta (SG)"
        
        return "Exterior (G/F)"

    final_stats['Rol Tactical'] = final_stats.apply(definir_rol_dinamico, axis=1)
    final_stats['Posicion'] = final_stats.apply(estimar_posicion, axis=1)

   # 8. LIMPIEZA FINAL
    final_stats.columns = [
        'Jugador', 'Equipo', 'Dorsal', 'PJ', 'MPP', 'PPP', 'RPP', 'ROf', 'RDef', 'Rec', 'APP', 
        'perdidas_mean', 't3_intentados_mean', 'fga_mean', 
        'USG%', 'TS%', 'eFG%', 'GmSc', 'Corner_Freq', 'Rim_Freq',
        'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF', 'Rol Tactical', 'Posicion'
    ]
    
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & (final_stats['MPP'] >= min_minutes)
    ].copy()

    # Redondeos
    final_stats['USG%'] = final_stats['USG%'].round(1)
    final_stats['TS%'] = (final_stats['TS%'] * 100).round(1)
    final_stats['eFG%'] = (final_stats['eFG%'] * 100).round(1)
    final_stats['GmSc'] = final_stats['GmSc'].round(1)
    final_stats['PPP'] = final_stats['PPP'].round(1)
    final_stats['RPP'] = final_stats['RPP'].round(1)
    final_stats['APP'] = final_stats['APP'].round(1)
    
    # RENOMBRADO FINAL CLAVE
    return final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct",
        "Rol Tactical": "Rol_Tactical"  # <--- ESTO ES VITAL
    })
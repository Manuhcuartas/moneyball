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

    # 2. PRE-PROCESAMIENTO
    df['equipo'] = df['equipo'].apply(normalize_team_name)

    def parse_minutos(val):
        try:
            if not isinstance(val, str) or ":" not in val: return 0.0
            m, s = map(int, val.split(":"))
            return m + s/60
        except: return 0.0

    df['MP'] = df['minutos'].apply(parse_minutos)
    
    # Cálculos básicos de tiro
    df['FGA'] = df['t2_intentados'] + df['t3_intentados']
    df['FG'] = df['t2_anotados'] + df['t3_anotados']
    df['FTA'] = df['t1_intentados']
    
    # Cálculo de porcentajes reales
    df['3P%'] = (df['t3_anotados'] / df['t3_intentados'].replace(0, 1)) * 100
    df['2P%'] = (df['t2_anotados'] / df['t2_intentados'].replace(0, 1)) * 100

    # Totales de equipo
    team_stats = df.groupby(['game_id', 'equipo'])[['MP', 'FGA', 'FTA', 'perdidas']].sum().reset_index()
    team_stats.columns = ['game_id', 'equipo', 'Team_MP', 'Team_FGA', 'Team_FTA', 'Team_TOV']
    df = pd.merge(df, team_stats, on=['game_id', 'equipo'])

    # 3. MÉTRICAS AVANZADAS
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

    # 4. MAPA DE CALOR
    shot_profiles = pd.DataFrame()
    if not df_shots.empty:
        df_shots['is_corner'] = df_shots['zone'].isin(['Z11-IZ', 'Z11-DE', 'Z13-IZ', 'Z13-DE'])
        df_shots['is_rim'] = df_shots['zone'].str.contains('Z1-', na=False) & ~df_shots['zone'].str.contains('Z11|Z12|Z13', na=False)

        shot_profiles = df_shots.groupby('dorsal').agg(
            total_mapped=('id', 'count'),
            corner_3s=('is_corner', 'sum'),
            rim_shots=('is_rim', 'sum')
        ).reset_index()
        
        shot_profiles['corner_freq'] = (shot_profiles['corner_3s'] / shot_profiles['total_mapped']).fillna(0)
        shot_profiles['rim_freq'] = (shot_profiles['rim_shots'] / shot_profiles['total_mapped']).fillna(0)

    # 5. AGREGACIÓN (MEDIAS)
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

    # 6. FILTRADO
    pool_stats = final_stats[
        (final_stats['game_id'] >= min_games) & (final_stats['MP'] >= min_minutes)
    ].copy()

    if pool_stats.empty: return pd.DataFrame()

    # --- PERCENTILES ---
    pool_stats['P_USG'] = pool_stats['USG%'].rank(pct=True)
    pool_stats['P_AST'] = pool_stats['asistencias'].rank(pct=True)
    pool_stats['P_REB'] = pool_stats['rebotes_total'].rank(pct=True)
    pool_stats['P_3PA'] = pool_stats['t3_intentados'].rank(pct=True)
    pool_stats['P_EFF'] = pool_stats['eFG%'].rank(pct=True)
    
    pool_stats['Def_Score'] = pool_stats['rebotes_def'] + (pool_stats['recuperaciones'] * 1.5)
    pool_stats['P_DEF'] = pool_stats['Def_Score'].rank(pct=True)

    final_stats = pd.merge(final_stats, pool_stats[['nombre', 'equipo', 'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF']], on=['nombre', 'equipo'], how='left')
    
    # ==============================================================================
    # 7. LÓGICA V3.0 (AJUSTE DE PÍVOTS)
    # ==============================================================================

    def estimar_posicion(row):
        if pd.isna(row.get('P_3PA')): return "Rotación"

        p_ast = row.get('P_AST', 0)      
        p_reb = row.get('P_REB', 0)      
        p_3pa = row.get('P_3PA', 0)      
        rim_freq = row.get('rim_freq', 0)

        # 1. BASE (PG) - Filtro estricto
        cond_base_puro = (p_ast > 0.80 and p_reb < 0.70)
        cond_base_bajito = (p_ast > 0.65 and p_reb < 0.50)
        
        if (cond_base_puro or cond_base_bajito) and rim_freq < 0.60:
            return "Base (PG)"

        # 2. INTERIORES Y POINT FORWARDS (La red para los altos)
        # Subimos el listón: Hay que rebotar MUCHO (Top 28%) o vivir en la zona
        if p_reb > 0.72 or (p_reb > 0.60 and rim_freq > 0.45):
            
            # Point Forward / Center (Jokic/Draymond)
            if p_ast > 0.65: return "Alero/Generador (Point Fwd)"
            
            # Stretch Big (Pívot tirador)
            if p_3pa > 0.55: return "Ala-Pívot (PF)"
            
            # --- FILTRO ANTI-FALSOS PÍVOTS ---
            # Si has caído aquí es que rebotas, pero no tiras triples ni asistes.
            # ¿Eres realmente un pívot? Solo si juegas cerca del aro o rebotas una barbaridad.
            if rim_freq > 0.35 or p_reb > 0.85:
                return "Pívot (C)"
            
            # Si rebotas bien pero juegas por fuera (rim_freq bajo) y no tiras triples...
            # Eres un Alero físico o un 4 móvil.
            return "Ala-Pívot (PF)" 

        # 3. EXTERIORES (Wings/Guards) - El resto
        if p_ast > 0.55: return "Combo Guard (CG)" 
        if p_reb > 0.55: return "Alero (SF)" 
        if p_3pa > 0.55: return "Escolta (SG)"
        
        return "Exterior (G/F)"

    def definir_rol_dinamico(row):
        if pd.isna(row['P_USG']): return "Fondo de Armario"
        
        p_usg = row['P_USG']
        p_eff = row['P_EFF']
        p_def = row['P_DEF']
        p_3pa = row['P_3PA']
        p_ast = row['P_AST']
        pct_3pt_real = row.get('3P%', 0)
        rim_freq = row.get('rim_freq', 0)
        corner_freq = row.get('corner_freq', 0)

        # --- NIVEL 1: ELITE & MOTORES ---
        if p_usg > 0.85 and p_ast > 0.75: return "Motor Ofensivo (Offensive Engine)"
        if p_ast > 0.90: return "Director de Juego (Floor General)"
        if p_usg > 0.80 and p_eff > 0.70: return "Anotador Élite (Bucket Getter)"

        # --- NIVEL 2: INTERIORES ---
        if row['Posicion'] in ["Pívot (C)", "Ala-Pívot (PF)", "Point Center", "Alero/Generador (Point Forward)"]:
            if p_3pa > 0.65 and pct_3pt_real > 32.0: return "Interior Abierto (Stretch Big)"
            if p_ast > 0.75: return "Distribuidor desde Poste"
            if p_def > 0.80: return "Ancla Defensiva (Rim Protector)"
            if rim_freq > 0.50: return "Finalizador (Rim Runner)"

        # --- NIVEL 3: PERÍMETRO / ESPECIALISTAS ---
        if p_3pa > 0.75 and pct_3pt_real > 34.0:
            if p_eff > 0.70: return "Francotirador (Sniper)"
            return "Tirador de Volumen (Volume Shooter)"

        if p_3pa > 0.60 and pct_3pt_real > 30.0 and p_def > 0.70:
            if corner_freq > 0.20: return "Especialista de Esquina (3&D)"
            return "3&D Wing"
        
        if rim_freq > 0.40 and p_usg > 0.50: return "Penetrador (Slasher)"

        # --- NIVEL 4: ROLES DE SOPORTE ---
        if p_ast > 0.70: return "Conector (Connector)"
        if p_def > 0.70: return "Especialista Defensivo"
        if p_eff > 0.70: return "Oportunista Eficiente"
        if p_usg > 0.80: return "Microondas (High Volume)"

        return "Rol de Rotación"

    final_stats['Posicion'] = final_stats.apply(estimar_posicion, axis=1)
    final_stats['Rol Tactical'] = final_stats.apply(definir_rol_dinamico, axis=1)

    # 8. LIMPIEZA FINAL
    final_stats.columns = [
        'Jugador', 'Equipo', 'Dorsal', 'PJ', 'MPP', 'PPP', 'RPP', 'ROf', 'RDef', 'Rec', 'APP', 
        'perdidas_mean', 't3_intentados_mean', '3P_pct_real', 'fga_mean', 
        'USG%', 'TS%', 'eFG%', 'GmSc', 'Corner_Freq', 'Rim_Freq',
        'P_USG', 'P_AST', 'P_REB', 'P_3PA', 'P_EFF', 'P_DEF', 'Posicion', 'Rol Tactical'
    ]
    
    final_stats = final_stats[
        (final_stats['PJ'] >= min_games) & (final_stats['MPP'] >= min_minutes)
    ].copy()

    # Redondeos
    cols_round_1 = ['USG%', 'GmSc', 'PPP', 'RPP', 'APP']
    for c in cols_round_1: 
        if c in final_stats.columns: final_stats[c] = final_stats[c].round(1)
        
    cols_round_100 = ['TS%', 'eFG%']
    for c in cols_round_100:
        if c in final_stats.columns: final_stats[c] = (final_stats[c] * 100).round(1)
    
    return final_stats.rename(columns={
        "USG%": "USG_pct",
        "TS%": "TS_pct",
        "eFG%": "eFG_pct",
        "Rol Tactical": "Rol_Tactical"
    })
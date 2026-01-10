import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- IMPORTACIÓN DIRECTA (EL TRUCO PARA LA NUBE) ---
# Al importar esto, accedemos a la lógica sin necesitar el servidor API encendido
from app.core.database import SessionLocal
from app.services.analytics import get_advanced_stats

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Moneyball FBPA", layout="wide", page_icon="🏀")

# --- FUNCIONES DE CARGA ---
@st.cache_data(ttl=600)
def load_data(min_games, min_minutes, team_filter=None):
    db = SessionLocal()
    try:
        # Llamamos a la función Python directamente, no a la URL
        df = get_advanced_stats(db, min_games=min_games, min_minutes=min_minutes)
        return df
    except Exception as e:
        st.error(f"Error calculando datos: {e}")
        return pd.DataFrame()
    finally:
        db.close()

def draw_radar_chart(df, player_name):
    # Buscamos al jugador
    player_stats = df[df['Jugador'] == player_name].iloc[0]
    
    # Definimos las métricas (Percentiles) y sus etiquetas bonitas
    categories = ['Uso Ofensivo', 'Eficiencia Tiro', 'Creación/Pase', 'Rebote', 'Impacto Defensivo']
    
    # Valores (multiplicamos por 100 para que sea 0-100)
    values = [
        player_stats.get('P_USG', 0) * 100,
        player_stats.get('P_EFF', 0) * 100,
        player_stats.get('P_AST', 0) * 100,
        player_stats.get('P_REB', 0) * 100,
        player_stats.get('P_DEF', 0) * 100
    ]
    
    # Cerramos el polígono repitiendo el primer valor
    values += values[:1]
    categories += categories[:1]

    fig = go.Figure()

    # Dibujamos el área del jugador
    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=player_name,
        line_color='#00CC96',
        opacity=0.7
    ))

    # Configuración estética
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                showticklabels=False, 
                linecolor='grey'
            ),
            angularaxis=dict(
                color='white',
                tickfont=dict(size=12) # <--- CORRECCIÓN AQUÍ (Estaba fuera)
            ),
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=False,
        title=dict(text=f"Perfil Moneyball: {player_stats['Rol Tactical']}", x=0.5),
        height=400,
        margin=dict(t=40, b=20, l=40, r=40),
        template="plotly_dark"
    )
    
    return fig

def draw_shot_chart(df_shots, title="Mapa de Tiros"):
    fig = go.Figure()

    if not df_shots.empty:
        df_shots = df_shots.copy()
        
        # Mantenemos tu transformación que ya funciona
        df_shots['x_final'] = df_shots['y'] 
        df_shots['y_final'] = df_shots['x'].apply(lambda x: x if x <= 50 else 100 - x)
        df_shots['y_final'] = df_shots['y_final'] * 2

        for is_made_val, color, symbol, name in [(True, "#00FF00", "circle", "Anotado"), 
                                                 (False, "#FF0000", "x", "Fallado")]:
            subset = df_shots[df_shots['is_made'] == is_made_val]
            fig.add_trace(go.Scatter(
                x=subset['x_final'], 
                y=subset['y_final'],
                mode='markers',
                marker=dict(color=color, symbol=symbol, size=10, opacity=0.8,
                            line=dict(width=1, color='black')),
                name=name,
                hoverinfo='text',
                text=subset['action_type']
            ))

    # --- DIBUJO DE CANCHA ESTRECHADA Y ARCO CALIBRADO ---
    fig.update_layout(
        title=title,
        # Estrechamos el rango visual de X para que los puntos no se vean tan "lejos" de las bandas
        xaxis=dict(range=[10, 90], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[0, 100], showgrid=False, zeroline=False, showticklabels=False),
        width=450, # Pista más estrecha
        height=600,
        template="plotly_dark",
        shapes=[
            # Rectángulo exterior (Pista estrechada)
            dict(type="rect", x0=10, y0=0, x1=90, y1=100, line_color="white", line_width=2),
            
            # ZONA (Más estilizada)
            dict(type="rect", x0=35, y0=0, x1=65, y1=35, line_color="white", line_width=2),
            
            # LÍNEA DE TRES (Arco que sigue la tendencia de tus puntos)
            # La curva empieza en las líneas laterales (Y=0) y sube hacia el centro
            dict(type="path", 
                 path="M 10,0 L 10,25 Q 50,85 90,25 L 90,0", 
                 line_color="white", line_width=2),
            
            # Línea de aro/tablero
            dict(type="line", x0=42, y0=8, x1=58, y1=8, line_color="white", line_width=3)
        ]
    )
    return fig

def load_shots(nombre_jugador):
    from app.models.shot import Shot
    from app.models.stats import PlayerStat
    db = SessionLocal()
    try:
        # 1. Buscamos TODOS los registros de este jugador en la temporada
        # Esto nos da la lista de IDs de todos los partidos que ha jugado
        player_games = db.query(PlayerStat).filter(PlayerStat.nombre == nombre_jugador).all()
        
        if not player_games:
            return pd.DataFrame()
        
        # Obtenemos la lista de game_ids y su dorsal (asumimos dorsal único por temporada)
        game_ids = [pg.game_id for pg in player_games]
        dorsal_jugador = player_games[0].dorsal
        
        # 2. Buscamos en la tabla de tiros filtrando por:
        # - Su dorsal
        # - Que el partido esté en su lista de partidos jugados
        query = db.query(Shot).filter(
            Shot.dorsal == dorsal_jugador,
            Shot.game_id.in_(game_ids)
        )
        
        df_shots = pd.read_sql(query.statement, db.bind)

        if not df_shots.empty:
            df_shots['x'] = df_shots['x'].astype(float)
            df_shots['y'] = df_shots['y'].astype(float)
            df_shots['is_made'] = df_shots['is_made'].astype(bool)
            
        return df_shots
    except Exception as e:
        st.error(f"Error cargando histórico de tiros: {e}")
        return pd.DataFrame()
    finally:
        db.close()

# --- SIDEBAR (FILTROS) ---
st.sidebar.title("🛠️ Filtros de Scouting")
min_games = st.sidebar.slider("Mínimo Partidos Jugados", 1, 10, 3)
min_minutes = st.sidebar.slider("Mínimo Minutos/Partido", 5, 30, 15)

# Cargar datos
df = load_data(min_games, min_minutes)

if df.empty:
    st.warning("No hay datos disponibles en la base de datos.")
    st.stop()

# --- TABLA ---
st.title("🏀 Moneyball FBPA: Análisis Avanzado")
st.markdown(f"**{len(df)}** jugadores analizados | Temporada 25/26")
st.divider()

# MODIFICA ESTA LÍNEA PARA AÑADIR "Posicion" y "Rol Tactical"
cols_show = ["Jugador", "Equipo", "Posicion", "Rol Tactical", "GmSc", "TS_pct", "eFG_pct", "USG_pct", "PPP", "RPP", "APP", "MPP", "PJ"]

st.dataframe(
    df[cols_show].style.background_gradient(subset=["GmSc", "TS_pct"], cmap="Greens"),
    use_container_width=True
)

# Filtro de Equipo
equipos_disponibles = ["Todos"] + sorted(df['Equipo'].unique().tolist())
equipo_seleccionado = st.sidebar.selectbox("Filtrar por Equipo", equipos_disponibles)

if equipo_seleccionado != "Todos":
    df = df[df['Equipo'] == equipo_seleccionado]

posiciones_disponibles = ["Todas"] + sorted(df['Posicion'].unique().tolist())
posicion_seleccionada = st.sidebar.selectbox("Filtrar por Posición", posiciones_disponibles)

if posicion_seleccionada != "Todas":
    df = df[df['Posicion'] == posicion_seleccionada]

# --- PÁGINA PRINCIPAL ---


# KPIs Rápidos
col1, col2, col3, col4 = st.columns(4)
with col1:
    top_scorer = df.loc[df['PPP'].idxmax()]
    st.metric("Máximo Anotador", f"{top_scorer['Jugador']}", f"{top_scorer['PPP']} PPP")
with col2:
    # Filtramos uso > 20 para evitar rarezas
    qualified = df[df['USG_pct'] > 20]
    if not qualified.empty:
        top_efficient = qualified.sort_values('TS_pct', ascending=False).iloc[0]
        st.metric("Más Eficiente (>20% Uso)", f"{top_efficient['Jugador']}", f"{top_efficient['TS_pct']}% TS")
with col3:
    top_impact = df.loc[df['GmSc'].idxmax()]
    st.metric("MVP (Game Score)", f"{top_impact['Jugador']}", f"{top_impact['GmSc']}")
with col4:
    top_rebounder = df.loc[df['RPP'].idxmax()]
    st.metric("Rey del Rebote", f"{top_rebounder['Jugador']}", f"{top_rebounder['RPP']} Reb/P")

st.divider()

# --- GRÁFICO ---
st.subheader("🎯 Eficiencia vs Volumen")
# Columna visual para evitar error de radio negativo
df['GmSc_Visual'] = df['GmSc'].apply(lambda x: max(float(x), 1.0))

fig_scatter = px.scatter(
    df,
    x="USG_pct",
    y="TS_pct",
    color="Equipo",
    size="GmSc_Visual",
    hover_name="Jugador",
    hover_data={
        "GmSc": True,
        "GmSc_Visual": False,
        "PPP": True, 
        "MPP": True, 
        "PJ": True
    },
    title="Mapa de Talento de la Liga",
    template="plotly_dark",
    height=600
)
fig_scatter.add_hline(y=50, line_dash="dash", annotation_text="Eficiencia Media")
fig_scatter.add_vline(x=20, line_dash="dash", annotation_text="Uso Medio")

st.plotly_chart(fig_scatter, width="stretch")

st.divider()
st.subheader("🔥 Análisis Geográfico (Shot Chart)")

# 1. Selección de Jugador
lista_jugadores = sorted(df['Jugador'].unique())
jugador_mapa = st.selectbox("Selecciona un jugador para ver su mapa de tiros", lista_jugadores, key="sel_jugador_mapa")

# --- SECCIÓN: SCOUTING INDIVIDUAL ---
st.divider()
st.subheader("🕵️ Ficha de Scouting")

# Selector de jugador unificado para toda la sección
lista_jugadores = sorted(df['Jugador'].unique())
jugador_sel = st.selectbox("Selecciona un jugador para analizar:", lista_jugadores, key="scout_player")

if jugador_sel:
    # FILA SUPERIOR: DATOS Y RADAR
    col_izq, col_der = st.columns([1, 1])
    
    with col_izq:
        # Gráfico de Radar
        fig_radar = draw_radar_chart(df, jugador_sel)
        st.plotly_chart(fig_radar, width="stretch")
        # Datos clave debajo del radar
        info = df[df['Jugador'] == jugador_sel].iloc[0]
        st.info(f"""
        **Posición Estimada:** {info['Posicion']}  
        **Rol Táctico:** {info['Rol Tactical']}  
        **Game Score:** {info['GmSc']}
        """)

    with col_der:
        # Mapa de Tiros
        df_shots_jugador = load_shots(jugador_sel)
        if not df_shots_jugador.empty:
            st.caption("Mapa de Tiros (Temporada)")
            # Reusamos tu función de mapa
            fig_mapa = draw_shot_chart(df_shots_jugador, title="") 
            st.plotly_chart(fig_mapa, width='stretch', key=f"map_{jugador_sel}")
            
            # Pequeño resumen de efectividad
            r_zona = df_shots_jugador.groupby('zone')['is_made'].mean() * 100
            if not r_zona.empty:
                 mej_zona = r_zona.idxmax()
                 st.caption(f"🔥 Zona favorita: **{mej_zona}** ({r_zona.max():.1f}%)")
        else:
            st.warning("⚠️ No hay datos de tiro registrados (Shot Chart) para este jugador.")

    # FILA INFERIOR: TABLA DE TIROS (Opcional, en acordeón para no molestar)
    if not df_shots_jugador.empty:
        with st.expander("Ver registro detallado de lanzamientos"):
            st.dataframe(df_shots_jugador[['game_id', 'period', 'zone', 'action_type', 'is_made']], use_container_width=True)
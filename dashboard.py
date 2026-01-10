import streamlit as st
import pandas as pd
import plotly.express as px

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

# --- SIDEBAR (FILTROS) ---
st.sidebar.title("🛠️ Filtros de Scouting")
min_games = st.sidebar.slider("Mínimo Partidos Jugados", 1, 10, 3)
min_minutes = st.sidebar.slider("Mínimo Minutos/Partido", 5, 30, 15)

# Cargar datos
df = load_data(min_games, min_minutes)

if df.empty:
    st.warning("No hay datos disponibles en la base de datos.")
    st.stop()

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
st.title("🏀 Moneyball FBPA: Análisis Avanzado")
st.markdown(f"**{len(df)}** jugadores analizados | Temporada 25/26")

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

st.plotly_chart(fig_scatter, use_container_width=True)

# --- TABLA ---
st.divider()
cols_show = ["Jugador", "Equipo", "GmSc", "TS_pct", "eFG_pct", "USG_pct", "PPP", "RPP", "APP", "MPP", "PJ"]
st.dataframe(
    df[cols_show].style.background_gradient(subset=["GmSc", "TS_pct"], cmap="Greens"),
    use_container_width=True
)
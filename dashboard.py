import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import os

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Moneyball FBPA", layout="wide", page_icon="🏀")

# URL del Backend
API_URL = os.getenv("API_INTERNAL_URL", "http://127.0.0.1:8000/api/v1")

# --- FUNCIONES DE CARGA ---
@st.cache_data(ttl=300)
def load_season_stats(min_games, min_minutes, team_filter=None):
    try:
        params = {
            "min_games": min_games,
            "min_minutes": min_minutes,
            "sort_by": "GmSc"
        }
        if team_filter and team_filter != "Todos":
            params["team"] = team_filter

        response = requests.get(f"{API_URL}/season/advanced", params=params)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data["data"])
        return df
    except Exception as e:
        st.error(f"❌ Error conectando con la API: {e}")
        return pd.DataFrame()

def load_player_profile_api(player_name):
    try:
        response = requests.get(f"{API_URL}/player/profile", params={"name": player_name})
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None

# --- FUNCIONES DE DIBUJO ---
def draw_radar_chart(profile_data):
    player_name = profile_data['Jugador']
    
    # Percentiles
    categories = ['Uso Ofensivo', 'Eficiencia Tiro', 'Creación/Pase', 'Rebote', 'Impacto Defensivo']
    values = [
        profile_data.get('P_USG', 0) * 100,
        profile_data.get('P_EFF', 0) * 100,
        profile_data.get('P_AST', 0) * 100,
        profile_data.get('P_REB', 0) * 100,
        profile_data.get('P_DEF', 0) * 100
    ]
    values += values[:1]
    categories += categories[:1]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values, theta=categories, fill='toself', name=player_name,
        line_color='#00CC96', opacity=0.7
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=False, linecolor='grey'),
            angularaxis=dict(color='white', tickfont=dict(size=12)),
            bgcolor="rgba(0,0,0,0)"
        ),
        showlegend=False,
        # OJO: Aquí usamos Rol_Tactical
        title=dict(text=f"Perfil: {profile_data.get('Rol_Tactical', 'N/A')}", x=0.5),
        height=400,
        margin=dict(t=40, b=20, l=40, r=40),
        template="plotly_dark"
    )
    return fig

def draw_shot_chart(shots_list, title="Mapa de Tiros"):
    fig = go.Figure()
    if not shots_list: pass 
    else:
        df_shots = pd.DataFrame(shots_list)
        df_shots['x_final'] = df_shots['y'] 
        df_shots['y_final'] = df_shots['x'].apply(lambda x: x if x <= 50 else 100 - x)
        df_shots['y_final'] = df_shots['y_final'] * 2

        for is_made_val, color, symbol, name in [(True, "#00FF00", "circle", "Anotado"), 
                                                 (False, "#FF0000", "x", "Fallado")]:
            subset = df_shots[df_shots['is_made'] == is_made_val]
            if not subset.empty:
                fig.add_trace(go.Scatter(
                    x=subset['x_final'], y=subset['y_final'], mode='markers',
                    marker=dict(color=color, symbol=symbol, size=10, opacity=0.8, line=dict(width=1, color='black')),
                    name=name, hoverinfo='text', text=subset['action_type']
                ))

    fig.update_layout(
        title=title,
        xaxis=dict(range=[10, 90], showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(range=[0, 100], showgrid=False, zeroline=False, showticklabels=False),
        width=450, height=600, template="plotly_dark",
        shapes=[
            dict(type="rect", x0=10, y0=0, x1=90, y1=100, line_color="white", line_width=2),
            dict(type="rect", x0=35, y0=0, x1=65, y1=35, line_color="white", line_width=2),
            dict(type="path", path="M 10,0 L 10,25 Q 50,85 90,25 L 90,0", line_color="white", line_width=2),
            dict(type="line", x0=42, y0=8, x1=58, y1=8, line_color="white", line_width=3)
        ]
    )
    return fig

# --- INTERFAZ ---
st.sidebar.title("🛠️ Filtros API")
min_games = st.sidebar.slider("Min Partidos", 1, 10, 3)
min_minutes = st.sidebar.slider("Min Minutos", 5, 30, 15)

# Cargar datos
df = load_season_stats(min_games, min_minutes)

if df.empty:
    st.warning("⚠️ No se pudieron cargar datos. Verifica que el Backend esté corriendo.")
    st.stop()

# Filtros
equipos = ["Todos"] + sorted(df['Equipo'].unique().tolist())
equipo_sel = st.sidebar.selectbox("Equipo", equipos)
if equipo_sel != "Todos": df = df[df['Equipo'] == equipo_sel]

# Ahora Posicion ya existe en el DataFrame gracias al Schema nuevo
posiciones = ["Todas"] + sorted(df['Posicion'].unique().tolist())
pos_sel = st.sidebar.selectbox("Posición", posiciones)
if pos_sel != "Todas": df = df[df['Posicion'] == pos_sel]

st.title("🏀 Moneyball FBPA (Full Stack)")
st.markdown(f"**{len(df)}** jugadores cargados vía API REST")

# KPIs
c1, c2, c3, c4 = st.columns(4)
c1.metric("Máximo Anotador", df.loc[df['PPP'].idxmax()]['Jugador'], f"{df['PPP'].max()} PPP")
c2.metric("Máximo Reboteador", df.loc[df['RPP'].idxmax()]['Jugador'], f"{df['RPP'].max()} RPP")
c3.metric("Mejor Pasador", df.loc[df['APP'].idxmax()]['Jugador'], f"{df['APP'].max()} APP")
c4.metric("MVP (GmSc)", df.loc[df['GmSc'].idxmax()]['Jugador'], f"{df['GmSc'].max()}")

st.divider()
# TABLA PRINCIPAL (Usamos Rol_Tactical)
cols_show = ["Jugador", "Equipo", "Posicion", "Rol_Tactical", "GmSc", "TS_pct", "eFG_pct", "USG_pct", "PPP", "RPP", "APP", "MPP", "PJ"]
st.dataframe(df[cols_show].style.background_gradient(subset=["GmSc"], cmap="Greens"), use_container_width=True)

# GRÁFICO
st.subheader("📊 Mapa de Talento")
df['GmSc_Visual'] = df['GmSc'].apply(lambda x: max(float(x), 1.0))
fig_scatter = px.scatter(
    df, x="USG_pct", y="TS_pct", color="Equipo", size="GmSc_Visual",
    hover_name="Jugador", title="Eficiencia vs Uso", template="plotly_dark", height=500
)
fig_scatter.add_hline(y=50, line_dash="dash"); fig_scatter.add_vline(x=20, line_dash="dash")
st.plotly_chart(fig_scatter, width="stretch")

# FICHA TÉCNICA
st.divider()
st.subheader("🕵️ Ficha Técnica")
jugadores = sorted(df['Jugador'].unique())
jugador_sel = st.selectbox("Selecciona jugador:", jugadores)

if jugador_sel:
    profile_response = load_player_profile_api(jugador_sel)
    if profile_response:
        stats = profile_response['profile']
        shots = profile_response['shots']
        
        c_izq, c_der = st.columns([1, 1])
        with c_izq:
            st.plotly_chart(draw_radar_chart(stats), width="stretch")
            st.info(f"**Rol:** {stats['Rol_Tactical']} | **Posición:** {stats['Posicion']} | **Partidos jugados:** {stats['PJ']}")
        with c_der:
            if shots:
                st.caption(f"Mapa de Tiros ({len(shots)} tiros)")
                st.plotly_chart(draw_shot_chart(shots, title=""), width="stretch")
            else:
                st.warning("Sin datos de tiro.")
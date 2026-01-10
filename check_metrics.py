from app.core.database import SessionLocal
from app.services.analytics import get_advanced_stats
import pandas as pd

# Configuración de visualización de pandas
pd.set_option('display.max_rows', 50)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 1000)

def main():
    db = SessionLocal()
    print("🧠 Calculando métricas Moneyball...")
    
    # Pedimos jugadores con al menos 3 partidos y 15 minutos de media
    df = get_advanced_stats(db, min_games=3, min_minutes=15)
    
    print("\n--- TOP 10 EFICIENCIA OFENSIVA (TS%) ---")
    print("(Jugadores que anotan mucho con pocos tiros)")
    # Filtramos gente que tire un mínimo (Usage > 15%) para quitar pívots que solo meten debajo del aro
    shooters = df[df['USG%'] > 15].sort_values('TS%', ascending=False).head(10)
    print(shooters[['Jugador', 'Equipo', 'PPP', 'USG%', 'TS%', 'eFG%']].to_string(index=False))

    print("\n--- TOP 10 'AMASADORES' DE BALÓN (USG%) ---")
    print("(Jugadores que se juegan todas las posesiones de su equipo)")
    ball_hogs = df.sort_values('USG%', ascending=False).head(10)
    print(ball_hogs[['Jugador', 'Equipo', 'PPP', 'USG%', 'TS%']].to_string(index=False))

    print("\n--- TOP 10 MVP REAL (Game Score) ---")
    print("(La métrica global más completa)")
    mvps = df.sort_values('GmSc', ascending=False).head(10)
    print(mvps[['Jugador', 'Equipo', 'PJ', 'PPP', 'RPP', 'APP', 'GmSc']].to_string(index=False))

    db.close()

if __name__ == "__main__":
    main()
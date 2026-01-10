from app.core.database import SessionLocal
from app.models.stats import PlayerStat, Game
from sqlalchemy import func, desc

def analizar_datos():
    db = SessionLocal()
    
    # 1. Conteo rápido
    total_partidos = db.query(Game).count()
    total_registros = db.query(PlayerStat).count()
    print(f"📊 ESTADO DE LA BASE DE DATOS:")
    print(f"   - Partidos registrados: {total_partidos}")
    print(f"   - Estadísticas individuales: {total_registros}")
    print("-" * 50)

    # 2. Top 10 Jugadores por Valoración Media (Minimo 3 partidos jugados)
    # SQL: SELECT nombre, equipo, AVG(valoracion) as val_media, COUNT(*) as partidos 
    #      FROM player_stats GROUP BY nombre, equipo HAVING partidos >= 3 ORDER BY val_media DESC
    
    results = (
        db.query(
            PlayerStat.nombre,
            PlayerStat.equipo,
            func.avg(PlayerStat.valoracion).label("media_val"),
            func.avg(PlayerStat.puntos).label("media_pts"),
            func.count(PlayerStat.id).label("partidos")
        )
        .group_by(PlayerStat.nombre, PlayerStat.equipo)
        .having(func.count(PlayerStat.id) >= 3) # Filtro para quitar jugadores que jugaron 1 partido bueno
        .order_by(desc("media_val"))
        .limit(15)
        .all()
    )

    print(f"{'JUGADOR':<35} | {'EQUIPO':<30} | {'VAL':<5} | {'PTS':<5} | {'PJ':<3}")
    print("-" * 90)
    
    for row in results:
        nombre = row.nombre[:35]
        equipo = row.equipo[:30]
        val = round(row.media_val, 1)
        pts = round(row.media_pts, 1)
        pj = row.partidos
        print(f"{nombre:<35} | {equipo:<30} | {val:<5} | {pts:<5} | {pj:<3}")

    db.close()

if __name__ == "__main__":
    analizar_datos()
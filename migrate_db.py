from app.core.database import engine, Base
from app.models.stats import PlayerSeasonStat, LeagueAverage

def migrate():
    print("🔄 Migrando esquema (eliminando player_season_stats)")
    PlayerSeasonStat.__table__.drop(engine, checkfirst=True)
    LeagueAverage.__table__.drop(engine, checkfirst=True)
    print("✨ Creando nuevas tablas...")
    Base.metadata.create_all(bind=engine)
    print("✅ Migración completada.")

if __name__ == "__main__":
    migrate()

from app.core.database import engine, Base

# Importar TODOS los modelos
from app.models.shot import Shot 
from app.models.stats import Game, PlayerStat, Team, Player # <--- Añadir Team y Player

def init_db():
    print("🔄 Reiniciando Base de Datos...")
    Base.metadata.drop_all(bind=engine)
    print("✨ Creando esquema nuevo (Teams, Players, Games, Stats)...")
    Base.metadata.create_all(bind=engine)
    print("✅ BD lista.")

if __name__ == "__main__":
    init_db()
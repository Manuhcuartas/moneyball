from app.core.database import engine, Base

# --- IMPORTANTE: Importar TODOS los modelos que quieras crear ---

# 1. Modelos antiguos (Si quieres mantener la tabla de Tiros/Shot Chart)
from app.models.shot import Shot 

# 2. NUEVOS MODELOS (Estadísticas completas)
# Nota: Importamos 'Game' desde stats, porque ese es el que tiene la relación con PlayerStat.
# Si tenías un 'app.models.game' antiguo, coméntalo para no tener dos clases 'Game' chocando.
from app.models.stats import Game, PlayerStat 

def init_db():
    print("🔄 Conectando a la base de datos...")
    
    # 1. Borrar todo lo viejo (¡Reset total!)
    # CUIDADO: Esto borra TODOS los datos que tengas ahora mismo.
    print("🗑️  Borrando tablas antiguas...")
    Base.metadata.drop_all(bind=engine)

    # 2. Crear las tablas nuevas
    # SQLAlchemy revisa todos los modelos importados arriba y crea las tablas
    print("✨ Creando tablas nuevas (Games, Shots, PlayerStats)...")
    Base.metadata.create_all(bind=engine)

    print("✅ ¡Base de datos lista y limpia!")

if __name__ == "__main__":
    init_db()
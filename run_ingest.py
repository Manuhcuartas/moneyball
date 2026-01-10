from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService

# ID de prueba
TEST_GAME_ID = "36007A00450072004500790065007400360031003900450048006E00780052005A00720047006600370067003D003D00"

def main():
    db = SessionLocal()
    try:
        scraper = ScraperService(db)
        
        # Preparamos metadatos mínimos que espera ingest_game_statistics
        game_metadata = {
            "id": TEST_GAME_ID,
            "jornada": "99",
            "fecha": "2026-01-10"
        }

        print(f"🚀 Iniciando ingesta manual del partido: {TEST_GAME_ID}")
        
        # 1. Ingesta de Estadísticas (Acta oficial)
        success_stats = scraper.ingest_game_statistics(game_metadata)
        
        if success_stats:
            print("✅ Estadísticas procesadas correctamente.")
            # 2. Ingesta de Mapa de Tiros (Coordenadas)
            success_shots = scraper.ingest_shot_chart(TEST_GAME_ID)
            if success_shots:
                print("✅ Mapa de tiros procesado correctamente.")
        else:
            print("❌ Falló la ingesta de estadísticas generales.")

    finally:
        db.close()

if __name__ == "__main__":
    main()
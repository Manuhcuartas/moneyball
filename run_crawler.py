# run_crawler.py
import time
from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService
from app.core.config import settings

# CONFIGURACIÓN
# Usamos el ID de la Atlética Avilesina como "pivote" para sacar los partidos de la liga
ID_EQUIPO_OBJETIVO = settings.FBPA_ID_EQUIPO_PROPIO

def main():
    # 1. Conectar a BD
    db = SessionLocal()
    scraper = ScraperService(db)
    
    print("🚀 INICIANDO CRAWLER FBPA")
    print("------------------------------------------------")

    # 2. Obtener lista de partidos (Usando el método del Equipo para asegurar IDs encriptados)
    # Nota: scraper.get_calendar_from_team es un método nuevo que añadiremos al servicio
    games_to_scrape = scraper.get_calendar_from_team(ID_EQUIPO_OBJETIVO)
    
    if not games_to_scrape:
        print("⚠️ No se encontraron partidos terminados o hubo un error.")
        return

    print(f"📅 Se procesarán {len(games_to_scrape)} partidos terminados.")

    # 3. Bucle de procesamiento
    for i, game in enumerate(games_to_scrape):
        print(f"[{i+1}/{len(games_to_scrape)}] Procesando: {game['local']} vs {game['visitante']}...", end=" ")
        
        try:
            # Llamamos a la lógica de extracción de estadísticas
            # Pasamos el objeto 'game' que contiene el ID hash y los nombres
            success = scraper.ingest_game_statistics(game)
            
            if success:
                scraper.ingest_shot_chart(game['id'])
                print("✅ Boxscore + ShotChart OK")
        
            else:
                print("⚠️ Sin datos/Error")
            
            # Pausa de cortesía
            time.sleep(1.0)
            
        except Exception as e:
            print(f"❌ Error: {e}")

        

    db.close()
    print("\n✨ PROCESO COMPLETADO ✨")

if __name__ == "__main__":
    main()
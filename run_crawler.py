import time
from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService
from app.core.config import settings

# Limpieza de la variable raíz por si acaso
ID_EQUIPO_OBJETIVO = str(settings.FBPA_ID_EQUIPO_PROPIO).replace('"', '').replace("'", "").strip()

def main():
    # 1. Conectar a BD
    db = SessionLocal()
    scraper = ScraperService(db)
    
    print("🚀 INICIANDO CRAWLER FBPA")
    print(f"ℹ️  Equipo Objetivo Hash: {ID_EQUIPO_OBJETIVO[:10]}...") 
    print("------------------------------------------------")

    # --- PASO CRÍTICO: LOGIN ---
    # Esto obtiene la key válida para poder consultar el calendario después
    if not scraper.login():
        print("🛑 Deteniendo: No se pudo iniciar sesión en la API.")
        return

    # 2. Obtener lista de partidos
    games_to_scrape = scraper.get_calendar_from_team(ID_EQUIPO_OBJETIVO)
    
    if not games_to_scrape:
        print("⚠️ No se encontraron partidos terminados o hubo un error.")
        return

    print(f"📅 Se procesarán {len(games_to_scrape)} partidos terminados.")

    # 3. Bucle de procesamiento
    for i, game in enumerate(games_to_scrape):
        print(f"[{i+1}/{len(games_to_scrape)}] Procesando: {game['local']} vs {game['visitante']}...", end=" ")
        
        try:
            # 1. ESTADÍSTICAS
            stats_ok = scraper.ingest_game_statistics(game)
            
            if stats_ok:
                # 2. TIROS
                shots_ok = scraper.ingest_shot_chart(game['id'])

                pbp_ok = scraper.ingest_play_by_play(game['id']) 
                
                if shots_ok:
                    print("✅ TODO OK")
                else:
                    print("⚠️ Stats OK pero TIROS FALLARON")
            else:
                print("⚠️ Fallo en Boxscore")
            
            time.sleep(1.0) # Respetamos un poco el servidor
            
        except Exception as e:
            print(f"❌ Error General: {e}")

    db.close()
    print("\n✨ PROCESO COMPLETADO ✨")

if __name__ == "__main__":
    main()
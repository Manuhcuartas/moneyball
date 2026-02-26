import argparse
import time
from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService
from app.core.config import settings

ID_EQUIPO_OBJETIVO = str(settings.FEDERATION_ID_EQUIPO_PROPIO).replace('"', '').replace("'", "").strip()


def main():
    parser = argparse.ArgumentParser(description="Moneyball Federation Crawler")
    parser.add_argument("--force", action="store_true", help="Force re-scrape all finished games, even if already in DB")
    parser.add_argument("--jornada", type=str, default=None, help="Only process games from this round (e.g. '18')")
    args = parser.parse_args()

    db = SessionLocal()
    scraper = ScraperService(db)

    print("🚀 INICIANDO CRAWLER FEDERATION")
    print(f"ℹ️  Equipo Objetivo Hash: {ID_EQUIPO_OBJETIVO[:10]}...")
    if args.force:
        print("⚡ MODO FORZADO: Re-descargando todos los partidos terminados")
    if args.jornada:
        print(f"🎯 Filtrando jornada: {args.jornada}")
    print("------------------------------------------------")

    if not scraper.login():
        print("🛑 Deteniendo: No se pudo iniciar sesión en la API.")
        return

    games_to_scrape = scraper.get_calendar_from_team(ID_EQUIPO_OBJETIVO)

    if not games_to_scrape:
        print("⚠️ No se encontraron partidos o hubo un error.")
        return

    # Filter by jornada if specified
    if args.jornada:
        games_to_scrape = [g for g in games_to_scrape if str(g.get("jornada")) == args.jornada]
        print(f"📅 {len(games_to_scrape)} partidos en jornada {args.jornada}")

    print(f"📅 Se evaluarán {len(games_to_scrape)} partidos.")

    # Ingest standings
    scraper.ingest_standings()

    # Sync rosters for all teams (federation IDs, PPG, MPG)
    from app.models.stats import Team
    teams_with_hex = db.query(Team).filter(Team.federation_hex.isnot(None)).all()
    print(f"🔄 Sincronizando rosters de {len(teams_with_hex)} equipos...")
    for team in teams_with_hex:
        scraper.sync_roster(team.federation_hex)

    # Processing loop
    count_scraped = 0
    count_skipped = 0

    for i, game in enumerate(games_to_scrape):
        status_source = game.get("estado", "")
        print(f"[{i+1}/{len(games_to_scrape)}] {game['local']} vs {game['visitante']} ({status_source})", end=" ")

        # Always update metadata (time, venue, teams, logos)
        scraper.upsert_game_metadata(game)

        # Smart check: should we download stats?
        if not scraper.should_scrape(game['id'], status_source, force=args.force):
            print("⏭️  SKIPPED (Ya en BD)")
            count_skipped += 1
            continue

        print("📥 DESCARGANDO...")

        try:
            stats_ok = scraper.fetch_game_stats(game['id'])

            if stats_ok:
                shots_ok = scraper.ingest_shot_chart(game['id'])
                pbp_ok = scraper.ingest_play_by_play(game['id'])
                video_ok = scraper.ingest_game_video(game['id'])

                if shots_ok:
                    print("   ✅ TODO OK")
                else:
                    print("   ⚠️ Stats OK pero TIROS FALLARON")

                count_scraped += 1
            else:
                print("   ⚠️ Stats no disponibles (Partido no comenzado o Error)")

            time.sleep(1.0)

        except Exception as e:
            print(f"   ❌ Error General: {e}")

    print("------------------------------------------------")
    print(f"📊 Resumen de Ejecución:")
    print(f"   - Procesados (Nuevos/Actualizados): {count_scraped}")
    print(f"   - Omitidos (Ya existían): {count_skipped}")

    from app.services.stats_aggregation import calculate_all_season_stats
    calculate_all_season_stats(db)

    db.close()
    print("\n✨ PROCESO COMPLETADO ✨")

if __name__ == "__main__":
    main()
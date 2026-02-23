import logging
from fastapi import APIRouter, BackgroundTasks
from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

_crawler_running = False


def _run_crawler(force: bool = False, jornada: str | None = None):
    """Execute the crawler in the background."""
    global _crawler_running
    _crawler_running = True

    db = SessionLocal()
    try:
        scraper = ScraperService(db)
        team_id = str(settings.FEDERATION_ID_EQUIPO_PROPIO).replace('"', '').replace("'", "").strip()

        logger.info("🚀 Crawler started (force=%s, jornada=%s)", force, jornada)

        if not scraper.login():
            logger.error("🛑 Could not log in to federation API")
            return

        games = scraper.get_calendar_from_team(team_id)
        if not games:
            logger.warning("⚠️ No games found")
            return

        if jornada:
            games = [g for g in games if str(g.get("jornada")) == jornada]

        # Ingest standings (updates team logos too)
        scraper.ingest_standings()

        count_scraped = 0
        count_skipped = 0

        for game in games:
            status = game.get("estado", "")
            scraper.upsert_game_metadata(game)

            if not scraper.should_scrape(game["id"], status, force=force):
                count_skipped += 1
                continue

            try:
                if scraper.fetch_game_stats(game["id"]):
                    scraper.ingest_shot_chart(game["id"])
                    scraper.ingest_play_by_play(game["id"])
                    count_scraped += 1
            except Exception as e:
                logger.error("❌ Error processing game %s: %s", game["id"][:10], e)

        logger.info("✅ Crawler finished: scraped=%d, skipped=%d", count_scraped, count_skipped)

    except Exception as e:
        logger.error("❌ Crawler failed: %s", e)
    finally:
        db.close()
        _crawler_running = False


@router.post("/crawler/run")
async def trigger_crawler(
    background_tasks: BackgroundTasks,
    force: bool = False,
    jornada: str | None = None,
):
    """Trigger a crawler run in the background. Protected by API key middleware."""
    if _crawler_running:
        return {"status": "already_running", "message": "A crawler run is already in progress"}

    background_tasks.add_task(_run_crawler, force=force, jornada=jornada)
    return {"status": "started", "message": "Crawler started in background", "force": force, "jornada": jornada}


@router.get("/crawler/status")
async def crawler_status():
    """Check if the crawler is currently running."""
    return {"running": _crawler_running}

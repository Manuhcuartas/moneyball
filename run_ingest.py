from app.core.database import SessionLocal
from app.services.scraper_service import ScraperService

# Este ID es el que venía en tu Postman. Si falla, es que el partido es muy viejo.
TEST_GAME_ID = "36007A00450072004500790065007400360031003900450048006E00780052005A00720047006600370067003D003D00"

def main():
    # 1. Abrimos conexión a BD
    db = SessionLocal()
    try:
        # 2. Iniciamos el servicio
        scraper = ScraperService(db)
        # 3. Descargamos
        scraper.ingest_game(TEST_GAME_ID)
    finally:
        db.close()

if __name__ == "__main__":
    main()
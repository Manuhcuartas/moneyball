from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.v1.endpoints import analytics, games, standings, crawler
from app.core.config import settings

app = FastAPI(
    title="FBPA Moneyball API",
    description="Backend de analítica avanzada para baloncesto amateur",
    version="1.0.0",
)


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    """Require X-API-Key header on /api/ routes when API_KEY is configured."""
    if settings.API_KEY and request.url.path.startswith("/api/"):
        key = request.headers.get("X-API-Key")
        if key != settings.API_KEY:
            return JSONResponse(status_code=403, content={"detail": "Invalid API key"})
    return await call_next(request)


# CORS configuration
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    settings.FRONTEND_URL,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
app.include_router(games.router, prefix="/api/v1/games", tags=["Games"])
app.include_router(standings.router, prefix="/api/v1", tags=["Standings"])
app.include_router(crawler.router, prefix="/api/v1", tags=["Crawler"])


@app.get("/")
def read_root():
    return {
        "status": "online",
        "project": "Moneyball FBPA",
        "docs": "Go to /docs to see the API",
    }
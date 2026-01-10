from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# IMPORTANTE: Importa el router donde definimos los endpoints nuevos.
# Si tu archivo se llama 'analytics.py' (como te sugerí) usa este import:
from app.api.v1.endpoints import analytics

# Si decidiste mantenerlo en 'stats.py', descomenta esta línea y comenta la de arriba:
# from app.api.routes import stats as analytics 

app = FastAPI(
    title="FBPA Moneyball API",
    description="Backend de analítica avanzada para baloncesto amateur",
    version="1.0.0"
)

# --- 1. CONFIGURACIÓN DE CORS ---
# Esto es vital para que tu futuro Frontend (React, Vue, etc.) pueda pedir datos
# sin que el navegador bloquee la petición.
origins = [
    "http://localhost:3000",  # React / Next.js por defecto
    "http://localhost:5173",  # Vite / Vue por defecto
    "*"                       # Permitir todo (solo para desarrollo)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Permitir GET, POST, PUT, DELETE...
    allow_headers=["*"],
)

# --- 2. REGISTRAR RUTAS ---
# Aquí "enchufamos" el archivo de analítica al servidor principal.
# El prefijo "/api/v1" significa que todas tus URLs empezarán por ahí.
app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])

@app.get("/")
def read_root():
    return {
        "status": "online",
        "project": "Moneyball FBPA",
        "docs": "Go to /docs to see the API"
    }
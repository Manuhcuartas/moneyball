import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Base de Datos
    DATABASE_URL: str
    
    # Credenciales FBPA / IndalWeb
    FBPA_BASE_URL: str
    FBPA_ID_DISPOSITIVO: str
    FBPA_ID_FASE: str
    FBPA_ID_GRUPO: str
    FBPA_ID_EQUIPO_PROPIO: str

    # --- NUEVAS VARIABLES DE LOGIN (Gesdeportiva) ---
    FBPA_LOGIN_URL: str = "https://appaficionfbpa.gesdeportiva.es/dispositivo.ashx"
    FBPA_DEVICE_UID: str
    FBPA_PUSH_TOKEN: str
    FBPA_APP_VERSION: str = "50015"

    class Config:
        env_file = ".env"
        extra = "ignore" # Ignora variables extra en el .env si las hubiera

settings = Settings()
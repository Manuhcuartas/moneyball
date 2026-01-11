import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Base de Datos
    DATABASE_URL: str
    
    FBPA_BASE_URL: str
    FBPA_ID_DISPOSITIVO: str
    FBPA_ID_FASE: str
    FBPA_ID_GRUPO: str
    FBPA_ID_EQUIPO_PROPIO: str

    FBPA_LOGIN_URL: str
    FBPA_DEVICE_UID: str
    FBPA_PUSH_TOKEN: str
    FBPA_APP_VERSION: str

    class Config:
        env_file = ".env"
        extra = "ignore" # Ignora variables extra en el .env si las hubiera

settings = Settings()
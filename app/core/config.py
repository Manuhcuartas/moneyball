from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Moneyball Asturias"
    DATABASE_URL: str
    
    # API FBPA
    FBPA_BASE_URL: str
    FBPA_ID_DISPOSITIVO: str
    FBPA_ID_FASE: str
    FBPA_ID_GRUPO: str
    FBPA_ID_EQUIPO_PROPIO: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
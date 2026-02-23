from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str

    FEDERATION_BASE_URL: str
    FEDERATION_ID_DISPOSITIVO: str
    FEDERATION_ID_FASE: str
    FEDERATION_ID_GRUPO: str
    FEDERATION_ID_EQUIPO_PROPIO: str

    FEDERATION_LOGIN_URL: str
    FEDERATION_DEVICE_UID: str
    FEDERATION_PUSH_TOKEN: str
    FEDERATION_APP_VERSION: str

    API_KEY: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
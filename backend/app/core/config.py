from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fase0.db"
    app_name: str = "Classificador de Comprovantes"


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aq_trading"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Futu
    futu_host: str = "127.0.0.1"
    futu_port: int = 11111

    # App
    debug: bool = True

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    app_name: str = "Mi API Backend"
    debug: bool = False
    
    # Base de datos
    db_user: str
    db_password: str
    db_host: str
    db_port: int = 5432  # ← CAMBIÉ DE 6543 A 5432
    db_name: str = "postgres"
    
    # Seguridad
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    allowed_origins: List[str] = [
        "http://localhost:3000",
        "exp://127.0.0.1:19000",
        "http://192.168.1.100:19006"
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

settings = Settings()
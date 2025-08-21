from pydantic_settings import BaseSettings
from typing import List
import os
class Settings(BaseSettings):
    # Información de la aplicación
    app_name: str = "Mi API Backend"
    debug: bool = False
    
    # Base de datos
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str
    db_password: str
    db_name: str
    database_url: str = ""
    
    # Seguridad
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    allowed_origins: List[str] = [
        "http://localhost:3000",                       # navegador web local
        "exp://127.0.0.1:19000",                       # Expo dev client iOS/Android
        "http://192.168.1.100:19006"                   # Expo Go dispositivo físico
    ]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Si no se proporciona DATABASE_URL, la construimos
        if not self.database_url:
            self.database_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"


# Instancia global de configuración
settings = Settings()
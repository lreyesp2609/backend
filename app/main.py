from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database.config import settings
from .database.database import *
from .usuarios.models import *
from .ubicaciones.models import *
from .database.seed import create_default_roles
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear la aplicación FastAPI
app = FastAPI(
    title=settings.app_name,
    description="Backend API con FastAPI y PostgreSQL",
    version="1.0.0",
    debug=settings.debug
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # permite todos los orígenes
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 Iniciando {settings.app_name}")
    
    if test_connection():
        logger.info("✅ Base de datos conectada correctamente")
        # Crear tablas
        create_tables()
        # Crear rol por defecto
        db = SessionLocal()
        try:
            create_default_roles(db)
        finally:
            db.close()
    else:
        logger.error("❌ No se pudo conectar a la base de datos")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Se ejecuta al cerrar la aplicación.
    """
    logger.info("🛑 Cerrando la aplicación")

@app.get("/")
async def root():
    rutas = []
    for route in app.routes:
        if hasattr(route, "path") and route.path not in ["/", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]:
            rutas.append({"path": route.path, "methods": list(route.methods)})
    return {"rutas_disponibles": rutas}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )


from .usuarios.router import router as usuarios_router
from .login.router import router as login_router
from .ubicaciones.router import router as ubicaciones_router
app.include_router(usuarios_router)
app.include_router(login_router)
app.include_router(ubicaciones_router)
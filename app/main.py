from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware  # 🆕 AGREGAR
from .database.config import settings
from .database.database import *
from .database.relationships import configure_relationships
from .usuarios.models import *
from .ubicaciones.models import *
from .ubicaciones.ubicaciones_historial.models import *
from .services.models import *
from .ubicaciones.ubicaciones_historial.rutas.models import *
from .database.seed import create_default_roles_and_admin
from .ubicaciones.ubicaciones_historial.seed import create_default_estados_ubicacion
from .grupos.models import *
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🆕 AGREGAR: TrustedHost para WebSockets en Render.com
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 Iniciando {settings.app_name}")
    
    if test_connection():
        logger.info("✅ Base de datos conectada correctamente")
        
        # PASO 1: Configurar relaciones ANTES de crear tablas
        configure_relationships()
        logger.info("✅ Relaciones entre modelos configuradas")
        
        # PASO 2: Crear tablas
        create_tables()
        logger.info("✅ Tablas creadas exitosamente")
        
        # PASO 3: Crear datos semilla
        db = SessionLocal()
        try:
            create_default_roles_and_admin(db)
            create_default_estados_ubicacion(db)
            
            # 🔹 Seed de transportes
            from app.ubicaciones.ubicaciones_historial.rutas.models import Transporte
            from app.ubicaciones.ubicaciones_historial.rutas.seed import seed_transportes
            seed_transportes(db)
            logger.info("✅ Transportes creados exitosamente")
            
            # ✅ AGREGAR - Inicializar Firebase FCM
            from app.services.fcm_service import FCMService
            
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
    rutas_por_modulo = {}
    for route in app.routes:
        if hasattr(route, "path") and route.path not in ["/", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]:
            prefijo = route.path.strip("/").split("/")[0]
            if prefijo not in rutas_por_modulo:
                rutas_por_modulo[prefijo] = []
            
            methods = list(route.methods) if hasattr(route, 'methods') else ["WEBSOCKET"]
            
            rutas_por_modulo[prefijo].append({
                "path": route.path, 
                "methods": methods
            })
    return rutas_por_modulo


# Incluir routers
from .usuarios.router import router as usuarios_router
from .login.router import router as login_router
from .ubicaciones.router import router as ubicaciones_router
from .ubicaciones.ubicaciones_historial.router import router as estados_ubicacion_router
from .ubicaciones.ubicaciones_historial.rutas.routers import router as rutas_router
from .services.router import router as services_router
from .recordatorios.routers import router as recordatorios_router
from .grupos.router import router as grupos_router
from .services.fcm_router import router as fcm_router
from .grupos.WebSocket.routers import router as ws_grupos_router

app.include_router(usuarios_router)
app.include_router(login_router)
app.include_router(ubicaciones_router)
app.include_router(estados_ubicacion_router)
app.include_router(rutas_router)
app.include_router(services_router)
app.include_router(recordatorios_router)
app.include_router(grupos_router)
app.include_router(fcm_router)
app.include_router(ws_grupos_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*"
    )
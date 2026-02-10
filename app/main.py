from fastapi import FastAPI, status  # 👈 Agrega status aquí
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from .database.config import settings
from .database.database import *
from .usuarios.models import *
from .ubicaciones.models import *
from .ubicaciones.ubicaciones_historial.models import *
from .services.models import *
from .ubicaciones.ubicaciones_historial.rutas.models import *
from .database.seed import create_default_roles_and_admin
from .ubicaciones.ubicaciones_historial.seed import create_default_estados_ubicacion
from .grupos.models import *
from .seguridad.models import *
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

# TrustedHost para WebSockets
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# 🆕 AGREGAR ESTE ENDPOINT DE HEALTH CHECK
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Endpoint de health check para Azure Container Apps.
    Verifica que la aplicación está corriendo y la DB conectada.
    """
    logger.info("🏥 Health check solicitado")
    
    health_status = {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "database": "unknown"
    }
    
    # Verificar conexión a base de datos
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        health_status["database"] = "connected"
        logger.info("✅ Health check: DB conectada")
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"
        logger.error(f"❌ Health check: DB error - {e}")
    
    return health_status


@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 Iniciando {settings.app_name}")
    
    if test_connection():
        logger.info("✅ Base de datos conectada correctamente")
        
        # PASO 1: Crear tablas
        create_tables()
        logger.info("✅ Tablas creadas exitosamente")
        
        # PASO 2: Crear datos semilla
        db = SessionLocal()
        try:
            create_default_roles_and_admin(db)
            create_default_estados_ubicacion(db)
            
            from app.ubicaciones.ubicaciones_historial.rutas.models import Transporte
            from app.ubicaciones.ubicaciones_historial.rutas.seed import seed_transportes
            seed_transportes(db)
            logger.info("✅ Transportes creados exitosamente")
            
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
from .seguridad.seguridad import router as seguridad_router
from .tracking.router import router as tracking_router

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
app.include_router(seguridad_router)
app.include_router(tracking_router)

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
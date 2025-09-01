from sqlalchemy.orm import Session

from app.ubicaciones.models import UbicacionUsuario
import logging

from app.ubicaciones.ubicaciones_historial.models import EstadoUbicacion, EstadoUbicacionUsuario

logger = logging.getLogger(__name__)

def create_default_estado_ubicaciones(db: Session):
    ubicaciones = db.query(UbicacionUsuario).all()
    for ubicacion in ubicaciones:
        estado_existente = db.query(EstadoUbicacionUsuario).filter_by(ubicacion_id=ubicacion.id).first()
        if estado_existente:
            logger.info(f"✅ Ubicación {ubicacion.id} ya tiene estado asignado")
            continue
        
        nuevo_estado = EstadoUbicacionUsuario(
            ubicacion_id=ubicacion.id,
            estado=EstadoUbicacion.EN_PROGRESO
        )
        try:
            db.add(nuevo_estado)
            db.commit()
            db.refresh(nuevo_estado)
            logger.info(f"✅ Estado inicial EN_PROGRESO creado para ubicación {ubicacion.id}")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error creando estado para ubicación {ubicacion.id}: {e}")
            raise

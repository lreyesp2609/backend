from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import RutaUsuario, SegmentoRuta, PasoRuta
from .schemas import RutaUsuarioCreate
from ..models import EstadoUbicacion, EstadoUbicacionUsuario
from fastapi import HTTPException
from typing import List, Optional

class CRUDRutas:

    def create_ruta(self, db: Session, ruta: RutaUsuarioCreate) -> RutaUsuario:
        """Crear ruta automáticamente con estado 'EN_PROGRESO'"""
        
        # 1. Buscar el estado 'EN_PROGRESO'
        estado_en_progreso = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == "EN_PROGRESO",
            EstadoUbicacion.activo == True
        ).first()
        
        if not estado_en_progreso:
            raise HTTPException(
                status_code=500,
                detail="El estado 'EN_PROGRESO' no existe en la base de datos"
            )
        
        # 2. Crear o encontrar EstadoUbicacionUsuario
        estado_usuario = db.query(EstadoUbicacionUsuario).filter(
            EstadoUbicacionUsuario.ubicacion_id == ruta.ubicacion_id,
            EstadoUbicacionUsuario.usuario_id == ruta.usuario_id,
            EstadoUbicacionUsuario.estado_ubicacion_id == estado_en_progreso.id
        ).first()
        
        if not estado_usuario:
            estado_usuario = EstadoUbicacionUsuario(
                ubicacion_id=ruta.ubicacion_id,
                usuario_id=ruta.usuario_id,
                estado_ubicacion_id=estado_en_progreso.id,
                duracion_segundos=0.0
            )
            db.add(estado_usuario)
            db.flush()  # Obtener ID sin commit completo

        # 3. Crear la ruta usando estado_usuario.id
        return self._create_ruta_internal(db, ruta, estado_usuario.id)
    
    def _create_ruta_internal(self, db: Session, ruta: RutaUsuarioCreate, estado_id: int) -> RutaUsuario:
        """Método interno para crear la ruta con sus segmentos y pasos"""
        try:
            db_ruta = RutaUsuario(
                estado_id=estado_id,
                transporte_id=ruta.transporte_id,  # <-- asignar transporte
                distancia_total=ruta.distancia_total,
                duracion_total=ruta.duracion_total,
                geometria=ruta.geometria,
                fecha_inicio=ruta.fecha_inicio,
                fecha_fin=ruta.fecha_fin
            )

            for segmento in ruta.segmentos:
                db_segmento = SegmentoRuta(
                    distancia=segmento.distancia,
                    duracion=segmento.duracion
                )
                for paso in segmento.pasos:
                    db_paso = PasoRuta(
                        instruccion=paso.instruccion,
                        distancia=paso.distancia,
                        duracion=paso.duracion,
                        tipo=paso.tipo
                    )
                    db_segmento.pasos.append(db_paso)
                db_ruta.segmentos.append(db_segmento)

            db.add(db_ruta)
            db.commit()
            db.refresh(db_ruta)
            return db_ruta
        
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Error de integridad en la base de datos: {str(e)}"
            )
    
    def get_ruta(self, db: Session, ruta_id: int) -> Optional[RutaUsuario]:
        return db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
    
    def list_rutas(self, db: Session, skip: int = 0, limit: int = 100) -> List[RutaUsuario]:
        return db.query(RutaUsuario).offset(skip).limit(limit).all()
    
    def delete_ruta(self, db: Session, ruta_id: int) -> bool:
        ruta = db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
        if not ruta:
            return False
        try:
            db.delete(ruta)
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Error al eliminar la ruta: {str(e)}"
            )

    def get_tipos_estados_disponibles(self, db: Session):
        return db.query(EstadoUbicacion).filter(EstadoUbicacion.activo == True).order_by(EstadoUbicacion.orden).all()
    
    def get_estados_usuario_disponibles(self, db: Session):
        return db.query(EstadoUbicacionUsuario).all()

# Instancia para usar en el router
crud_rutas = CRUDRutas()

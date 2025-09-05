from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import RutaUsuario, SegmentoRuta, PasoRuta
from .schemas import RutaUsuarioCreate
from ..models import EstadoUbicacion, EstadoUbicacionUsuario
from fastapi import HTTPException
from typing import List, Optional
from ..rutas.models import Transporte
# 🔥 NUEVOS IMPORTS
from ....services.ucb_service import UCBService
import logging

logger = logging.getLogger(__name__)

class CRUDRutas:

    def create_ruta(self, db: Session, ruta: RutaUsuarioCreate, usuario_id: int, tipo_ruta_usado: str = None) -> RutaUsuario:
        """
        🔥 ACTUALIZADO: Ahora acepta tipo_ruta_usado del ML
        """
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
            EstadoUbicacionUsuario.usuario_id == usuario_id,
            EstadoUbicacionUsuario.estado_ubicacion_id == estado_en_progreso.id
        ).first()
        
        if not estado_usuario:
            estado_usuario = EstadoUbicacionUsuario(
                ubicacion_id=ruta.ubicacion_id,
                usuario_id=usuario_id,
                estado_ubicacion_id=estado_en_progreso.id,
                duracion_segundos=0.0
            )
            db.add(estado_usuario)
            db.flush()
        
        # 3. Verificar transporte por nombre
        transporte = db.query(Transporte).filter(
            Transporte.nombre == ruta.transporte_texto
        ).first()
        
        if not transporte:
            raise HTTPException(
                status_code=400,
                detail=f"El transporte '{ruta.transporte_texto}' no existe en la base de datos"
            )
        
        # 4. Crear la ruta usando el id real Y el tipo del ML
        return self._create_ruta_internal(db, ruta, estado_usuario.id, transporte.id, tipo_ruta_usado)

    def _create_ruta_internal(
        self, db: Session, ruta: RutaUsuarioCreate, estado_id: int, transporte_id: int, tipo_ruta_usado: str = None
    ) -> RutaUsuario:
        """
        🔥 ACTUALIZADO: Método interno para crear la ruta CON tipo_ruta_usado
        """
        try:
            db_ruta = RutaUsuario(
                estado_id=estado_id,
                transporte_id=transporte_id,
                distancia_total=ruta.distancia_total,
                duracion_total=ruta.duracion_total,
                geometria=ruta.geometria,
                fecha_inicio=ruta.fecha_inicio,
                fecha_fin=ruta.fecha_fin,
                tipo_ruta_usado=tipo_ruta_usado  # 🔥 NUEVO CAMPO
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
            
            # 🔥 LOG para debugging
            logger.info(f"✅ Ruta creada con tipo ML: {tipo_ruta_usado} para estado_id: {estado_id}")
            
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

    def get_tipos_estados_disponibles(self, db: Session):
        return db.query(EstadoUbicacion).filter(EstadoUbicacion.activo == True).order_by(EstadoUbicacion.orden).all()
    
    def get_estados_usuario_disponibles(self, db: Session):
        return db.query(EstadoUbicacionUsuario).all()

    def finalizar_ruta(self, db: Session, ruta_id: int) -> RutaUsuario:
        """
        🔥 ACTUALIZADO: Ahora actualiza el bandit ML con feedback positivo
        """
        ruta = db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
        if not ruta:
            raise HTTPException(status_code=404, detail="Ruta no encontrada")
        
        # 1. Buscar estado FINALIZADA
        estado_finalizada = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == "FINALIZADA",
            EstadoUbicacion.activo == True
        ).first()

        if not estado_finalizada:
            raise HTTPException(status_code=500, detail="Estado 'FINALIZADA' no existe")

        # 2. Marcar la ruta como finalizada
        ruta.fecha_fin = datetime.utcnow()
        db.commit()
        db.refresh(ruta)

        # 3. Actualizar EstadoUbicacionUsuario
        estado_usuario = db.query(EstadoUbicacionUsuario).filter(
            EstadoUbicacionUsuario.id == ruta.estado_id
        ).first()

        if estado_usuario:
            estado_usuario.estado_ubicacion_id = estado_finalizada.id
            db.commit()
            db.refresh(estado_usuario)

            # 🔥 ACTUALIZAR BANDIT ML CON FEEDBACK POSITIVO
            try:
                if ruta.tipo_ruta_usado:  # Solo si tiene el tipo guardado
                    ucb_service = UCBService(db)
                    ucb_service.actualizar_feedback(
                        usuario_id=estado_usuario.usuario_id,
                        tipo_usado=ruta.tipo_ruta_usado,  # 🎯 Tipo exacto que se usó
                        completada=True,  # ✅ Ruta completada exitosamente
                        ubicacion_id=estado_usuario.ubicacion_id,
                        distancia=ruta.distancia_total,
                        duracion=ruta.duracion_total
                    )
                    
                    logger.info(f"✅ BANDIT ACTUALIZADO - FINALIZADA: Usuario {estado_usuario.usuario_id}, "
                               f"Ruta {ruta_id}, Tipo: {ruta.tipo_ruta_usado}, Ubicación: {estado_usuario.ubicacion_id}")
                else:
                    logger.warning(f"⚠️ Ruta {ruta_id} no tiene tipo_ruta_usado - No se puede actualizar bandit")
                
            except Exception as e:
                logger.error(f"❌ Error actualizando bandit en finalizar_ruta {ruta_id}: {e}")
                # No hacer rollback - la ruta ya se finalizó correctamente

        return ruta
    
    def cancelar_ruta(self, db: Session, ruta_id: int) -> Optional[RutaUsuario]:
        """
        🔥 ACTUALIZADO: Ahora actualiza el bandit ML con feedback negativo
        """
        ruta = db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
        if not ruta:
            return None

        # 1. Buscar estado CANCELADA
        estado_cancelada = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == "CANCELADA",
            EstadoUbicacion.activo == True
        ).first()

        if not estado_cancelada:
            raise HTTPException(status_code=500, detail="Estado 'CANCELADA' no existe")

        # 2. Actualizar la ruta
        ruta.fecha_fin = datetime.utcnow()
        db.commit()
        db.refresh(ruta)

        # 3. Actualizar el EstadoUbicacionUsuario
        estado_usuario = db.query(EstadoUbicacionUsuario).filter(
            EstadoUbicacionUsuario.id == ruta.estado_id
        ).first()

        if estado_usuario:
            estado_usuario.estado_ubicacion_id = estado_cancelada.id
            db.commit()
            db.refresh(estado_usuario)

            # 🔥 ACTUALIZAR BANDIT ML CON FEEDBACK NEGATIVO
            try:
                if ruta.tipo_ruta_usado:  # Solo si tiene el tipo guardado
                    ucb_service = UCBService(db)
                    ucb_service.actualizar_feedback(
                        usuario_id=estado_usuario.usuario_id,
                        tipo_usado=ruta.tipo_ruta_usado,  # 🎯 Tipo exacto que se usó
                        completada=False,  # ❌ Ruta cancelada = feedback negativo
                        ubicacion_id=estado_usuario.ubicacion_id,
                        distancia=ruta.distancia_total,
                        duracion=ruta.duracion_total
                    )
                    
                    logger.info(f"⚠️ BANDIT ACTUALIZADO - CANCELADA: Usuario {estado_usuario.usuario_id}, "
                               f"Ruta {ruta_id}, Tipo: {ruta.tipo_ruta_usado}, Ubicación: {estado_usuario.ubicacion_id}")
                else:
                    logger.warning(f"⚠️ Ruta {ruta_id} no tiene tipo_ruta_usado - No se puede actualizar bandit")
                
            except Exception as e:
                logger.error(f"❌ Error actualizando bandit en cancelar_ruta {ruta_id}: {e}")
                # No hacer rollback - la ruta ya se canceló correctamente

        return ruta

# Instancia para usar en el router
crud_rutas = CRUDRutas()
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
        🔥 ARQUITECTURA FINAL: Crea TANTO ruta COMO EstadoUbicacionUsuario
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

        # 2. Crear/actualizar EstadoUbicacionUsuario (para ML y analytics)
        estado_usuario_existente = db.query(EstadoUbicacionUsuario).filter(
            EstadoUbicacionUsuario.ubicacion_id == ruta.ubicacion_id,
            EstadoUbicacionUsuario.usuario_id == usuario_id
        ).first()

        if estado_usuario_existente:
            # Actualizar estado existente
            estado_usuario_existente.estado_ubicacion_id = estado_en_progreso.id
            estado_usuario_existente.duracion_segundos = 0.0
            estado_usuario = estado_usuario_existente
            logger.info(f"🔄 Actualizando EstadoUbicacionUsuario existente: {estado_usuario.id}")
        else:
            # Crear nuevo estado
            estado_usuario = EstadoUbicacionUsuario(
                ubicacion_id=ruta.ubicacion_id,
                usuario_id=usuario_id,
                estado_ubicacion_id=estado_en_progreso.id,
                duracion_segundos=0.0
            )
            db.add(estado_usuario)
            logger.info(f"✅ Creando nuevo EstadoUbicacionUsuario")
        
        db.flush()  # Para obtener el ID
        logger.info(f"📊 EstadoUbicacionUsuario ID: {estado_usuario.id}")

        # 3. Verificar transporte por nombre
        transporte = db.query(Transporte).filter(
            Transporte.nombre == ruta.transporte_texto
        ).first()
        
        if not transporte:
            raise HTTPException(
                status_code=400,
                detail=f"El transporte '{ruta.transporte_texto}' no existe en la base de datos"
            )

        # 4. Crear la ruta (estado independiente para la ruta)
        return self._create_ruta_internal(
            db, 
            ruta, 
            transporte.id, 
            tipo_ruta_usado, 
            estado_ruta_id=estado_en_progreso.id,
            usuario_id=usuario_id,
            estado_usuario_id=estado_usuario.id  # 🔥 AQUÍ SE ASIGNA
        )

    def _create_ruta_internal(
        self, db: Session, ruta: RutaUsuarioCreate, transporte_id: int, 
        tipo_ruta_usado: str = None, estado_ruta_id: int = None, 
        usuario_id: int = None, estado_usuario_id: int = None
    ) -> RutaUsuario:
        """
        🔥 ARQUITECTURA FINAL: Crea la ruta CON referencia a EstadoUbicacionUsuario
        """
        try:
            db_ruta = RutaUsuario(
                transporte_id=transporte_id,
                usuario_id=usuario_id,  # 🔥 IMPORTANTE
                distancia_total=ruta.distancia_total,
                duracion_total=ruta.duracion_total,
                geometria=ruta.geometria,
                fecha_inicio=ruta.fecha_inicio,
                fecha_fin=ruta.fecha_fin,
                tipo_ruta_usado=tipo_ruta_usado,
                estado_ruta_id=estado_ruta_id,
                estado_usuario_id=estado_usuario_id  # 🔥 AQUÍ SE GUARDA LA REFERENCIA
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
            
            logger.info(f"✅ Ruta creada - ID: {db_ruta.id}, Tipo ML: {tipo_ruta_usado}, "
                       f"estado_ruta_id: {estado_ruta_id}, estado_usuario_id: {estado_usuario_id}")
            
            return db_ruta
        
        except IntegrityError as e:
            db.rollback()
            logger.error(f"❌ Error de integridad: {e}")
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

    def finalizar_ruta(self, db: Session, ruta_id: int) -> RutaUsuario:
        """
        🔥 ARQUITECTURA FINAL: Actualiza TANTO rutas_usuario COMO estados_ubicacion_usuario
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

        # 2. Actualizar la ruta
        ruta.fecha_fin = datetime.utcnow()
        ruta.estado_ruta_id = estado_finalizada.id
        db.commit()
        db.refresh(ruta)

        # 3. Actualizar EstadoUbicacionUsuario si existe la referencia
        if ruta.estado_usuario_id:
            estado_usuario = db.query(EstadoUbicacionUsuario).filter(
                EstadoUbicacionUsuario.id == ruta.estado_usuario_id
            ).first()

            if estado_usuario:
                estado_usuario.estado_ubicacion_id = estado_finalizada.id
                # Calcular duración si es necesario
                if ruta.fecha_inicio and ruta.fecha_fin:
                    duracion = (ruta.fecha_fin - ruta.fecha_inicio).total_seconds()
                    estado_usuario.duracion_segundos = duracion
                
                db.commit()
                db.refresh(estado_usuario)
                logger.info(f"✅ EstadoUbicacionUsuario {estado_usuario.id} actualizado a FINALIZADA")
            else:
                logger.warning(f"⚠️ EstadoUbicacionUsuario {ruta.estado_usuario_id} no encontrado")
        else:
            logger.warning(f"⚠️ Ruta {ruta_id} no tiene estado_usuario_id")

        # 4. Actualizar Bandit ML
        try:
            if ruta.tipo_ruta_usado and ruta.usuario_id:
                ucb_service = UCBService(db)
                # Buscar ubicacion_id a través del EstadoUbicacionUsuario
                ubicacion_id = None
                if ruta.estado_usuario_id:
                    estado_usuario = db.query(EstadoUbicacionUsuario).filter(
                        EstadoUbicacionUsuario.id == ruta.estado_usuario_id
                    ).first()
                    if estado_usuario:
                        ubicacion_id = estado_usuario.ubicacion_id

                ucb_service.actualizar_feedback(
                    usuario_id=ruta.usuario_id,
                    tipo_usado=ruta.tipo_ruta_usado,
                    completada=True,
                    ubicacion_id=ubicacion_id,
                    distancia=ruta.distancia_total,
                    duracion=ruta.duracion_total
                )
                logger.info(f"✅ BANDIT ACTUALIZADO - FINALIZADA: Usuario {ruta.usuario_id}, "
                            f"Ruta {ruta_id}, Tipo: {ruta.tipo_ruta_usado}, Ubicación: {ubicacion_id}")
            else:
                logger.warning(f"⚠️ Ruta {ruta_id} no tiene tipo_ruta_usado o usuario_id")
        except Exception as e:
            logger.error(f"❌ Error actualizando bandit en finalizar_ruta {ruta_id}: {e}")

        return ruta
    
    def cancelar_ruta(self, db: Session, ruta_id: int) -> RutaUsuario:
        """
        🔥 ARQUITECTURA FINAL: Actualiza TANTO rutas_usuario COMO estados_ubicacion_usuario
        """
        ruta = db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
        if not ruta:
            raise HTTPException(status_code=404, detail="Ruta no encontrada")

        # Buscar estado CANCELADA
        estado_cancelada = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == "CANCELADA",
            EstadoUbicacion.activo == True
        ).first()
        if not estado_cancelada:
            raise HTTPException(status_code=500, detail="Estado 'CANCELADA' no existe")

        # Actualizar la ruta
        ruta.estado_ruta_id = estado_cancelada.id
        ruta.fecha_fin = datetime.utcnow()
        db.commit()
        db.refresh(ruta)

        # Actualizar EstadoUbicacionUsuario si existe la referencia
        if ruta.estado_usuario_id:
            estado_usuario = db.query(EstadoUbicacionUsuario).filter(
                EstadoUbicacionUsuario.id == ruta.estado_usuario_id
            ).first()

            if estado_usuario:
                estado_usuario.estado_ubicacion_id = estado_cancelada.id
                # Calcular duración si es necesario
                if ruta.fecha_inicio and ruta.fecha_fin:
                    duracion = (ruta.fecha_fin - ruta.fecha_inicio).total_seconds()
                    estado_usuario.duracion_segundos = duracion
                
                db.commit()
                db.refresh(estado_usuario)
                logger.info(f"✅ EstadoUbicacionUsuario {estado_usuario.id} actualizado a CANCELADA")
            else:
                logger.warning(f"⚠️ EstadoUbicacionUsuario {ruta.estado_usuario_id} no encontrado")
        else:
            logger.warning(f"⚠️ Ruta {ruta_id} no tiene estado_usuario_id")

        # 🔥 Actualizar Bandit ML para cancelación
        try:
            if ruta.tipo_ruta_usado and ruta.usuario_id:
                ucb_service = UCBService(db)
                # Buscar ubicacion_id a través del EstadoUbicacionUsuario
                ubicacion_id = None
                if ruta.estado_usuario_id:
                    estado_usuario = db.query(EstadoUbicacionUsuario).filter(
                        EstadoUbicacionUsuario.id == ruta.estado_usuario_id
                    ).first()
                    if estado_usuario:
                        ubicacion_id = estado_usuario.ubicacion_id

                ucb_service.actualizar_feedback(
                    usuario_id=ruta.usuario_id,
                    tipo_usado=ruta.tipo_ruta_usado,
                    completada=False,  # Cancelada = False
                    ubicacion_id=ubicacion_id,
                    distancia=ruta.distancia_total,
                    duracion=ruta.duracion_total
                )
                logger.info(f"✅ BANDIT ACTUALIZADO - CANCELADA: Usuario {ruta.usuario_id}, "
                            f"Ruta {ruta_id}, Tipo: {ruta.tipo_ruta_usado}, Ubicación: {ubicacion_id}")
        except Exception as e:
            logger.error(f"❌ Error actualizando bandit en cancelar_ruta {ruta_id}: {e}")

        return ruta

# Instancia para usar en el router
crud_rutas = CRUDRutas()
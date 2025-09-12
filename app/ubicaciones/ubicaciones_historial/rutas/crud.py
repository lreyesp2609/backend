from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .models import RutaUsuario, SegmentoRuta, PasoRuta
from .schemas import RutaUsuarioCreate
from ..models import EstadoUbicacion, EstadoUbicacionUsuario
from fastapi import HTTPException
from typing import List, Optional
from ..rutas.models import Transporte

from ....services.ucb_service import UCBService
from ....services.detector_desobediencia import DetectorDesobedienciaService, convertir_puntos_gps_a_geometria
import logging
logger = logging.getLogger(__name__)

class CRUDRutas:

    def create_ruta(self, db: Session, ruta: RutaUsuarioCreate, usuario_id: int, tipo_ruta_usado: str = None) -> RutaUsuario:
        """
        🔥 ARQUITECTURA FINAL: Crea TANTO ruta COMO EstadoUbicacionUsuario
        Lógica corregida: Solo reutilizar si está EN_PROGRESO
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

        # 2. Buscar EstadoUbicacionUsuario existente
        estado_usuario_existente = db.query(EstadoUbicacionUsuario).filter(
            EstadoUbicacionUsuario.ubicacion_id == ruta.ubicacion_id,
            EstadoUbicacionUsuario.usuario_id == usuario_id
        ).first()

        estado_usuario = None

        if estado_usuario_existente:
            # Verificar el estado actual
            estado_actual = db.query(EstadoUbicacion).filter(
                EstadoUbicacion.id == estado_usuario_existente.estado_ubicacion_id
            ).first()
            
            if estado_actual and estado_actual.nombre == "EN_PROGRESO":
                # ✅ CASO 1: Ya está EN_PROGRESO - REUTILIZAR
                estado_usuario_existente.duracion_segundos = 0.0  # Resetear duración
                estado_usuario = estado_usuario_existente
                logger.info(f"🔄 Reutilizando EstadoUbicacionUsuario EN_PROGRESO: {estado_usuario.id}")
                
            else:
                # ✅ CASO 2: Está FINALIZADA/CANCELADA - CREAR NUEVO
                estado_usuario = EstadoUbicacionUsuario(
                    ubicacion_id=ruta.ubicacion_id,
                    usuario_id=usuario_id,
                    estado_ubicacion_id=estado_en_progreso.id,
                    duracion_segundos=0.0
                )
                db.add(estado_usuario)
                logger.info(f"✅ Creando NUEVO EstadoUbicacionUsuario (anterior estaba {estado_actual.nombre if estado_actual else 'UNKNOWN'})")
        else:
            # ✅ CASO 3: No existe - CREAR NUEVO
            estado_usuario = EstadoUbicacionUsuario(
                ubicacion_id=ruta.ubicacion_id,
                usuario_id=usuario_id,
                estado_ubicacion_id=estado_en_progreso.id,
                duracion_segundos=0.0
            )
            db.add(estado_usuario)
            logger.info(f"✅ Creando primer EstadoUbicacionUsuario para ubicación {ruta.ubicacion_id}")
        
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
    
    def finalizar_ruta(self, db: Session, ruta_id: int, fecha_fin: str, 
                       puntos_gps: List[dict] = None, 
                       siguio_ruta_recomendada: bool = None,
                       porcentaje_similitud: float = None):
        """
        Finaliza ruta y detecta desobediencia - VERSIÓN CORREGIDA
        """
        logger.info(f"Finalizando ruta {ruta_id} - GPS recibidos: {len(puntos_gps) if puntos_gps else 0}")
        logger.info(f"RECIBIDO desde Android: siguio={siguio_ruta_recomendada}, porcentaje={porcentaje_similitud}")

        # 1. VALIDAR RUTA
        ruta = db.query(RutaUsuario).filter(RutaUsuario.id == ruta_id).first()
        if not ruta:
            raise HTTPException(status_code=404, detail="Ruta no encontrada")
        
        # 2. ESTADO FINALIZADA
        estado_finalizada = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == "FINALIZADA",
            EstadoUbicacion.activo == True
        ).first()

        if not estado_finalizada:
            raise HTTPException(status_code=500, detail="Estado 'FINALIZADA' no existe")

        # 3. ACTUALIZAR FECHA FIN
        import dateutil.parser
        try:
            ruta.fecha_fin = dateutil.parser.parse(fecha_fin)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {fecha_fin}")
        
        ruta.estado_ruta_id = estado_finalizada.id
        db.commit()
        db.refresh(ruta)

        # 4. ACTUALIZAR ESTADO UBICACIÓN
        ubicacion_id = None
        if ruta.estado_usuario_id:
            estado_usuario = db.query(EstadoUbicacionUsuario).filter(
                EstadoUbicacionUsuario.id == ruta.estado_usuario_id
            ).first()

            if estado_usuario:
                estado_usuario.estado_ubicacion_id = estado_finalizada.id
                ubicacion_id = estado_usuario.ubicacion_id
                
                if ruta.fecha_inicio and ruta.fecha_fin:
                    duracion = (ruta.fecha_fin - ruta.fecha_inicio).total_seconds()
                    estado_usuario.duracion_segundos = duracion
                
                db.commit()
                db.refresh(estado_usuario)

        # 5. ACTUALIZAR BANDIT ML
        try:
            if ruta.tipo_ruta_usado and ruta.usuario_id:
                ucb_service = UCBService(db)
                ucb_service.actualizar_feedback(
                    usuario_id=ruta.usuario_id,
                    tipo_usado=ruta.tipo_ruta_usado,
                    completada=True,
                    ubicacion_id=ubicacion_id,
                    distancia=ruta.distancia_total,
                    duracion=ruta.duracion_total,
                    fecha_inicio=ruta.fecha_inicio.isoformat() if ruta.fecha_inicio else None,
                    fecha_fin=ruta.fecha_fin.isoformat() if ruta.fecha_fin else None
                )
        except Exception as e:
            logger.error(f"Error actualizando bandit: {e}")

        # 6. DETECTAR DESOBEDIENCIA
        resultado_desobediencia = {
            "debe_alertar": False, 
            "mensaje": None, 
            "similitud": 0,
            "desobediencias_consecutivas": 0,
            "es_ruta_similar": False,
            "detalles_analisis": {}
        }
        
        if puntos_gps and len(puntos_gps) > 0:
            try:
                # Importar el servicio actualizado
                from ....services.detector_desobediencia import DetectorDesobedienciaService, convertir_puntos_gps_a_geometria
                detector = DetectorDesobedienciaService(db)
                ruta_real_geometria = convertir_puntos_gps_a_geometria(puntos_gps)
                
                if ruta_real_geometria and ruta.geometria:
                    # IMPORTANTE: Limpiar el polyline si tiene caracteres escapados
                    geometria_limpia = ruta.geometria
                    if '\\x' in geometria_limpia:
                        import codecs
                        try:
                            geometria_limpia = codecs.decode(geometria_limpia.encode(), 'unicode_escape')
                        except:
                            pass
                    
                    resultado_desobediencia = detector.analizar_comportamiento(
                        usuario_id=ruta.usuario_id,
                        ruta_id=ruta_id,
                        ubicacion_id=ubicacion_id or 0,
                        ruta_recomendada=geometria_limpia,
                        ruta_real=ruta_real_geometria,
                        siguio_ruta_android=siguio_ruta_recomendada,
                        porcentaje_android=porcentaje_similitud

                    )
                    
                    logger.info(f"Análisis desobediencia: {resultado_desobediencia}")
                    
                    # Log adicional si viene valor de Android
                    if siguio_ruta_recomendada is not None:
                        logger.info(f"Usando cálculo de Android: siguió ruta = {siguio_ruta_recomendada}")
                else:
                    logger.warning("No se pudo generar geometría real o falta geometría recomendada")
                    
            except Exception as e:
                logger.error(f"Error analizando desobediencia: {e}", exc_info=True)
        else:
            logger.info("Sin datos GPS para análisis de desobediencia")
        
        # 7. RESPUESTA FINAL - IMPORTANTE: Incluir campos que Android espera
        respuesta = {
            "success": True,
            "ruta_id": ruta_id,
            "alerta_desobediencia": resultado_desobediencia.get("debe_alertar", False),
            "mensaje_alerta": resultado_desobediencia.get("mensaje", None),
            "similitud_calculada": resultado_desobediencia.get("similitud", 0),
            "desobediencias_consecutivas": resultado_desobediencia.get("desobediencias_consecutivas", 0),
            "debug_info": {
                "similitud_calculada": resultado_desobediencia.get("similitud", 0),
                "desobediencias_consecutivas": resultado_desobediencia.get("desobediencias_consecutivas", 0),
                "puntos_gps_procesados": len(puntos_gps) if puntos_gps else 0,
                "tiene_geometria_recomendada": bool(ruta.geometria),
                "ubicacion_id": ubicacion_id,
                "es_ruta_similar": resultado_desobediencia.get("es_ruta_similar", False),
                "detalles_analisis": resultado_desobediencia.get("detalles_analisis", {})
            }
        }
        
        # LOG IMPORTANTE para debug
        if resultado_desobediencia.get("debe_alertar", False):
            logger.warning(f"⚠️ ALERTA ACTIVADA para usuario {ruta.usuario_id}: {resultado_desobediencia.get('mensaje')}")
        
        return respuesta

    def cancelar_ruta(self, db: Session, ruta_id: int, fecha_fin: str) -> RutaUsuario:
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

        # Actualizar la ruta con la fecha recibida
        import dateutil.parser
        try:
            # Parsea fechas con timezone automáticamente
            ruta.fecha_fin = dateutil.parser.parse(fecha_fin)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {fecha_fin}")
            
        ruta.estado_ruta_id = estado_cancelada.id
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
                    duracion=ruta.duracion_total,
                    fecha_inicio=ruta.fecha_inicio.isoformat() if ruta.fecha_inicio else None,
                    fecha_fin=ruta.fecha_fin.isoformat() if ruta.fecha_fin else None
                )
                logger.info(f"✅ BANDIT ACTUALIZADO - CANCELADA: Usuario {ruta.usuario_id}, "
                            f"Ruta {ruta_id}, Tipo: {ruta.tipo_ruta_usado}, Ubicación: {ubicacion_id}")
        except Exception as e:
            logger.error(f"❌ Error actualizando bandit en cancelar_ruta {ruta_id}: {e}")

        return ruta

# Instancia para usar en el router
crud_rutas = CRUDRutas()
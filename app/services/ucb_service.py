import math
import random
from sqlalchemy.orm import Session
from datetime import datetime
from .models import BanditSimple, HistorialRutas
import logging
from ..ubicaciones.ubicaciones_historial.models import EstadoUbicacionUsuario
from ..ubicaciones.ubicaciones_historial.rutas.models import RutaUsuario

logger = logging.getLogger(__name__)

class UCBService:
    # 🔹 ACTUALIZADO: Solo las preferencias reales de OpenRouteService
    TIPOS_RUTA = ["fastest", "shortest", "recommended"]
    
    def __init__(self, db: Session):
        self.db = db
    
    def seleccionar_tipo_ruta(self, usuario_id: int, ubicacion_id: int = None) -> str:
        """
        Selecciona entre 'fastest', 'shortest', 'recommended' usando UCB
        Compatible con OpenRouteService preferences
        """
        try:
            bandits = self._get_or_create_user_bandits(usuario_id, ubicacion_id)
            
            # Si es usuario nuevo, rotar entre tipos para explorar
            total_plays = sum(b.total_usos for b in bandits)
            
            if total_plays < len(self.TIPOS_RUTA):
                # Primeras veces: probar cada tipo una vez
                tipos_usados = {b.tipo_ruta for b in bandits if b.total_usos > 0}
                tipos_pendientes = [t for t in self.TIPOS_RUTA if t not in tipos_usados]
                if tipos_pendientes:
                    selected = random.choice(tipos_pendientes)
                    logger.info(f"Usuario {usuario_id} - Explorando: {selected}")
                    return selected
            
            # UCB normal para seleccionar el mejor brazo
            best_arm = None
            best_score = -1
            
            for bandit in bandits:
                if bandit.total_usos == 0:
                    logger.info(f"Usuario {usuario_id} - Explorando brazo sin uso: {bandit.tipo_ruta}")
                    return bandit.tipo_ruta
                
                # Calcular UCB score
                avg_reward = bandit.total_rewards / bandit.total_usos
                confidence = math.sqrt(2 * math.log(total_plays) / bandit.total_usos)
                ucb_score = avg_reward + confidence
                
                logger.info(f"Usuario {usuario_id}, ORS Type {bandit.tipo_ruta}: "
                           f"reward_avg={avg_reward:.3f}, confidence={confidence:.3f}, ucb={ucb_score:.3f}")
                
                if ucb_score > best_score:
                    best_score = ucb_score
                    best_arm = bandit.tipo_ruta
            
            selected_type = best_arm or "fastest"
            logger.info(f"Usuario {usuario_id} - UCB seleccionó: {selected_type}")
            return selected_type
            
        except Exception as e:
            logger.error(f"Error en seleccionar_tipo_ruta: {e}")
            return "fastest"
    
    def actualizar_feedback(self, usuario_id: int, tipo_usado: str, completada: bool, 
                      ubicacion_id: int = None, distancia: float = None, duracion: float = None,
                      fecha_inicio: str = None, fecha_fin: str = None):
        """
        Actualiza el bandit con el resultado de la ruta
        Valida que el tipo_usado sea compatible con ORS
        """
        try:
            # Validar parámetros requeridos
            if ubicacion_id is None:
                logger.warning(f"ubicacion_id es None para usuario {usuario_id}")
                ubicacion_id = 1  # fallback a ubicación por defecto
            
            # Validar que el tipo sea válido
            if tipo_usado not in self.TIPOS_RUTA:
                logger.warning(f"Tipo de ruta inválido: {tipo_usado}. Usando 'fastest' como fallback")
                tipo_usado = "fastest"
            
            # Actualizar el bandit correspondiente para esta ubicación específica
            bandit = self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id,
                BanditSimple.ubicacion_id == ubicacion_id,
                BanditSimple.tipo_ruta == tipo_usado
            ).first()
            
            if bandit:
                bandit.total_usos += 1
                if completada:
                    bandit.total_rewards += 1
                bandit.fecha_actualizacion = datetime.utcnow()
                
                logger.info(f"Bandit ORS actualizado - Usuario {usuario_id}, Ubicación {ubicacion_id}, Tipo {tipo_usado}: "
                           f"usos={bandit.total_usos}, rewards={bandit.total_rewards}, "
                           f"success_rate={bandit.total_rewards/bandit.total_usos:.3f}")
            
            import dateutil.parser
        
            fecha_inicio_parsed = None
            fecha_fin_parsed = None
            
            if fecha_inicio:
                try:
                    fecha_inicio_parsed = dateutil.parser.parse(fecha_inicio)
                except ValueError:
                    logger.warning(f"Formato de fecha_inicio inválido: {fecha_inicio}")
                    fecha_inicio_parsed = datetime.utcnow()
            else:
                fecha_inicio_parsed = datetime.utcnow()
                
            if fecha_fin:
                try:
                    fecha_fin_parsed = dateutil.parser.parse(fecha_fin)
                except ValueError:
                    logger.warning(f"Formato de fecha_fin inválido: {fecha_fin}")
                    fecha_fin_parsed = datetime.utcnow() if completada else None
            else:
                fecha_fin_parsed = datetime.utcnow() if completada else None
            
            # Crear registro en historial
            historial = HistorialRutas(
                usuario_id=usuario_id,
                ubicacion_id=ubicacion_id,
                tipo_seleccionado=tipo_usado,
                distancia=distancia,
                duracion=duracion,
                fecha_inicio=fecha_inicio_parsed,
                fecha_fin=fecha_fin_parsed
            )
            
            self.db.add(historial)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error en actualizar_feedback: {e}")
            self.db.rollback()
            raise e
    
    def obtener_estadisticas(self, usuario_id: int, ubicacion_id: int = None):
        """
        Devuelve estadísticas del bandit y resumen de movilidad para un usuario y ubicación específica
        """
        try:
            # 🔹 Bandits (igual)
            query_bandits = self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id
            )
            if ubicacion_id is not None:
                query_bandits = query_bandits.filter(BanditSimple.ubicacion_id == ubicacion_id)
            bandits = query_bandits.all()
            
            total_plays = sum(b.total_usos for b in bandits)
            
            bandits_stats = []
            for bandit in bandits:
                success_rate = (bandit.total_rewards / bandit.total_usos) if bandit.total_usos > 0 else 0
                ucb_score = 0.0
                if bandit.total_usos > 0 and total_plays > 0:
                    confidence = math.sqrt(2 * math.log(total_plays) / bandit.total_usos)
                    ucb_score = success_rate + confidence
                bandits_stats.append({
                    "tipo_ruta": bandit.tipo_ruta,
                    "total_usos": bandit.total_usos,
                    "total_rewards": bandit.total_rewards,
                    "success_rate": round(success_rate, 3),
                    "ucb_score": round(ucb_score, 3),
                    "fecha_creacion": bandit.fecha_creacion,
                    "fecha_actualizacion": bandit.fecha_actualizacion
                })
            
            bandits_stats.sort(key=lambda x: x["ucb_score"], reverse=True)

            # 🔹 Query usando RutaUsuario (no HistorialRutas) para tener estado_ruta_id
            query_rutas = self.db.query(RutaUsuario).filter(
                RutaUsuario.usuario_id == usuario_id
            )
            if ubicacion_id is not None:
                # Necesitas unir con EstadoUbicacionUsuario para filtrar por ubicacion_id
                query_rutas = query_rutas.join(EstadoUbicacionUsuario).filter(
                    EstadoUbicacionUsuario.ubicacion_id == ubicacion_id
                )
            
            rutas = query_rutas.all()

            total_rutas = len(rutas)
            # 🔹 CORRECCIÓN: Usar estado_ruta_id para determinar completadas vs canceladas
            rutas_completadas = sum(1 for ruta in rutas if ruta.estado_ruta_id == 2)  # 2 = FINALIZADA
            rutas_canceladas = sum(1 for ruta in rutas if ruta.estado_ruta_id == 3)   # 3 = CANCELADA

            # Tiempo promedio solo para rutas FINALIZADAS (no canceladas)
            tiempo_por_tipo = {}
            for ruta in rutas:
                if ruta.estado_ruta_id == 2:  # Solo rutas FINALIZADAS
                    # Calcular duración real en segundos
                    duracion_real = (ruta.fecha_fin - ruta.fecha_inicio).total_seconds()
                    
                    if ruta.tipo_ruta_usado not in tiempo_por_tipo:
                        tiempo_por_tipo[ruta.tipo_ruta_usado] = []
                    tiempo_por_tipo[ruta.tipo_ruta_usado].append(duracion_real)
            
            tiempo_promedio_por_tipo = {
                tipo: round(sum(lista) / len(lista), 2) if lista else 0
                for tipo, lista in tiempo_por_tipo.items()
            }

            stats = {
                "usuario_id": usuario_id,
                "ubicacion_id": ubicacion_id,
                "bandits": bandits_stats,
                "total_rutas_generadas": total_rutas,
                "rutas_completadas": rutas_completadas,
                "rutas_canceladas": rutas_canceladas,
                "tiempo_promedio_por_tipo": tiempo_promedio_por_tipo
            }

            return stats

        except Exception as e:
            logger.error(f"Error en obtener_estadisticas: {e}")
            raise e
    
    def resetear_usuario(self, usuario_id: int, ubicacion_id: int = None):
        """
        Resetea todo el aprendizaje de un usuario
        Opcionalmente solo para una ubicación específica
        """
        try:
            query = self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id
            )
            
            # Filtrar por ubicación si se especifica
            if ubicacion_id is not None:
                query = query.filter(BanditSimple.ubicacion_id == ubicacion_id)
            
            deleted_bandits = query.delete()
            
            history_query = self.db.query(HistorialRutas).filter(
                HistorialRutas.usuario_id == usuario_id
            )
            
            if ubicacion_id is not None:
                history_query = history_query.filter(HistorialRutas.ubicacion_id == ubicacion_id)
            
            deleted_history = history_query.delete()
            
            self.db.commit()
            logger.info(f"Bandit reseteado para usuario {usuario_id}, ubicación {ubicacion_id}: "
                       f"{deleted_bandits} bandits, {deleted_history} registros de historial eliminados")
            
        except Exception as e:
            logger.error(f"Error en resetear_usuario: {e}")
            self.db.rollback()
            raise e
    
    def _get_or_create_user_bandits(self, usuario_id: int, ubicacion_id: int = None):
        """
        Crea bandits para una ubicación específica del usuario
        Cada combinación usuario+ubicación tiene sus propios bandits
        """
        if ubicacion_id is None:
            logger.warning(f"ubicacion_id es None para usuario {usuario_id}")
            ubicacion_id = 1  # fallback a ubicación por defecto
        
        existing = self.db.query(BanditSimple).filter(
            BanditSimple.usuario_id == usuario_id,
            BanditSimple.ubicacion_id == ubicacion_id
        ).all()
        
        if len(existing) == len(self.TIPOS_RUTA):
            return existing
        
        # Si no existen o están incompletos, crearlos para esta ubicación
        tipos_existentes = {b.tipo_ruta for b in existing}
        tipos_faltantes = set(self.TIPOS_RUTA) - tipos_existentes
        
        nuevos_bandits = []
        for tipo in tipos_faltantes:
            bandit = BanditSimple(
                usuario_id=usuario_id, 
                ubicacion_id=ubicacion_id,
                tipo_ruta=tipo,
                total_usos=0,
                total_rewards=0
            )
            nuevos_bandits.append(bandit)
            self.db.add(bandit)
        
        if nuevos_bandits:
            self.db.commit()
            logger.info(f"Creados {len(nuevos_bandits)} bandits ORS para usuario {usuario_id}, ubicación {ubicacion_id}: "
                       f"{[b.tipo_ruta for b in nuevos_bandits]}")
        
        # Devolver todos los bandits del usuario para esta ubicación
        return self.db.query(BanditSimple).filter(
            BanditSimple.usuario_id == usuario_id,
            BanditSimple.ubicacion_id == ubicacion_id
        ).all()
    
    def get_ors_preference_mapping(self):
        """
        Devuelve el mapeo directo para usar con OpenRouteService API
        """
        return {
            "fastest": "fastest",
            "shortest": "shortest",
            "recommended": "recommended"
        }
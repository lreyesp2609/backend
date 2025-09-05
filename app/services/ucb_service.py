# app/ml/ucb_service.py
import math
import random
from sqlalchemy.orm import Session
from datetime import datetime
from .models import BanditSimple, HistorialRutas
import logging

logger = logging.getLogger(__name__)

class UCBService:
    # 🔹 CAMBIO: Más opciones de rutas
    TIPOS_RUTA = ["fastest", "shortest", "scenic", "balanced"]
    
    def __init__(self, db: Session):
        self.db = db
    
    def seleccionar_tipo_ruta(self, usuario_id: int) -> str:
        """
        Selecciona entre 'fastest', 'shortest', 'scenic', 'balanced' usando UCB
        Esto genera RUTAS ALTERNAS automáticamente
        """
        try:
            bandits = self._get_or_create_user_bandits(usuario_id)
            
            # Si es usuario nuevo, rotar entre tipos para explorar
            total_plays = sum(b.total_usos for b in bandits)
            
            if total_plays < len(self.TIPOS_RUTA):
                # Primeras veces: probar cada tipo una vez
                tipos_usados = {b.tipo_ruta for b in bandits if b.total_usos > 0}
                tipos_pendientes = [t for t in self.TIPOS_RUTA if t not in tipos_usados]
                if tipos_pendientes:
                    return random.choice(tipos_pendientes)
            
            # UCB normal para seleccionar el mejor brazo
            best_arm = None
            best_score = -1
            
            for bandit in bandits:
                if bandit.total_usos == 0:
                    return bandit.tipo_ruta  # Explorar primero
                
                # Calcular UCB score
                avg_reward = bandit.total_rewards / bandit.total_usos
                confidence = math.sqrt(2 * math.log(total_plays) / bandit.total_usos)
                ucb_score = avg_reward + confidence
                
                logger.info(f"Usuario {usuario_id}, Tipo {bandit.tipo_ruta}: "
                           f"reward_avg={avg_reward:.3f}, confidence={confidence:.3f}, ucb={ucb_score:.3f}")
                
                if ucb_score > best_score:
                    best_score = ucb_score
                    best_arm = bandit.tipo_ruta
            
            return best_arm or "fastest"  # fallback
            
        except Exception as e:
            logger.error(f"Error en seleccionar_tipo_ruta: {e}")
            return "fastest"  # fallback seguro
    
    def actualizar_feedback(self, usuario_id: int, tipo_usado: str, completada: bool, 
                          distancia: float = None, duracion: float = None):
        """
        Actualiza el bandit con el resultado de la ruta
        """
        try:
            # Actualizar el bandit correspondiente
            bandit = self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id,
                BanditSimple.tipo_ruta == tipo_usado
            ).first()
            
            if bandit:
                bandit.total_usos += 1
                if completada:
                    bandit.total_rewards += 1
                bandit.fecha_actualizacion = datetime.utcnow()
                
                logger.info(f"Bandit actualizado - Usuario {usuario_id}, Tipo {tipo_usado}: "
                           f"usos={bandit.total_usos}, rewards={bandit.total_rewards}")
            
            # Crear registro en historial
            historial = HistorialRutas(
                usuario_id=usuario_id,
                tipo_seleccionado=tipo_usado,
                completada=1 if completada else 0,
                distancia=distancia,
                duracion=duracion,
                fecha_inicio=datetime.utcnow(),
                fecha_fin=datetime.utcnow() if completada else None
            )
            
            self.db.add(historial)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error en actualizar_feedback: {e}")
            self.db.rollback()
            raise e
    
    def obtener_estadisticas(self, usuario_id: int):
        """
        Devuelve estadísticas del bandit para un usuario
        """
        try:
            bandits = self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id
            ).all()
            
            stats = {
                "usuario_id": usuario_id,
                "bandits": [],
                "total_rutas_generadas": len(bandits)
            }
            
            total_plays = sum(b.total_usos for b in bandits)
            
            for bandit in bandits:
                success_rate = (bandit.total_rewards / bandit.total_usos) if bandit.total_usos > 0 else 0
                
                bandit_stats = {
                    "tipo_ruta": bandit.tipo_ruta,
                    "total_usos": bandit.total_usos,
                    "total_rewards": bandit.total_rewards,
                    "success_rate": round(success_rate, 3),
                    "fecha_creacion": bandit.fecha_creacion,
                    "fecha_actualizacion": bandit.fecha_actualizacion
                }
                
                # Agregar UCB score si tiene usos
                if bandit.total_usos > 0 and total_plays > 0:
                    confidence = math.sqrt(2 * math.log(total_plays) / bandit.total_usos)
                    ucb_score = success_rate + confidence
                    bandit_stats["ucb_score"] = round(ucb_score, 3)
                
                stats["bandits"].append(bandit_stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error en obtener_estadisticas: {e}")
            raise e
    
    def resetear_usuario(self, usuario_id: int):
        """
        Resetea todo el aprendizaje de un usuario
        """
        try:
            # Eliminar bandits existentes
            self.db.query(BanditSimple).filter(
                BanditSimple.usuario_id == usuario_id
            ).delete()
            
            # Opcional: también eliminar historial
            self.db.query(HistorialRutas).filter(
                HistorialRutas.usuario_id == usuario_id
            ).delete()
            
            self.db.commit()
            logger.info(f"Bandit reseteado para usuario {usuario_id}")
            
        except Exception as e:
            logger.error(f"Error en resetear_usuario: {e}")
            self.db.rollback()
            raise e
    
    def _get_or_create_user_bandits(self, usuario_id: int):
        """
        🔹 CAMBIO: Crea bandits para TODOS los tipos de ruta
        """
        existing = self.db.query(BanditSimple).filter(
            BanditSimple.usuario_id == usuario_id
        ).all()
        
        if len(existing) == len(self.TIPOS_RUTA):
            return existing
        
        # Si no existen o están incompletos, crearlos
        tipos_existentes = {b.tipo_ruta for b in existing}
        tipos_faltantes = set(self.TIPOS_RUTA) - tipos_existentes
        
        nuevos_bandits = []
        for tipo in tipos_faltantes:
            bandit = BanditSimple(
                usuario_id=usuario_id, 
                tipo_ruta=tipo,
                total_usos=0,
                total_rewards=0
            )
            nuevos_bandits.append(bandit)
            self.db.add(bandit)
        
        if nuevos_bandits:
            self.db.commit()
            logger.info(f"Creados {len(nuevos_bandits)} bandits para usuario {usuario_id}")
        
        # Devolver todos los bandits del usuario
        return self.db.query(BanditSimple).filter(
            BanditSimple.usuario_id == usuario_id
        ).all()
import firebase_admin
from firebase_admin import credentials, messaging
from typing import List, Optional, Dict
import os
import logging
import time

logger = logging.getLogger(__name__)

class FCMService:
    """
    Servicio singleton para enviar notificaciones push mediante Firebase Cloud Messaging.
    Se inicializa automáticamente al importarse.
    """
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FCMService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not FCMService._initialized:
            self._initialize_firebase()
            FCMService._initialized = True
    
    def _initialize_firebase(self):
        """Inicializa Firebase Admin SDK una sola vez"""
        try:
            # Ruta al archivo de credenciales (raíz del proyecto)
            # app/services/fcm_service.py -> ../../firebase-credentials.json
            current_dir = os.path.dirname(__file__)
            cred_path = os.path.abspath(os.path.join(current_dir, "..", "..", "firebase-credentials.json"))
            
            if not os.path.exists(cred_path):
                logger.warning("⚠️ Archivo firebase-credentials.json no encontrado")
                logger.warning(f"   Buscado en: {cred_path}")
                logger.warning("   Las notificaciones FCM no funcionarán")
                return
            
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            logger.info("🔥 Firebase Admin SDK inicializado correctamente")
            
        except ValueError as e:
            # Ya está inicializado (puede pasar en hot-reload)
            logger.info("ℹ️ Firebase ya estaba inicializado")
        except Exception as e:
            logger.error(f"❌ Error inicializando Firebase: {e}")
    
    async def enviar_notificacion_mensaje(
        self,
        token: str,
        grupo_id: int,
        grupo_nombre: str,
        remitente_nombre: str,
        mensaje: str,
        timestamp: Optional[int] = None
    ) -> bool:
        """
        ✅ NUEVO: Envía notificación de MENSAJE con todos los datos necesarios
        para acumulación
        
        Args:
            token: Token FCM del dispositivo
            grupo_id: ID del grupo
            grupo_nombre: Nombre del grupo
            remitente_nombre: Nombre de quien envió el mensaje
            mensaje: Contenido del mensaje
            timestamp: Timestamp del mensaje (opcional)
        
        Returns:
            bool: True si se envió correctamente
        
        Example:
            await fcm_service.enviar_notificacion_mensaje(
                token="dispositivo_token_123",
                grupo_id=123,
                grupo_nombre="Familia",
                remitente_nombre="Juan",
                mensaje="Hola, ¿cómo están?",
                timestamp=1730000000000
            )
        """
        try:
            # ✅ DATOS COMPLETOS para acumulación
            notification_data = {
                "type": "nuevo_mensaje",
                "grupo_id": str(grupo_id),
                "grupo_nombre": grupo_nombre,
                "remitente_nombre": remitente_nombre,  # ✅ CRÍTICO
                "cuerpo": mensaje,
                "timestamp": str(timestamp or int(time.time() * 1000))
            }
            
            # Título para la notificación
            titulo = f"💬 {grupo_nombre}"
            
            # Construir mensaje FCM
            message = messaging.Message(
                notification=messaging.Notification(
                    title=titulo,
                    body=f"{remitente_nombre}: {mensaje[:50]}..."  # Preview
                ),
                data=notification_data,
                token=token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='recuerdago_mensajes',  # ✅ Debe coincidir con Android
                        click_action='FLUTTER_NOTIFICATION_CLICK'
                    )
                )
            )
            
            # Enviar
            response = messaging.send(message)
            logger.info(f"✅ FCM mensaje enviado: {response}")
            logger.info(f"   Grupo: {grupo_nombre} | Remitente: {remitente_nombre}")
            return True
            
        except messaging.UnregisteredError:
            logger.warning(f"⚠️ Token FCM no registrado: {token[:20]}...")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error enviando FCM mensaje: {e}")
            return False
    
    async def enviar_notificacion(
        self,
        token: str,
        titulo: str,
        cuerpo: str,
        data: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        ⚠️ DEPRECATED: Usar enviar_notificacion_mensaje() para mensajes
        
        Envía una notificación FCM genérica a un dispositivo específico
        """
        try:
            notification_data = {}
            if data:
                notification_data = {k: str(v) for k, v in data.items()}
            
            message = messaging.Message(
                notification=messaging.Notification(
                    title=titulo,
                    body=cuerpo[:100]
                ),
                data=notification_data,
                token=token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='recuerdago_mensajes',
                        click_action='FLUTTER_NOTIFICATION_CLICK'
                    )
                )
            )
            
            response = messaging.send(message)
            logger.info(f"✅ FCM enviado correctamente: {response}")
            return True
            
        except messaging.UnregisteredError:
            logger.warning(f"⚠️ Token FCM no registrado o expirado: {token[:20]}...")
            return False
            
        except firebase_admin.exceptions.InvalidArgumentError as e:
            logger.error(f"❌ Argumento inválido en FCM: {e}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error enviando FCM: {e}")
            return False
    
    async def enviar_mensaje_a_grupo(
        self,
        tokens: List[str],
        grupo_id: int,
        grupo_nombre: str,
        remitente_nombre: str,
        mensaje: str,
        timestamp: Optional[int] = None
    ) -> Dict[str, any]:
        """
        ✅ FALLBACK: Enviar uno por uno si send_multicast no está disponible
        """
        if not tokens:
            logger.warning("⚠️ No hay tokens para enviar")
            return {"exitosos": 0, "fallidos": 0, "tokens_invalidos": []}
        
        try:
            notification_data = {
                "type": "nuevo_mensaje",
                "grupo_id": str(grupo_id),
                "grupo_nombre": grupo_nombre,
                "remitente_nombre": remitente_nombre,
                "cuerpo": mensaje,
                "timestamp": str(timestamp or int(time.time() * 1000)),
                "titulo": f"💬 {grupo_nombre}"
            }
            
            # ✅ INTENTAR send_multicast primero
            try:
                message = messaging.MulticastMessage(
                    data=notification_data,
                    tokens=tokens,
                    android=messaging.AndroidConfig(priority='high')
                )
                
                response = messaging.send_multicast(message)
                
                tokens_invalidos = []
                if response.failure_count > 0:
                    for idx, resp in enumerate(response.responses):
                        if not resp.success:
                            tokens_invalidos.append(tokens[idx])
                            logger.warning(f"⚠️ Token inválido: {tokens[idx][:20]}...")
                
                logger.info(f"📊 FCM grupo: {response.success_count} exitosos, {response.failure_count} fallidos")
                
                return {
                    "exitosos": response.success_count,
                    "fallidos": response.failure_count,
                    "tokens_invalidos": tokens_invalidos
                }
            
            except AttributeError:
                # ⚠️ FALLBACK: send_multicast no disponible, enviar uno por uno
                logger.warning("⚠️ send_multicast no disponible, usando send() individual")
                
                exitosos = 0
                fallidos = 0
                tokens_invalidos = []
                
                for token in tokens:
                    try:
                        message = messaging.Message(
                            data=notification_data,
                            token=token,
                            android=messaging.AndroidConfig(priority='high')
                        )
                        
                        response = messaging.send(message)
                        exitosos += 1
                        logger.info(f"✅ FCM enviado a token: {token[:20]}...")
                        
                    except messaging.UnregisteredError:
                        fallidos += 1
                        tokens_invalidos.append(token)
                        logger.warning(f"⚠️ Token no registrado: {token[:20]}...")
                    
                    except Exception as e:
                        fallidos += 1
                        logger.error(f"❌ Error enviando a token {token[:20]}...: {e}")
                
                logger.info(f"📊 FCM individual: {exitosos} exitosos, {fallidos} fallidos")
                
                return {
                    "exitosos": exitosos,
                    "fallidos": fallidos,
                    "tokens_invalidos": tokens_invalidos
                }
                
        except Exception as e:
            logger.error(f"❌ Error en envío: {e}")
            return {
                "exitosos": 0,
                "fallidos": len(tokens),
                "tokens_invalidos": []  # ❌ NO marcar como inválidos si fue error del SDK
            }
    
    async def enviar_a_multiples(
        self,
        tokens: List[str],
        titulo: str,
        cuerpo: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, any]:
        """
        ⚠️ DEPRECATED: Usar enviar_mensaje_a_grupo() para mensajes
        
        Envía notificación genérica a múltiples dispositivos
        """
        if not tokens:
            logger.warning("⚠️ No se proporcionaron tokens")
            return {"exitosos": 0, "fallidos": 0, "tokens_invalidos": []}
        
        try:
            notification_data = {}
            if data:
                notification_data = {k: str(v) for k, v in data.items()}
            
            message = messaging.MulticastMessage(
                notification=messaging.Notification(
                    title=titulo,
                    body=cuerpo[:100]
                ),
                data=notification_data,
                tokens=tokens,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        channel_id='recuerdago_mensajes'
                    )
                )
            )
            
            response = messaging.send_multicast(message)
            
            tokens_invalidos = []
            if response.failure_count > 0:
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        tokens_invalidos.append(tokens[idx])
            
            logger.info(f"📊 FCM multicast: {response.success_count} exitosos, {response.failure_count} fallidos")
            
            return {
                "exitosos": response.success_count,
                "fallidos": response.failure_count,
                "tokens_invalidos": tokens_invalidos
            }
            
        except Exception as e:
            logger.error(f"❌ Error en envío multicast: {e}")
            return {
                "exitosos": 0,
                "fallidos": len(tokens),
                "tokens_invalidos": tokens
            }
    
    async def verificar_token_valido(self, token: str) -> bool:
        """
        Verifica si un token FCM es válido
        """
        try:
            message = messaging.Message(
                data={"tipo": "validacion"},
                token=token,
                android=messaging.AndroidConfig(priority='normal')
            )
            
            messaging.send(message, dry_run=True)
            return True
            
        except messaging.UnregisteredError:
            return False
        except Exception as e:
            logger.error(f"❌ Error verificando token: {e}")
            return False


# ✅ Instancia única global (singleton)
fcm_service = FCMService()
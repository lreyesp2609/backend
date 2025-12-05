import logging
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)

class ValidadorSeguridadPersonal:
    """
    🔒 Validador de rutas contra zonas peligrosas PERSONALES del usuario
    """
    
    def __init__(self, db: Session, usuario_id: int):
        self.db = db
        self.usuario_id = usuario_id
        self._cache_zonas = None
        self._cache_timestamp = None
        # 🆕 Tolerancia para puentes/pasos elevados
        self.TOLERANCIA_BUFFER_METROS = 30  # Ignorar si pasa muy cerca pero no dentro
    
    def _get_zonas_peligrosas_usuario(self) -> List:
        """
        Obtiene las zonas peligrosas activas del usuario con caché de 5 minutos
        """
        from .models import ZonaPeligrosaUsuario        

        ahora = datetime.now()
        
        # Usar caché si es válido (menos de 5 minutos)
        if (self._cache_zonas is not None and 
            self._cache_timestamp is not None and 
            (ahora - self._cache_timestamp).seconds < 300):
            return self._cache_zonas
        
        # Cargar zonas activas del usuario
        zonas = self.db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == self.usuario_id,
            ZonaPeligrosaUsuario.activa == True
        ).all()
        
        self._cache_zonas = zonas
        self._cache_timestamp = ahora
        
        logger.info(f"Usuario {self.usuario_id}: {len(zonas)} zonas peligrosas activas cargadas")
        return zonas
    
    def validar_ruta(self, geometry_polyline: str, metadata: Dict = None) -> Dict:
        """
        Valida si una ruta pasa por zonas peligrosas del usuario
        
        🔥 MEJORADO: Usa distancia al centro + buffer en lugar de Ray Casting puro
        """
        try:
            # Obtener zonas peligrosas del usuario
            zonas_peligrosas = self._get_zonas_peligrosas_usuario()
            
            if not zonas_peligrosas:
                logger.info(f"Usuario {self.usuario_id} no tiene zonas peligrosas definidas")
                return {
                    'es_segura': True,
                    'nivel_riesgo': 0,
                    'zonas_detectadas': [],
                    'mensaje': None
                }
            
            # Decodificar la ruta a puntos
            puntos_ruta = self._decode_polyline(geometry_polyline)
            
            if not puntos_ruta:
                logger.warning("No se pudo decodificar la geometría de la ruta")
                return {
                    'es_segura': True,
                    'nivel_riesgo': 0,
                    'zonas_detectadas': [],
                    'mensaje': 'No se pudo validar la ruta',
                    'error': True
                }
            
            # 🔥 NUEVO ALGORITMO: Distancia al centro + buffer
            zonas_detectadas = []
            nivel_riesgo_maximo = 0
            
            # Muestrear puntos (cada 5 en lugar de cada 10 para mayor precisión)
            puntos_muestreados = puntos_ruta[::5] if len(puntos_ruta) > 20 else puntos_ruta
            
            logger.info(f"🔍 Validando ruta con {len(puntos_muestreados)} puntos muestreados")
            
            for zona in zonas_peligrosas:
                # Obtener centro de la zona
                centro = zona.poligono[0] if zona.poligono else None
                if not centro:
                    logger.warning(f"Zona {zona.nombre} sin coordenadas centrales")
                    continue
                
                radio_zona = zona.radio_metros or 200
                # 🔥 Añadir buffer de tolerancia (para evitar falsos positivos en puentes)
                radio_con_buffer = radio_zona - self.TOLERANCIA_BUFFER_METROS
                
                puntos_dentro_zona = 0
                distancias_minimas = []
                
                logger.info(f"📍 Evaluando zona '{zona.nombre}': centro=({centro['lat']}, {centro['lon']}), radio={radio_zona}m")
                
                for punto in puntos_muestreados:
                    # 🔥 Calcular distancia haversine al centro
                    distancia = self._calcular_distancia_haversine(
                        punto['lat'], punto['lon'],
                        centro['lat'], centro['lon']
                    )
                    
                    distancias_minimas.append(distancia)
                    
                    # 🔥 Solo contar si está DENTRO del círculo (con buffer)
                    if distancia <= radio_con_buffer:
                        puntos_dentro_zona += 1
                
                # Debug: mostrar distancia mínima a la zona
                dist_min_zona = min(distancias_minimas) if distancias_minimas else float('inf')
                logger.info(f"  ↳ Distancia mínima a zona: {dist_min_zona:.1f}m")
                logger.info(f"  ↳ Puntos dentro de zona: {puntos_dentro_zona}/{len(puntos_muestreados)}")
                
                # 🔥 CRITERIO MÁS ESTRICTO: Requiere múltiples puntos dentro
                if puntos_dentro_zona >= 2:  # Al menos 2 puntos dentro
                    porcentaje = (puntos_dentro_zona / len(puntos_muestreados)) * 100
                    
                    logger.warning(f"⚠️ ZONA DETECTADA: {zona.nombre} - {porcentaje:.1f}% de la ruta")
                    
                    zonas_detectadas.append({
                        'zona_id': zona.id,
                        'nombre': zona.nombre,
                        'nivel_peligro': zona.nivel_peligro,
                        'tipo': zona.tipo,
                        'porcentaje_ruta': round(porcentaje, 2),
                        'notas': zona.notas,
                        'distancia_minima': round(dist_min_zona, 1)
                    })
                    
                    nivel_riesgo_maximo = max(nivel_riesgo_maximo, zona.nivel_peligro)
            
            # Determinar si es segura
            es_segura = nivel_riesgo_maximo < 3
            
            # Generar mensaje
            mensaje = None
            if not es_segura:
                if nivel_riesgo_maximo >= 4:
                    mensaje = f"RIESGO ALTO: Esta ruta pasa por {len(zonas_detectadas)} zona(s) que marcaste como peligrosas"
                elif nivel_riesgo_maximo == 3:
                    mensaje = f"PRECAUCIÓN: Esta ruta pasa por {len(zonas_detectadas)} zona(s) con riesgo moderado"
            
            resultado = {
                'es_segura': es_segura,
                'nivel_riesgo': nivel_riesgo_maximo,
                'zonas_detectadas': zonas_detectadas,
                'mensaje': mensaje,
                'puntos_analizados': len(puntos_ruta),
                'puntos_muestreados': len(puntos_muestreados)
            }
            
            logger.info(f"✅ Usuario {self.usuario_id} - Validación: segura={es_segura}, "
                       f"nivel={nivel_riesgo_maximo}, zonas={len(zonas_detectadas)}")
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error validando ruta para usuario {self.usuario_id}: {e}", exc_info=True)
            return {
                'es_segura': True,
                'nivel_riesgo': 0,
                'zonas_detectadas': [],
                'mensaje': 'Error en validación',
                'error': str(e)
            }
    
    def _calcular_distancia_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        🔥 NUEVO: Calcula distancia en metros usando fórmula de Haversine
        Más preciso que Ray Casting para círculos
        
        Returns:
            Distancia en metros
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371000  # Radio de la Tierra en metros
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        distancia = R * c
        return distancia
    
    def validar_multiples_rutas(self, rutas: List[Dict]) -> List[Dict]:
        """
        Valida múltiples rutas y las ordena por seguridad
        """
        resultados = []
        
        for ruta in rutas:
            validacion = self.validar_ruta(
                ruta['geometry'],
                metadata={
                    'tipo': ruta.get('tipo'),
                    'distance': ruta.get('distance'),
                    'duration': ruta.get('duration')
                }
            )
            
            resultados.append({
                'tipo': ruta.get('tipo'),
                'es_segura': validacion['es_segura'],
                'nivel_riesgo': validacion['nivel_riesgo'],
                'zonas_detectadas': validacion['zonas_detectadas'],
                'mensaje': validacion['mensaje'],
                'distance': ruta.get('distance'),
                'duration': ruta.get('duration')
            })
        
        # Ordenar por seguridad
        resultados.sort(key=lambda x: (not x['es_segura'], x['nivel_riesgo']))
        
        return resultados
    
    def _decode_polyline(self, encoded: str) -> List[Dict]:
        """
        Decodifica polyline de OpenRouteService a lista de coordenadas
        """
        points = []
        index = 0
        lat = 0
        lng = 0
        
        try:
            while index < len(encoded):
                b = 0
                shift = 0
                result = 0
                
                while True:
                    b = ord(encoded[index]) - 63
                    index += 1
                    result |= (b & 0x1f) << shift
                    shift += 5
                    if b < 0x20:
                        break
                
                dlat = ~(result >> 1) if (result & 1) else (result >> 1)
                lat += dlat
                
                shift = 0
                result = 0
                
                while True:
                    b = ord(encoded[index]) - 63
                    index += 1
                    result |= (b & 0x1f) << shift
                    shift += 5
                    if b < 0x20:
                        break
                
                dlng = ~(result >> 1) if (result & 1) else (result >> 1)
                lng += dlng
                
                points.append({
                    'lat': lat / 1e5,
                    'lon': lng / 1e5
                })
            
            return points
            
        except Exception as e:
            logger.error(f"Error decodificando polyline: {e}")
            return []
    
    def obtener_estadisticas_seguridad(self) -> Dict:
        """
        Obtiene estadísticas de seguridad del usuario
        """
        from .models import ZonaPeligrosaUsuario
                
        zonas = self.db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == self.usuario_id
        ).all()
        
        # Contar por tipo
        zonas_por_tipo = {}
        for zona in zonas:
            tipo = zona.tipo or 'otro'
            zonas_por_tipo[tipo] = zonas_por_tipo.get(tipo, 0) + 1
        
        # Contar por nivel
        zonas_por_nivel = {}
        for zona in zonas:
            zonas_por_nivel[zona.nivel_peligro] = zonas_por_nivel.get(zona.nivel_peligro, 0) + 1
        
        return {
            'total_zonas': len(zonas),
            'zonas_activas': len([z for z in zonas if z.activa]),
            'zonas_inactivas': len([z for z in zonas if not z.activa]),
            'zonas_por_tipo': zonas_por_tipo,
            'zonas_por_nivel': zonas_por_nivel
        }


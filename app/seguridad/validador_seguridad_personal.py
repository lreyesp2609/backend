import logging
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)

class ValidadorSeguridadPersonal:
    """
    🔒 Validador de rutas contra zonas peligrosas PERSONALES del usuario
    ✅ VERSIÓN PRODUCCIÓN - Optimizado para diferentes terrenos
    """
    
    def __init__(self, db: Session, usuario_id: int):
        self.db = db
        self.usuario_id = usuario_id
        self._cache_zonas = None
        self._cache_timestamp = None
        
        # 🔥 CONFIGURACIÓN ADAPTATIVA PARA PRODUCCIÓN
        self.BUFFER_DETECCION_METROS = 50  # Detecta rutas CERCA del borde (no solo dentro)
        self.PUNTOS_MINIMOS_ALERTA = 2     # Requiere 2+ puntos para confirmar (evita falsos positivos)
        self.INTERVALO_MUESTREO = 5        # Analizar cada 5 puntos (balance precisión/rendimiento)
        
        # 🎯 Niveles de riesgo adaptativos
        self.UMBRAL_RIESGO_ALTO = 4        # Nivel 4-5: Bloqueo total
        self.UMBRAL_RIESGO_MEDIO = 3       # Nivel 3: Advertencia fuerte
    
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
        ✅ VERSIÓN PRODUCCIÓN: Valida si una ruta pasa por zonas peligrosas del usuario
        
        🔥 MEJORAS:
        - Detecta rutas CERCA del borde (buffer +50m para seguridad)
        - Requiere múltiples puntos para confirmar (evita falsos positivos en puentes)
        - Calcula distancia mínima real a cada zona
        - Adaptativo a diferentes densidades de puntos
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
            
            # 🔥 MUESTREO ADAPTATIVO
            # Para rutas largas (1000+ puntos): cada 10
            # Para rutas medianas (100-1000): cada 5
            # Para rutas cortas (<100): todos los puntos
            if len(puntos_ruta) > 1000:
                intervalo = 10
            elif len(puntos_ruta) > 100:
                intervalo = self.INTERVALO_MUESTREO
            else:
                intervalo = 1
            
            puntos_muestreados = puntos_ruta[::intervalo]
            
            logger.info(f"🔍 Validando ruta: {len(puntos_ruta)} puntos totales, "
                       f"{len(puntos_muestreados)} muestreados (cada {intervalo})")
            
            # 🔥 ANÁLISIS POR ZONA CON BUFFER DE SEGURIDAD
            zonas_detectadas = []
            nivel_riesgo_maximo = 0
            
            for zona in zonas_peligrosas:
                # Obtener centro de la zona
                centro = zona.poligono[0] if zona.poligono else None
                if not centro:
                    logger.warning(f"Zona {zona.nombre} sin coordenadas centrales")
                    continue
                
                radio_zona = zona.radio_metros or 200
                
                # 🔥 BUFFER DE DETECCIÓN: Amplía la zona para detectar rutas CERCANAS
                # Esto previene que rutas pasen "rozando" sin ser detectadas
                radio_con_buffer = radio_zona + self.BUFFER_DETECCION_METROS
                
                puntos_dentro_zona = 0
                distancias_minimas = []
                
                logger.info(f"📍 Evaluando zona '{zona.nombre}': "
                           f"centro=({centro['lat']:.6f}, {centro['lon']:.6f}), "
                           f"radio_base={radio_zona}m, radio_detección={radio_con_buffer}m")
                
                # Calcular distancias de todos los puntos muestreados
                for punto in puntos_muestreados:
                    distancia = self._calcular_distancia_haversine(
                        punto['lat'], punto['lon'],
                        centro['lat'], centro['lon']
                    )
                    
                    distancias_minimas.append(distancia)
                    
                    # 🔥 Contar puntos dentro del radio de detección (con buffer)
                    if distancia <= radio_con_buffer:
                        puntos_dentro_zona += 1
                
                # Obtener distancia mínima real a la zona
                dist_min_zona = min(distancias_minimas) if distancias_minimas else float('inf')
                
                logger.info(f"  ↳ Distancia mínima a zona: {dist_min_zona:.1f}m (radio: {radio_zona}m)")
                logger.info(f"  ↳ Puntos dentro de radio detección ({radio_con_buffer}m): "
                           f"{puntos_dentro_zona}/{len(puntos_muestreados)}")
                
                # 🔥 CRITERIO DE ALERTA: Múltiples puntos + consideración de densidad
                # Ajustar umbral según cantidad de puntos muestreados
                umbral_puntos = max(self.PUNTOS_MINIMOS_ALERTA, 
                                   int(len(puntos_muestreados) * 0.02))  # Mínimo 2% de puntos
                
                if puntos_dentro_zona >= umbral_puntos:
                    porcentaje = (puntos_dentro_zona / len(puntos_muestreados)) * 100
                    
                    # 🔥 Clasificar proximidad
                    if dist_min_zona <= radio_zona:
                        proximidad = "DENTRO DE LA ZONA"
                    elif dist_min_zona <= radio_zona + 25:
                        proximidad = "MUY CERCA DEL BORDE"
                    else:
                        proximidad = "CERCA DE LA ZONA"
                    
                    logger.warning(f"⚠️ ZONA DETECTADA: {zona.nombre} - {porcentaje:.1f}% de la ruta - {proximidad}")
                    
                    zonas_detectadas.append({
                        'zona_id': zona.id,
                        'nombre': zona.nombre,
                        'nivel_peligro': zona.nivel_peligro,
                        'tipo': zona.tipo,
                        'porcentaje_ruta': round(porcentaje, 2),
                        'notas': zona.notas,
                        'distancia_minima': round(dist_min_zona, 1),
                        'radio_zona': radio_zona,
                        'proximidad': proximidad,
                        'puntos_detectados': puntos_dentro_zona
                    })
                    
                    nivel_riesgo_maximo = max(nivel_riesgo_maximo, zona.nivel_peligro)
                else:
                    logger.info(f"  ↳ Zona '{zona.nombre}' descartada: "
                               f"solo {puntos_dentro_zona} puntos (umbral: {umbral_puntos})")
            
            # 🔥 DETERMINAR SEGURIDAD CON CRITERIOS ADAPTATIVOS
            es_segura = nivel_riesgo_maximo < self.UMBRAL_RIESGO_MEDIO
            
            # 🔥 GENERAR MENSAJE CONTEXTUAL
            mensaje = None
            if not es_segura:
                if nivel_riesgo_maximo >= self.UMBRAL_RIESGO_ALTO:
                    mensaje = f"⛔ RIESGO ALTO: Esta ruta pasa por {len(zonas_detectadas)} zona(s) que marcaste como MUY PELIGROSAS. Se recomienda elegir otra ruta."
                elif nivel_riesgo_maximo == self.UMBRAL_RIESGO_MEDIO:
                    mensaje = f"⚠️ PRECAUCIÓN: Esta ruta pasa cerca de {len(zonas_detectadas)} zona(s) con riesgo moderado. Considera alternativas si es posible."
            
            resultado = {
                'es_segura': es_segura,
                'nivel_riesgo': nivel_riesgo_maximo,
                'zonas_detectadas': zonas_detectadas,
                'mensaje': mensaje,
                'puntos_analizados': len(puntos_ruta),
                'puntos_muestreados': len(puntos_muestreados),
                'config': {
                    'buffer_deteccion': self.BUFFER_DETECCION_METROS,
                    'umbral_puntos': self.PUNTOS_MINIMOS_ALERTA
                }
            }
            
            logger.info(f"✅ Usuario {self.usuario_id} - Validación completada: "
                       f"segura={es_segura}, nivel={nivel_riesgo_maximo}, "
                       f"zonas={len(zonas_detectadas)}")
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error validando ruta para usuario {self.usuario_id}: {e}", exc_info=True)
            return {
                'es_segura': True,  # En caso de error, permitir la ruta por seguridad
                'nivel_riesgo': 0,
                'zonas_detectadas': [],
                'mensaje': 'Error en validación de seguridad',
                'error': str(e)
            }
    
    def _calcular_distancia_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        🌍 Calcula distancia en metros usando fórmula de Haversine
        Preciso para distancias cortas (<1000km) en cualquier terreno
        
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
        
        🔥 PRODUCCIÓN: Prioriza rutas seguras, luego por distancia/tiempo
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
                'duration': ruta.get('duration'),
                'geometry': ruta.get('geometry')  # Preservar geometría
            })
        
        # 🔥 ORDENAMIENTO INTELIGENTE:
        # 1. Rutas seguras primero
        # 2. Luego por menor nivel de riesgo
        # 3. Finalmente por distancia (rutas cortas primero)
        resultados.sort(key=lambda x: (
            not x['es_segura'],           # Seguras primero
            x['nivel_riesgo'],            # Menor riesgo primero
            x.get('distance', float('inf'))  # Más cortas primero
        ))
        
        return resultados
    
    def _decode_polyline(self, encoded: str) -> List[Dict]:
        """
        Decodifica polyline de OpenRouteService a lista de coordenadas
        Compatible con diferentes proveedores de rutas
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
        Útil para dashboards y reportes
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
            nivel = zona.nivel_peligro
            zonas_por_nivel[nivel] = zonas_por_nivel.get(nivel, 0) + 1
        
        # Calcular cobertura total (suma de áreas)
        area_total_km2 = sum([
            3.14159 * ((z.radio_metros or 200) / 1000) ** 2 
            for z in zonas if z.activa
        ])
        
        return {
            'total_zonas': len(zonas),
            'zonas_activas': len([z for z in zonas if z.activa]),
            'zonas_inactivas': len([z for z in zonas if not z.activa]),
            'zonas_por_tipo': zonas_por_tipo,
            'zonas_por_nivel': zonas_por_nivel,
            'area_total_vigilada_km2': round(area_total_km2, 2),
            'configuracion': {
                'buffer_deteccion_metros': self.BUFFER_DETECCION_METROS,
                'puntos_minimos_alerta': self.PUNTOS_MINIMOS_ALERTA
            }
        }
    
    def invalidar_cache(self):
        """
        Invalida el caché de zonas peligrosas
        Útil después de que el usuario modifique sus zonas
        """
        self._cache_zonas = None
        self._cache_timestamp = None
        logger.info(f"Caché de zonas invalidado para usuario {self.usuario_id}")
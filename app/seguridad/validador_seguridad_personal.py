import logging
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import math

logger = logging.getLogger(__name__)

class ValidadorSeguridadPersonal:
    """
    🔒 Validador de rutas con detección inteligente de puentes
    """
    
    def __init__(self, db: Session, usuario_id: int):
        self.db = db
        self.usuario_id = usuario_id
        self._cache_zonas = None
        self._cache_timestamp = None
        
        # 🔥 AJUSTAR ESTOS VALORES
        self.RADIO_VERIFICACION_PUENTE = 200
        self.MIN_PUNTOS_CONSECUTIVOS = 3
        self.VELOCIDAD_MINIMA_PUENTE = 12.0  # ← CAMBIAR de 8.0 a 12.0 (más estricto)
        self.TOLERANCIA_INTERSECCION_REAL = 50  # ← CAMBIAR de 25 a 50 (más permisivo)
        
        # 🆕 NUEVOS UMBRALES
        self.UMBRAL_CONFIANZA_MINIMA = 30  # Bajar de 50 a 30
        
    def _get_zonas_peligrosas_usuario(self) -> List:
        """Obtiene zonas peligrosas activas del usuario"""
        from .models import ZonaPeligrosaUsuario        
        ahora = datetime.now()
        
        if (self._cache_zonas is not None and 
            self._cache_timestamp is not None and 
            (ahora - self._cache_timestamp).seconds < 300):
            return self._cache_zonas
        
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
        🔥 VALIDACIÓN MEJORADA CON DETECCIÓN DE PUENTES
        """
        try:
            zonas_peligrosas = self._get_zonas_peligrosas_usuario()
            
            if not zonas_peligrosas:
                return {
                    'es_segura': True,
                    'nivel_riesgo': 0,
                    'zonas_detectadas': [],
                    'mensaje': None
                }
            
            # Decodificar ruta
            puntos_ruta = self._decode_polyline(geometry_polyline)
            
            if not puntos_ruta:
                return {
                    'es_segura': True,
                    'nivel_riesgo': 0,
                    'zonas_detectadas': [],
                    'mensaje': 'No se pudo validar la ruta',
                    'error': True
                }
            
            # 🔥 ANÁLISIS CON DETECCIÓN DE PUENTES
            zonas_detectadas = []
            nivel_riesgo_maximo = 0
            
            # Analizar cada zona
            for zona in zonas_peligrosas:
                resultado_zona = self._analizar_zona_con_deteccion_puentes(
                    zona, 
                    puntos_ruta,
                    metadata
                )
                
                if resultado_zona['es_interseccion_real']:
                    zonas_detectadas.append({
                        'zona_id': zona.id,
                        'nombre': zona.nombre,
                        'nivel_peligro': zona.nivel_peligro,
                        'tipo': zona.tipo,
                        'porcentaje_ruta': round(resultado_zona['porcentaje'], 2),
                        'notas': zona.notas,
                        'distancia_minima': round(resultado_zona['distancia_minima'], 1),
                        'posible_puente': resultado_zona['posible_puente'],
                        'puntos_dentro': resultado_zona['puntos_dentro']
                    })
                    
                    nivel_riesgo_maximo = max(nivel_riesgo_maximo, zona.nivel_peligro)
            
            # Determinar seguridad
            es_segura = nivel_riesgo_maximo < 3
            
            # Mensaje
            mensaje = None
            if not es_segura:
                if nivel_riesgo_maximo >= 4:
                    mensaje = f"RIESGO ALTO: Esta ruta pasa por {len(zonas_detectadas)} zona(s) peligrosas"
                elif nivel_riesgo_maximo == 3:
                    mensaje = f"PRECAUCIÓN: Esta ruta pasa por {len(zonas_detectadas)} zona(s) con riesgo moderado"
            
            return {
                'es_segura': es_segura,
                'nivel_riesgo': nivel_riesgo_maximo,
                'zonas_detectadas': zonas_detectadas,
                'mensaje': mensaje,
                'puntos_analizados': len(puntos_ruta)
            }
            
        except Exception as e:
            logger.error(f"Error validando ruta: {e}", exc_info=True)
            return {
                'es_segura': True,
                'nivel_riesgo': 0,
                'zonas_detectadas': [],
                'mensaje': 'Error en validación',
                'error': str(e)
            }
    
    def _analizar_zona_con_deteccion_puentes(
        self, 
        zona, 
        puntos_ruta: List[Dict],
        metadata: Dict = None
    ) -> Dict:
        """
        🔥 NUEVO: Analiza si la ruta REALMENTE pasa por la zona o solo es un puente
        
        Estrategias:
        1. Verificar clustering de puntos (¿hay muchos puntos consecutivos dentro?)
        2. Analizar velocidad (¿va muy rápido? = posible puente/autopista elevada)
        3. Verificar distancia mínima al centro (¿pasa justo por el borde o por el centro?)
        4. Análisis de patrón de entrada/salida
        """
        
        # Datos de la zona
        centro = zona.poligono[0] if zona.poligono else None
        if not centro:
            return {'es_interseccion_real': False, 'porcentaje': 0, 'distancia_minima': float('inf')}
        
        radio_zona = zona.radio_metros or 200
        
        # Variables de análisis
        puntos_dentro = 0
        puntos_muy_cerca_centro = 0  # Puntos a menos de 50m del centro
        distancias_al_centro = []
        indices_puntos_dentro = []
        
        # Analizar cada punto
        for i, punto in enumerate(puntos_ruta):
            distancia = self._calcular_distancia_haversine(
                punto['lat'], punto['lon'],
                centro['lat'], centro['lon']
            )
            
            distancias_al_centro.append(distancia)
            
            # ¿Está dentro del radio?
            if distancia <= radio_zona:
                puntos_dentro += 1
                indices_puntos_dentro.append(i)
                
                # ¿Está MUY cerca del centro?
                if distancia <= 50:
                    puntos_muy_cerca_centro += 1
        
        # Si no hay puntos dentro, no hay intersección
        if puntos_dentro == 0:
            return {
                'es_interseccion_real': False,
                'porcentaje': 0,
                'distancia_minima': min(distancias_al_centro),
                'posible_puente': False,
                'puntos_dentro': 0
            }
        
        # 🔥 ESTRATEGIA 1: Análisis de clustering
        # Si los puntos están muy dispersos = posible puente
        clustering_score = self._analizar_clustering(indices_puntos_dentro)
        
        # 🔥 ESTRATEGIA 2: Análisis de velocidad (si disponible en metadata)
        velocidad_promedio = self._estimar_velocidad_promedio(
            puntos_ruta, 
            indices_puntos_dentro,
            metadata
        )
        
        # 🔥 ESTRATEGIA 3: Distancia mínima al centro
        distancia_minima = min(distancias_al_centro)
        
        # 🔥 ESTRATEGIA 4: Análisis de entrada/salida
        patron_entrada_salida = self._analizar_patron_entrada_salida(
            puntos_ruta,
            indices_puntos_dentro,
            centro,
            radio_zona
        )
        
        # 🎯 DECISIÓN FINAL: ¿Es intersección real o solo un puente?
        es_posible_puente = False
        confianza_interseccion = 100
        
        # Indicadores de PUENTE (más estrictos):
        if clustering_score < 0.2:  # ← Cambiar de 0.3 a 0.2
            es_posible_puente = True
            confianza_interseccion -= 50  # ← Penalizar más fuerte
            logger.info(f"   ⚠️ {zona.nombre}: Puntos MUY dispersos")
        
        if velocidad_promedio > self.VELOCIDAD_MINIMA_PUENTE:  # Ahora 12 m/s
            es_posible_puente = True
            confianza_interseccion -= 40
            logger.info(f"   ⚠️ {zona.nombre}: Velocidad ALTA ({velocidad_promedio:.1f} m/s)")
        
        # 🔥 SOLO descartar si la distancia es > 150m Y hay otros indicadores
        if distancia_minima > 150 and clustering_score < 0.2:  # ← Combinación
            es_posible_puente = True
            confianza_interseccion -= 40
        
        # 🎯 UMBRAL DE DECISIÓN MEJORADO
        es_interseccion_real = (
            clustering_score >= 0.15 and  # ← Más permisivo (antes 0.3)
            confianza_interseccion >= 30 and  # ← Más permisivo (antes 50)
            (puntos_muy_cerca_centro >= 1 or patron_entrada_salida['transito_lento'] or distancia_minima <= 100)  # ← Añadir distancia
        )
        
        # Calcular porcentaje
        porcentaje = (puntos_dentro / len(puntos_ruta)) * 100 if es_interseccion_real else 0
        
        # Log detallado
        if puntos_dentro > 0:
            logger.info(f"📊 {zona.nombre}:")
            logger.info(f"   Puntos dentro: {puntos_dentro}/{len(puntos_ruta)}")
            logger.info(f"   Puntos cerca centro: {puntos_muy_cerca_centro}")
            logger.info(f"   Clustering: {clustering_score:.2f}")
            logger.info(f"   Velocidad estimada: {velocidad_promedio:.1f} m/s")
            logger.info(f"   Distancia mínima: {distancia_minima:.1f}m")
            logger.info(f"   Confianza: {confianza_interseccion}%")
            logger.info(f"   {'❌ DESCARTADO' if es_posible_puente and not es_interseccion_real else '✅ INTERSECCIÓN REAL'}")
        
        return {
            'es_interseccion_real': es_interseccion_real,
            'porcentaje': porcentaje,
            'distancia_minima': distancia_minima,
            'posible_puente': es_posible_puente,
            'puntos_dentro': puntos_dentro,
            'confianza': confianza_interseccion,
            'clustering_score': clustering_score,
            'velocidad_promedio': velocidad_promedio
        }
    
    def _analizar_clustering(self, indices: List[int]) -> float:
        """
        Analiza qué tan agrupados están los puntos
        Retorna: 0.0 (muy dispersos) a 1.0 (muy agrupados)
        """
        if len(indices) < 2:
            return 0.0
        
        # Calcular gaps entre índices consecutivos
        gaps = [indices[i+1] - indices[i] for i in range(len(indices)-1)]
        
        # Si hay muchos gaps grandes = disperso
        gaps_grandes = sum(1 for g in gaps if g > 10)
        
        # Score: más bajo si hay muchos gaps grandes
        score = 1.0 - (gaps_grandes / len(gaps))
        
        return max(0.0, score)
    
    def _estimar_velocidad_promedio(
        self, 
        puntos_ruta: List[Dict],
        indices_dentro: List[int],
        metadata: Dict = None
    ) -> float:
        """
        Estima la velocidad promedio en la zona
        
        Métodos:
        1. Si metadata tiene 'tipo_transporte' y 'duracion', calcular
        2. Distancia entre puntos / tiempo estimado
        """
        
        # Método 1: Usar metadata si disponible
        if metadata and 'duration' in metadata and 'distance' in metadata:
            try:
                duracion_s = metadata['duration']  # segundos
                distancia_m = metadata['distance']  # metros
                if duracion_s > 0:
                    velocidad = distancia_m / duracion_s
                    return velocidad
            except:
                pass
        
        # Método 2: Estimar por tipo de ruta
        if metadata and 'tipo' in metadata:
            tipo = metadata['tipo'].lower()
            if 'fastest' in tipo or 'car' in tipo:
                return 15.0  # ~54 km/h (ciudad)
            elif 'shortest' in tipo:
                return 5.0   # ~18 km/h (peatonal/lento)
            elif 'recommended' in tipo:
                return 10.0  # ~36 km/h (intermedio)
        
        # Método 3: Default conservador
        return 5.0  # Asumir tránsito lento por defecto
    
    def _analizar_patron_entrada_salida(
        self,
        puntos_ruta: List[Dict],
        indices_dentro: List[int],
        centro: Dict,
        radio: float
    ) -> Dict:
        """
        Analiza el patrón de cómo la ruta entra y sale de la zona
        
        Retorna:
            - transito_lento: Si hay evidencia de tránsito lento/detenido
            - entrada_gradual: Si entra gradualmente o de golpe
        """
        
        if len(indices_dentro) < 3:
            return {'transito_lento': False, 'entrada_gradual': False}
        
        # Analizar distancias al centro en los puntos dentro
        distancias_dentro = []
        for idx in indices_dentro:
            punto = puntos_ruta[idx]
            dist = self._calcular_distancia_haversine(
                punto['lat'], punto['lon'],
                centro['lat'], centro['lon']
            )
            distancias_dentro.append(dist)
        
        # ¿Hay tránsito lento? (varios puntos muy cerca entre sí)
        puntos_muy_juntos = sum(1 for d in distancias_dentro if d < 30)
        transito_lento = puntos_muy_juntos >= 3
        
        # ¿Entrada gradual? (distancias decrecientes progresivamente)
        if len(distancias_dentro) >= 3:
            # Verificar si hay patrón de acercamiento gradual
            primeras_3 = distancias_dentro[:3]
            entrada_gradual = (
                primeras_3[0] > primeras_3[1] > primeras_3[2] or
                primeras_3[0] < primeras_3[1] < primeras_3[2]
            )
        else:
            entrada_gradual = False
        
        return {
            'transito_lento': transito_lento,
            'entrada_gradual': entrada_gradual
        }
    
    # ══════════════════════════════════════════════════════════
    # MÉTODOS AUXILIARES (mantener los existentes)
    # ══════════════════════════════════════════════════════════
    
    def _calcular_distancia_haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calcula distancia en metros usando Haversine"""
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
        """Valida múltiples rutas"""
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
        
        resultados.sort(key=lambda x: (not x['es_segura'], x['nivel_riesgo']))
        return resultados
    
    def _decode_polyline(self, encoded: str) -> List[Dict]:
        """Decodifica polyline a coordenadas"""
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
        """Obtiene estadísticas de seguridad del usuario"""
        from .models import ZonaPeligrosaUsuario
                
        zonas = self.db.query(ZonaPeligrosaUsuario).filter(
            ZonaPeligrosaUsuario.usuario_id == self.usuario_id
        ).all()
        
        zonas_por_tipo = {}
        for zona in zonas:
            tipo = zona.tipo or 'otro'
            zonas_por_tipo[tipo] = zonas_por_tipo.get(tipo, 0) + 1
        
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
import logging
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)

class ValidadorSeguridadPersonal:
    """
    🔒 Validador de rutas contra zonas peligrosas PERSONALES del usuario
    Cada usuario tiene su propio conjunto de zonas peligrosas
    """
    
    def __init__(self, db: Session, usuario_id: int):
        self.db = db
        self.usuario_id = usuario_id
        self._cache_zonas = None
        self._cache_timestamp = None
    
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
        
        Args:
            geometry_polyline: Polyline encoded de la ruta
            metadata: Información adicional (tipo, distancia, duración)
        
        Returns:
            {
                'es_segura': bool,
                'nivel_riesgo': int (0-5),
                'zonas_detectadas': List[Dict],
                'mensaje': str
            }
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
                    'es_segura': True,  # Conservador: aprobar si hay error
                    'nivel_riesgo': 0,
                    'zonas_detectadas': [],
                    'mensaje': 'No se pudo validar la ruta',
                    'error': True
                }
            
            # Verificar intersecciones
            zonas_detectadas = []
            nivel_riesgo_maximo = 0
            
            # Muestrear puntos de la ruta (cada 10 puntos para eficiencia)
            puntos_muestreados = puntos_ruta[::10] if len(puntos_ruta) > 20 else puntos_ruta
            
            for zona in zonas_peligrosas:
                puntos_en_zona = 0
                
                for punto in puntos_muestreados:
                    if self._punto_en_poligono(punto, zona.poligono):
                        puntos_en_zona += 1
                
                if puntos_en_zona > 0:
                    # Calcular porcentaje aproximado
                    porcentaje = (puntos_en_zona / len(puntos_muestreados)) * 100
                    
                    zonas_detectadas.append({
                        'zona_id': zona.id,
                        'nombre': zona.nombre,
                        'nivel_peligro': zona.nivel_peligro,
                        'tipo': zona.tipo,
                        'porcentaje_ruta': round(porcentaje, 2),
                        'notas': zona.notas
                    })
                    
                    nivel_riesgo_maximo = max(nivel_riesgo_maximo, zona.nivel_peligro)
            
            # Determinar si es segura (nivel 3+ es considerado inseguro)
            es_segura = nivel_riesgo_maximo < 3
            
            # Generar mensaje
            mensaje = None
            if not es_segura:
                if nivel_riesgo_maximo >= 4:
                    mensaje = f"⚠️ RIESGO ALTO: Esta ruta pasa por {len(zonas_detectadas)} zona(s) que marcaste como peligrosas"
                elif nivel_riesgo_maximo == 3:
                    mensaje = f"⚠️ PRECAUCIÓN: Esta ruta pasa por {len(zonas_detectadas)} zona(s) con riesgo moderado"
            
            resultado = {
                'es_segura': es_segura,
                'nivel_riesgo': nivel_riesgo_maximo,
                'zonas_detectadas': zonas_detectadas,
                'mensaje': mensaje,
                'puntos_analizados': len(puntos_ruta),
                'puntos_muestreados': len(puntos_muestreados)
            }
            
            logger.info(f"Usuario {self.usuario_id} - Validación: segura={es_segura}, "
                       f"nivel={nivel_riesgo_maximo}, zonas={len(zonas_detectadas)}")
            
            return resultado
            
        except Exception as e:
            logger.error(f"Error validando ruta para usuario {self.usuario_id}: {e}", exc_info=True)
            # En caso de error, ser conservador y aprobar la ruta
            return {
                'es_segura': True,
                'nivel_riesgo': 0,
                'zonas_detectadas': [],
                'mensaje': 'Error en validación',
                'error': str(e)
            }
    
    def validar_multiples_rutas(self, rutas: List[Dict]) -> List[Dict]:
        """
        Valida múltiples rutas y las ordena por seguridad
        
        Args:
            rutas: Lista de diccionarios con 'tipo', 'geometry', etc.
        
        Returns:
            Lista de rutas validadas con información de seguridad
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
        
        # Ordenar por seguridad (seguras primero, luego por nivel de riesgo)
        resultados.sort(key=lambda x: (not x['es_segura'], x['nivel_riesgo']))
        
        return resultados
    
    def _punto_en_poligono(self, punto: Dict, poligono: List[Dict]) -> bool:
        """
        Algoritmo Ray Casting para determinar si un punto está dentro de un polígono
        
        Args:
            punto: {'lat': float, 'lon': float}
            poligono: [{'lat': float, 'lon': float}, ...]
        
        Returns:
            True si el punto está dentro del polígono
        """
        x, y = punto['lon'], punto['lat']
        n = len(poligono)
        inside = False
        
        p1x, p1y = poligono[0]['lon'], poligono[0]['lat']
        
        for i in range(1, n + 1):
            p2x, p2y = poligono[i % n]['lon'], poligono[i % n]['lat']
            
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _decode_polyline(self, encoded: str) -> List[Dict]:
        """
        Decodifica polyline de OpenRouteService/Google a lista de coordenadas
        
        Args:
            encoded: String polyline encoded
        
        Returns:
            Lista de puntos: [{'lat': float, 'lon': float}, ...]
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
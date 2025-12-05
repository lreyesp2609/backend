import math
from typing import List, Dict

def crear_poligono_circular(lat: float, lon: float, radio_metros: int, num_puntos: int = 32) -> List[Dict]:
    """
    Crea un polígono circular dado un punto central y un radio
    
    Args:
        lat: Latitud del centro
        lon: Longitud del centro
        radio_metros: Radio del círculo en metros
        num_puntos: Número de puntos del polígono (default 32)
    
    Returns:
        Lista de puntos [{'lat': float, 'lon': float}, ...]
    """
    puntos = []
    
    # Conversión de metros a grados
    radio_grados_lat = radio_metros / 111320.0
    radio_grados_lon = radio_metros / (111320.0 * math.cos(math.radians(lat)))
    
    # Generar puntos alrededor del círculo
    for i in range(num_puntos + 1):  # +1 para cerrar el círculo
        angulo = (2 * math.pi * i) / num_puntos
        
        # ✅ CORRECTO: cos() para latitud, sin() para longitud
        dlat = radio_grados_lat * math.cos(angulo)
        dlon = radio_grados_lon * math.sin(angulo)
        
        puntos.append({
            'lat': lat + dlat,
            'lon': lon + dlon
        })
    
    return puntos

def calcular_distancia_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en metros entre dos puntos usando la fórmula de Haversine
    
    Args:
        lat1, lon1: Coordenadas del punto 1
        lat2, lon2: Coordenadas del punto 2
    
    Returns:
        Distancia en metros
    """
    R = 6371000  # Radio de la Tierra en metros
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 + 
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def validar_coordenadas(lat: float, lon: float) -> bool:
    """
    Valida que las coordenadas sean válidas
    
    Args:
        lat: Latitud
        lon: Longitud
    
    Returns:
        True si son válidas
    """
    return -90 <= lat <= 90 and -180 <= lon <= 180

def calcular_bounding_box(puntos: List[Dict]) -> Dict:
    """
    Calcula el bounding box (caja delimitadora) de un conjunto de puntos
    
    Args:
        puntos: Lista de puntos [{'lat': float, 'lon': float}, ...]
    
    Returns:
        {'min_lat': float, 'max_lat': float, 'min_lon': float, 'max_lon': float}
    """
    if not puntos:
        return None
    
    lats = [p['lat'] for p in puntos]
    lons = [p['lon'] for p in puntos]
    
    return {
        'min_lat': min(lats),
        'max_lat': max(lats),
        'min_lon': min(lons),
        'max_lon': max(lons)
    }
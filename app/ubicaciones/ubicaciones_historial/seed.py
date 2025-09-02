from sqlalchemy.orm import Session
from .models import EstadoUbicacion

def create_default_estados_ubicacion(db: Session):
    estados_default = [
        {
            "nombre": "EN_PROGRESO",
            "descripcion": "La ubicación está siendo rastreada activamente",
            "activo": True,
            "orden": 1
        },
        {
            "nombre": "FINALIZADA",
            "descripcion": "El rastreo de ubicación ha terminado exitosamente",
            "activo": True,
            "orden": 2
        },
        {
            "nombre": "CANCELADA",
            "descripcion": "El rastreo de ubicación fue cancelado",
            "activo": True,
            "orden": 3
        }
    ]
    
    for estado_data in estados_default:
        estado_existente = db.query(EstadoUbicacion).filter(
            EstadoUbicacion.nombre == estado_data["nombre"]
        ).first()
        
        if not estado_existente:
            estado = EstadoUbicacion(**estado_data)
            db.add(estado)
    
    try:
        db.commit()
        print("✅ Estados de ubicación creados exitosamente")
    except Exception as e:
        db.rollback()
        print(f"❌ Error creando estados de ubicación: {e}")

def get_estado_en_progreso_id(db: Session) -> int:
    """Helper para obtener el ID del estado EN_PROGRESO"""
    estado = db.query(EstadoUbicacion).filter(
        EstadoUbicacion.nombre == "EN_PROGRESO"
    ).first()
    return estado.id if estado else None
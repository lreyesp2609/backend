from sqlalchemy.orm import Session
from .models import Transporte

def seed_transportes(db: Session):
    transportes = [
        {"nombre": "foot-walking", "descripcion": "Caminar"},
        {"nombre": "driving-car", "descripcion": "Carro"},
        {"nombre": "cycling-regular", "descripcion": "Bicicleta"}
    ]

    for t in transportes:
        existe = db.query(Transporte).filter(Transporte.nombre == t["nombre"]).first()
        if not existe:
            db.add(Transporte(nombre=t["nombre"], descripcion=t["descripcion"]))
    
    db.commit()

from sqlalchemy.orm import relationship

def configure_relationships():

    # Importar todos los modelos
    from app.ubicaciones.models import UbicacionUsuario
    from app.usuarios.models import Usuario
    from app.ubicaciones.ubicaciones_historial.models import EstadoUbicacionUsuario, EstadoUbicacion
    from app.ubicaciones.ubicaciones_historial.rutas.models import RutaUsuario
    
    # Configurar relaciones de UbicacionUsuario
    UbicacionUsuario.estados = relationship(
        "EstadoUbicacionUsuario",
        back_populates="ubicacion",
        cascade="all, delete-orphan"
    )
    
    # Configurar relaciones de Usuario
    Usuario.estados_ubicacion = relationship(
        "EstadoUbicacionUsuario",
        back_populates="usuario",
        cascade="all, delete-orphan"
    )
    
    # Configurar relaciones entre EstadoUbicacionUsuario y RutaUsuario
    EstadoUbicacionUsuario.rutas = relationship(
        "RutaUsuario",
        back_populates="estado",
        cascade="all, delete-orphan"
    )
    
    RutaUsuario.estado = relationship(
        "EstadoUbicacionUsuario", 
        back_populates="rutas"
    )
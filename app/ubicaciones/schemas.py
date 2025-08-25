from pydantic import BaseModel, Field

class UbicacionUsuarioBase(BaseModel):
    nombre: str = Field(..., example="Casa")
    latitud: float = Field(..., example=-0.180653)
    longitud: float = Field(..., example=-78.467834)
    direccion_completa: str = Field(..., example="Av. Amazonas y Naciones Unidas")

class UbicacionUsuarioCreate(UbicacionUsuarioBase):
    pass

class UbicacionUsuarioUpdate(BaseModel):
    nombre: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    direccion_completa: str | None = None  # 🔹 cambiar aquí

class UbicacionUsuarioResponse(UbicacionUsuarioBase):
    id: int
    usuario_id: int

    class Config:
        orm_mode = True

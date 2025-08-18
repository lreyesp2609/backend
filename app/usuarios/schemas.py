from pydantic import BaseModel, EmailStr, Field

class UsuarioCreate(BaseModel):
    nombre: str = Field(..., max_length=100)
    apellido: str = Field(..., max_length=100)
    correo: EmailStr
    contrasenia: str = Field(..., min_length=6)

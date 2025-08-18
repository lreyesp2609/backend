from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    correo: EmailStr
    contrasenia: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

-- Active: 1728086680261@@127.0.0.1@5432@app_fastapi
-- Tabla de roles
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion TEXT
);

-- Tabla de datos personales  
CREATE TABLE datos_personales (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL
);

-- Tabla de usuarios (correo como identificador de acceso)
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    correo VARCHAR(150) NOT NULL UNIQUE,  -- antes era usuario
    contrasenia VARCHAR(255) NOT NULL,
    datos_personales_id INTEGER NOT NULL REFERENCES datos_personales(id),
    rol_id INTEGER NOT NULL REFERENCES roles(id),
    activo BOOLEAN DEFAULT true,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- nuevo campo
);

-- Insertar algunos roles básicos
INSERT INTO roles (nombre, descripcion) VALUES 
('usuario', 'Usuario regular');

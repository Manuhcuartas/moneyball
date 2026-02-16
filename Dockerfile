# Usamos una imagen ligera de Python 3.11
FROM python:3.11-slim

# Evita que Python genere archivos .pyc y fuerza logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalamos dependencias del sistema necesarias para compilar algunas librerías
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiamos los requisitos e instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamos todo el código del proyecto al contenedor
COPY . .

# Exponemos el puerto (Render usa $PORT)
EXPOSE 8000

# Comando de arranque (Render inyecta $PORT automáticamente)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
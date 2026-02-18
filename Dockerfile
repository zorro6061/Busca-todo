# Usar una imagen base de Python estable y ligera
FROM python:3.11-slim

# Evitar que Python genere archivos .pyc y asegurar logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para psycopg2 y Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Exponer el puerto que usa Cloud Run (por defecto 8080)
ENV PORT 8080

# Comando para arrancar con Gunicorn (optimizado)
CMD gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app

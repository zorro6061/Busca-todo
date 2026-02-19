# Informe Técnico de Arquitectura: Busca-todo (Aperture Home)

**Estatus:** Producción (Google Cloud Run)
**Misión:** Localización de activos físicos mediante Visión Artificial y Procesamiento de Lenguaje Natural (NLP).

---

## 1. Estructura del Repositorio
```text
CTRL_F_FISICO_APP/
├── ai_engine.py           # Integración con Gemini (Vision & NLP)
├── app.py                 # Lógica de servidor Flask y API
├── models.py              # Esquema de Base de Datos (SQLAlchemy)
├── video_processor.py     # Procesamiento de frames y buffers
├── spatial_engine.py      # Lógica de proyección en planos 2D
├── Dockerfile             # Configuración del contenedor
├── requirements.txt       # Dependencias de Python
├── Procfile               # Configuración para Gunicorn
├── static/                # Assets (CSS/JS)
│   ├── css/style.css      # Design System (Glassmorphism)
│   └── js/                # Scripts de frontend
├── templates/             # Vistas Jinja2 (HTML)
│   ├── layout.html        # Estructura base
│   ├── index.html         # Buscador NLP
│   └── ...
└── uploads/               # Almacenamiento local (temporal/GCS Cache)
```

---

## 2. Stack Tecnológico
*   **Lenguajes:** Python (Backend), Javascript (Vanilla ES6), HTML/CSS.
*   **Framework Backend:** Flask (WSGI).
*   **ORM:** SQLAlchemy (Flask-SQLAlchemy).
*   **Inteligencia Artificial:** Google Gemini (SDK `google-genai==0.3.0`).
*   **Base de Datos:** PostgreSQL (Cloud SQL) / SQLite (Fallback Local).
*   **Almacenamiento:** Google Cloud Storage (Bucket para fotos/planos).
*   **Infraestructura:** Google Cloud Run (Dockerized), Cloud Build (CI/CD).
*   **Librerías Clave:**
    *   `rapidfuzz`: Búsqueda difusa y coincidencia de strings.
    *   `Pillow`/`pillow-heif`: Procesamiento de imágenes (JPG, PNG, HEIC).
    *   `psycopg2-binary`: Driver para PostgreSQL.

---

## 3. Esquema de Base de Datos (SQL)
```sql
-- Tabla: Planos (Mapas o croquis de la casa)
CREATE TABLE planos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    imagen_path VARCHAR(255),
    ancho INTEGER DEFAULT 1000,
    alto INTEGER DEFAULT 1000,
    homografia_json TEXT
);

-- Tabla: Ubicaciones (Capturas específicas o vistas)
CREATE TABLE ubicaciones (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    imagen_path VARCHAR(255) NOT NULL,
    items_json TEXT, -- Almacena bboxes originales de la IA
    plano_id INTEGER REFERENCES planos(id)
);

-- Tabla: Objetos (Items detectados)
CREATE TABLE objetos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    categoria_principal VARCHAR(50),
    descripcion TEXT,
    color_predominante VARCHAR(30),
    material VARCHAR(50),
    estado VARCHAR(50),
    tags_semanticos TEXT,
    confianza FLOAT,
    ubicacion_id INTEGER REFERENCES ubicaciones(id),
    pos_x FLOAT, -- Posición normalizada en el mapa
    pos_y FLOAT,
    zona_id INTEGER REFERENCES zonas(id)
);
```

---

## 4. Integración con Gemini (AI Logic)

### Envío de Imágenes a la IA
```python
def analizar_imagen_objetos(image_path, tipo_espacio="general"):
    client = get_client() # Carga google-genai con API_KEY v1 stable
    img = Image.open(image_path)
    
    # Prompt Maestro: Rol de Experto en Logística
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=[SYSTEM_PROMPT, img]
    )
    return parse_json_response(response.text)
```

### System Prompt (Extracto Actual)
> **ROL:** Eres un experto en logística y gestión de activos físicos...
> **OBJETIVOS:** Detallar Color, Material, Estado y Bounding Boxes [0-1000].
> **OUTPUT:** JSON Estricto con `items`, `metadata` y `analisis_espacial`.

---

## 5. Configuración del Contenedor (Dockerfile)
```dockerfile
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT 8080
CMD gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
```

---

## 6. Variables de Entorno (Requeridas)
*   `DATABASE_URL`: URI de conexión a PostgreSQL (Interna o Cloud SQL).
*   `GEMINI_API_KEY`: Llave de acceso a Google AI Studio.
*   `GCP_BUCKET_NAME`: Nombre del bucket en Google Cloud Storage.
*   `SECRET_KEY`: Llave para sesiones de Flask.
*   `FLASK_DEBUG`: (Opcional) true o false para logs extendidos.

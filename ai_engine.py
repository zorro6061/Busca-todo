import os
from google import genai
from PIL import Image
from dotenv import load_dotenv
import json
import logging

load_dotenv()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de Gemini (SDK Moderna google-genai)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_client = None

def get_client():
    global _client
    if _client:
        return _client
    
    if GEMINI_API_KEY:
        try:
            # Forzamos v1 estable para evitar el error 404 de v1beta visto en Render
            from google import genai as genai_module
            _client = genai_module.Client(
                api_key=GEMINI_API_KEY,
                http_options={'api_version': 'v1'}
            )
            key_prefix = GEMINI_API_KEY[:6] if GEMINI_API_KEY else "None"
            # Confirmación explícita para diagnóstico
            logger.info(f"[GEMINI-DIAGNOSTIC] API Key cargada: True")
            
            # Intentar obtener versión si está disponible (vía importlib.metadata)
            try:
                import importlib.metadata
                version = importlib.metadata.version("google-genai")
                logger.info(f"[GEMINI-DIAGNOSTIC] Usando google-genai versión: {version}")
            except:
                logger.info(f"[GEMINI-DIAGNOSTIC] google-genai versión: No se pudo detectar vía importlib.metadata")
            
            logger.info(f"[GEMINI-DIAGNOSTIC] Cliente inicializado correctamente. Prefix: {key_prefix}***")
            return _client
        except Exception as e:
            logger.error(f"[GEMINI-DIAGNOSTIC] Error FATAL inicializando cliente: {e}")
    else:
        logger.error("[GEMINI-DIAGNOSTIC] API Key NO encontrada en el entorno.")
    return None

def analizar_imagen_objetos(image_path, tipo_espacio="general"):
    """
    Usa la SDK moderna de Gemini para identificar objetos en una imagen física.
    """
    client = get_client()
    if not client:
        logger.error("Cliente Gemini no disponible")
        return {
            "items": [], 
            "tags": "Error: SDK no disponible",
            "analisis_espacial": {}
        }

    try:
        # 0. Verificación dinámica de modelos disponibles (Debug)
        try:
            available_models = list(client.models.list())
            logger.info("[GEMINI-DEBUG] Modelos encontrados para esta API Key:")
            for m in available_models:
                # Verificamos si tiene soporte para imágenes (multimodal)
                modalities = getattr(m, 'input_modalities', [])
                logger.info(f" - Model: {m.name} | Modalities: {modalities}")
        except Exception as list_err:
            logger.error(f"[GEMINI-DEBUG] No se pudo listar los modelos: {list_err}")

        # 1. Validación de Archivo e Imagen (Pillow)
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return {"items": [], "tags": "Error: Archivo no encontrado", "analisis_espacial": {}}
            
        try:
            img = Image.open(image_path)
            img.verify()
            img = Image.open(image_path) # Re-abrir para procesamiento
        except Exception as img_err:
            logger.error(f"Pillow no pudo validar la imagen: {img_err}")
            return {"items": [], "tags": f"Error: Imagen inválida", "analisis_espacial": {}}

        # 2. Prompt Maestro OmniVision (Expert Logistics Upgrade)
        prompt = f"""
ROL: Eres un experto en logística y gestión de activos físicos con años de experiencia analizando depósitos industriales, estanterías y mobiliario técnico.

INSTRUCCIONES DE ANÁLISIS:
1. DETECCIÓN DE OBJETOS: Identifica cada objeto visible, por pequeño que sea. No agrupes. Si hay cajas o contenedores con texto, lee el contenido de las etiquetas y menciónalo en el nombre o descripción.
2. ATRIBUTOS TÉCNICOS: Para cada objeto, detecta:
   - Color predominante.
   - Material estimado (metal, plástico, madera, cartón, etc.).
   - Estado aparente (nuevo, usado, dañado).
   - Tamaño relativo (pequeño, mediano, grande).
3. UBICACIÓN ESPACIAL: Describe dónde está el objeto en relación a la imagen (ej: "Estante superior, lado izquierdo, detrás de la caja roja").
4. CLASIFICACIÓN SEMÁNTICA: Agrupa los objetos por categorías lógicas (Herramientas, Electrónica, Papelería, Repuestos, etc.).
5. COORDINADAS: Detecta la ubicación exacta con bounding box [ymin, xmin, ymax, xmax] en escala 0-1000.

FORMATO DE RESPUESTA (JSON ESTRICTO):
{{
  "items": [
    {{
      "nombre": "Nombre descriptivo específico (incluyendo etiquetas si las hay)",
      "categoria_principal": "Categoría lógica",
      "descripcion": "Detalles visuales y ubicación espacial descriptiva",
      "bbox": [ymin, xmin, ymax, xmax],
      "confianza": 0.XX,
      "metadata": {{
        "color": "...",
        "material": "...",
        "estado": "...",
        "tamaño": "..."
      }},
      "tags_semanticos": "lista, de, etiquetas, separadas, por, coma"
    }}
  ],
  "analisis_espacial": {{
    "tipo_espacio": "{tipo_espacio}",
    "organizacion": "ordenado|caótico|estantería",
    "densidad_objetos": "baja|media|alta"
  }},
  "tags": ["contexto1", "contexto2"]
}}
"""

        # 3. Ejecución con Fallback Dinámico y Logging Extendido
        # Intentamos con varios nombres de modelo por si alguno está restringido o deprecado
        modelos_a_probar = [
            "gemini-1.5-flash", 
            "gemini-1.5-flash-latest", 
            "gemini-2.0-flash", 
            "gemini-1.5-pro"
        ]
        
        text_response = None
        current_used_model = None
        
        for model_name in modelos_a_probar:
            try:
                logger.info(f"[AI-RUNTIME] Probando modelo: {model_name}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, img]
                )
                text_response = response.text
                current_used_model = model_name
                break # Éxito, salimos del bucle
            except Exception as e:
                logger.warning(f"[AI-RUNTIME] Falló {model_name}: {str(e)}")
                continue

        if not text_response:
            raise ValueError("Ninguno de los modelos de Gemini respondió (verificar API Key y cuotas)")

        logger.info(f"[AI-RUNTIME] Respuesta exitosa recibida usando {current_used_model}")

        # 4. Limpieza y Recuperación de JSON
        # Eliminar posibles bloques markdown
        clean_response = text_response.replace('```json', '').replace('```', '').strip()
        
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError:
            # Recuperación: Buscar el primer '{' y último '}'
            start_idx = clean_response.find('{')
            end_idx = clean_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                data = json.loads(clean_response[start_idx:end_idx+1])
            else:
                raise ValueError("No se encontró estructura JSON válida en la respuesta")

        # 5. Normalización de Resultados
        if "items" not in data:
            data["items"] = []
            
        result = {
            "items": data.get("items", []),
            "tags": ", ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", ""),
            "analisis_espacial": data.get("analisis_espacial", {}),
            "texto_detectado": data.get("texto_detectado", []) # Opcional, mantener compatibilidad
        }

        logger.info(f"[AI-SUCCESS] {len(result['items'])} objetos identificados por {current_used_model}")
        return result

    except Exception as e:
        logger.error(f"[AI-ERROR] Fallo crítico en el motor: {str(e)}")
        return {
            "items": [],
            "tags": f"Error procesando imagen: {str(e)}",
            "analisis_espacial": {},
            "texto_detectado": []
        }

def interpretar_consulta(query):
    """
    Usa Gemini para convertir una pregunta natural (¿Dónde están mis llaves?) 
    en un término de búsqueda simple (llaves).
    """
    client = get_client()
    if not client:
        return query # Fallback al texto original

    prompt = f"""
    Eres un asistente de búsqueda para el hogar. Tu tarea es extraer el NOMBRE DEL OBJETO principal que el usuario está buscando.
    
    EJEMPLOS:
    - "¿Dónde dejé las llaves del auto?" -> "llaves"
    - "No encuentro mi billetera marrón" -> "billetera"
    - "¿Dónde está el cargador de la laptop?" -> "cargador"
    - "Quiero ver mi taladro" -> "taladro"
    
    USUARIO: "{query}"
    RESPUESTA (JSON): {{"termino": "nombre_simple"}}
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[prompt]
        )
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(clean_json)
        return data.get("termino", query)
    except Exception as e:
        logger.error(f"Error interpretando consulta: {e}")
        return query

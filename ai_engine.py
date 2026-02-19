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
        # Validación DBA/SRE: Las llaves válidas de Google empiezan por AIza
        if not GEMINI_API_KEY.startswith("AIza"):
            logger.error(f"[GEMINI-DIAGNOSTIC] ERROR CRÍTICO: La API Key parece mal escrita (empieza con {GEMINI_API_KEY[:4]}... en lugar de AIza).")
            return None

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

def analizar_imagen_objetos(image_data, tipo_espacio="general"):
    """
    Usa la SDK moderna de Gemini para identificar objetos en una imagen física.
    image_data puede ser una ruta (str) o bytes.
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
        # ... (logging de modelos omitido para brevedad) ...

        # 1. Carga de Imagen (Pillow)
        try:
            if isinstance(image_data, str):
                if not os.path.exists(image_data):
                     raise FileNotFoundError(f"Archivo no encontrado: {image_data}")
                img = Image.open(image_data)
            else:
                # Asumimos que son bytes
                import io
                img = Image.open(io.BytesIO(image_data))
            
            # Forzar carga para validar
            img.load()
        except Exception as img_err:
            logger.error(f"Pillow no pudo validar la imagen: {img_err}")
            return {"items": [], "tags": f"Error: Imagen inválida", "analisis_espacial": {}}

        # 2. Prompt Maestro: Organizador Doméstico e Inteligencia Familiar
        prompt = f"""
ROL: Eres "Aperture Home", un organizador profesional del hogar con visión computacional avanzada. Tu objetivo es indexar de forma impecable todas las pertenencias de una familia.

REGLAS DE CATEGORIZACIÓN (ESTRICTAS):
Debes clasificar cada objeto identificado en una de estas categorías:
- Tecnología
- Herramientas
- Documentación
- Cuidado Personal
- Niños
- Cocina
- Otros

LÓGICA DE PROPIETARIO (JUANA Y VICENTE):
- Si el objeto es de la categoría "Niños" (juguetes, ropa infantil, útiles escolares), analiza el contexto visual.
- Si parece pertenecer a una niña o tiene motivos asociados a Juana, etiqueta "Juana".
- Si parece pertenecer a un niño o tiene motivos asociados a Vicente, etiqueta "Vicente".
- IMPORTANTE: Solo asigna el propietario en 'tags_semanticos' si tienes al menos un 80% de confianza. Si no, usa el valor "General".

INSTRUCCIONES DE ANÁLISIS:
1. DESCRIPCIÓN ESPACIAL: Genera una descripción que complemente las coordenadas pos_x/y mediante lenguaje natural (ej: 'sobre el estante blanco', 'dentro del contenedor azul').
2. ATRIBUTOS TÉCNICOS: Identifica el color predominante, el material (madera, metal, etc.) y el estado (nuevo, usado, dañado).

FORMATO DE RESPUESTA (JSON):
{{
  "items": [
    {{
      "nombre": "nombre descriptivo",
      "categoria_principal": "Tecnología|Herramientas|Documentación|Cuidado Personal|Niños|Cocina|Otros",
      "descripcion": "Descripción del objeto + ubicación relativa en lenguaje natural",
      "bbox": [ymin, xmin, ymax, xmax],
      "confianza": 0.XX,
      "color_predominante": "color",
      "material": "material",
      "estado": "nuevo|usado|dañado",
      "tags_semanticos": "propietario:Juana|propietario:Vicente|propietario:General, palabra_clave1, palabra_clave2"
    }}
  ]
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
            logger.warning("[AI-SRE] Falla total de modelos o Rate Limit (429). Activando modo 'Pendiente'.")
            return {
                "items": [{
                    "nombre": "Objeto pendiente",
                    "categoria_principal": "Otros",
                    "descripcion": "El análisis de IA falló por límite de cuota o red. Procesamiento pendiente.",
                    "tags_semanticos": "propietario:General, pendiente:procesar"
                }],
                "tags": "pendiente:procesar",
                "analisis_espacial": {}
            }

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

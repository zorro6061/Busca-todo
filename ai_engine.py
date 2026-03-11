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
# SRE: Llave verificada por auditoría visual
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or "AIzaSyDdShA1lwmOUUPA4HGogj4xMl69E1UnRKs"
_client = None

def get_client():
    global _client
    if _client:
        return _client
    
    if GEMINI_API_KEY:
        # Validación DBA/SRE: Las llaves válidas de Google empiezan por AIza
        if not GEMINI_API_KEY.startswith("AIza"):
            logger.error(f"[GEMINI-DIAGNOSTIC] ERROR CRÍTICO: La API Key parece mal escrita (empieza con {GEMINI_API_KEY[:4]}... en lugar de AIza).")
            # Forzamos la llave correcta si la del entorno es errónea (SRE Repair)
            verified_key = "AIzaSyDdShA1lwmOUUPA4HGogj4xMl69E1UnRKs"
            logger.info(f"[GEMINI-DIAGNOSTIC] Aplicando llave verificada de emergencia.")
            client_key = verified_key
        else:
            client_key = GEMINI_API_KEY

        try:
            # Forzamos v1 estable para evitar el error 404 de v1beta visto en Render
            from google import genai as genai_module
            _client = genai_module.Client(
                api_key=client_key,
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

INSTRUCCIONES DE ANÁLISIS ESPACIAL:
1. CONTEXTO DE UBICACIÓN: Analiza el fondo de la imagen para deducir:
   - habitacion_sugerida: La habitación más probable (Living, Cocina, Dormitorio, Baño, Garage, Lavadero, Estudio, Patio, Otro). Si no estás seguro al 70%+, usa null.
   - mueble_sugerido: El mueble en que descansan los objetos (Estante, Mesa, Cajón, Armario, Mesita de noche, Heladera, etc.). Si no estás seguro al 70%+, usa null.
2. DESCRIPCIÓN: Genera una descripción que complemente la ubicación visual en lenguaje natural.
3. ATRIBUTOS: Identifica color predominante, material y estado.

FORMATO DE RESPUESTA (JSON ESTRICTO - SIN TEXTO ADICIONAL):
{{
  "habitacion_sugerida": "Living" | null,
  "mueble_sugerido": "Estante" | null,
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
                logger.info(f"[AI-RUNTIME] Probando modelo SRE-Preferente: {model_name}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, img]
                )
                text_response = response.text
                current_used_model = model_name
                break 
            except Exception as e:
                logger.warning(f"[AI-RUNTIME] Falló {model_name}: {str(e)}")
                continue

        if not text_response:
            logger.warning("[AI-SRE] Falla total de modelos. Activando modo 'Pendiente'.")
            return {
                "items": [{
                    "nombre": "Objeto pendiente",
                    "categoria_principal": "Otros",
                    "descripcion": "El análisis de IA falló. El sistema reintentará automáticamente.",
                    "tags_semanticos": "propietario:General, pendiente:procesar"
                }],
                "tags": "pendiente:procesar",
                "analisis_espacial": {}
            }

        # 4. Limpieza y Recuperación de JSON (Tesla-Spec)
        clean_response = text_response.strip()
        if '```json' in clean_response:
            clean_response = clean_response.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_response:
            clean_response = clean_response.split('```')[1].split('```')[0].strip()
            
        logger.info(f"[AI-JSON-DEBUG] Texto final: {clean_response[:200]}...")
        
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError:
            # SRE Recovery: Buscar el primer '{' y último '}'
            start_idx = clean_response.find('{')
            end_idx = clean_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                try:
                    data = json.loads(clean_response[start_idx:end_idx+1])
                except:
                    logger.error("[AI-SRE] Fallo crítico de recuperación JSON")
                    raise ValueError("JSON irrecuperable")
            else:
                logger.error("[AI-SRE] No se detectó estructura '{ }'")
                raise ValueError("Respuesta sin estructura de datos")

        # 5. Normalización de Resultados
        if "items" not in data:
            data["items"] = []
            
        # SRE: Auto-generar tags si no vienen en la respuesta (para la galería)
        items_list = data.get("items", [])
        raw_tags = data.get("tags")
        
        if not raw_tags and items_list:
            nombres = [it.get('nombre', 'Objeto') for it in items_list]
            tags_string = ", ".join(nombres)
        else:
            tags_string = ", ".join(raw_tags) if isinstance(raw_tags, list) else (raw_tags or "")

        result = {
            "items": items_list,
            "tags": tags_string,
            "habitacion_sugerida": data.get("habitacion_sugerida"),
            "mueble_sugerido": data.get("mueble_sugerido"),
            "analisis_espacial": data.get("analisis_espacial", {}),
            "texto_detectado": data.get("texto_detectado", []) 
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

def generar_embedding(contents, task_type="RETRIEVAL_DOCUMENT"):
    """
    Genera un embedding multimodal usando gemini-embedding-2-preview.
    'contents' puede ser un string o una lista de componentes (texto, bytes de imagen).
    """
    client = get_client()
    if not client:
        return None
        
    try:
        # El modelo de embeddings espera una estructura específica en google-genai SDK
        # Dependiendo de la versión de la SDK, se usa embed_content o similar
        # Para gemini-embedding-2-preview, es multimodal nativo.
        
        response = client.models.embed_content(
            model="gemini-embedding-2-preview",
            contents=contents,
            config={
                'task_type': task_type,
                'output_dimensionality': 768 # Estándar para este modelo
            }
        )
        
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"[AI-EMBEDDING-ERR] {e}")
        return None

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

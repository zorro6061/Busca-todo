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
            # La nueva SDK usa el cliente unificado (API v1 estable)
            from google import genai as genai_pkg
            _client = genai.Client(api_key=GEMINI_API_KEY)
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

        # 2. Prompt Maestro OmniVision
        prompt = f"""
CONTEXTO: Eres un experto en organización del hogar y gestión de pertenencias personales. Tu trabajo es ayudar a las personas a encontrar sus cosas en casa con máxima precisión.

TAREA: Analiza esta imagen de un espacio físico ({tipo_espacio}).

OBJETIVOS:
1. Identifica TODOS los objetos individuales visibles (no agrupes)
2. Para cada objeto, proporciona información completa y precisa
3. Usa categorización jerárquica (Principal > Subcategoría > Tipo Específico)
4. Detecta ubicación exacta con bounding box [ymin, xmin, ymax, xmax] (0-1000)
5. Analiza el contexto espacial del ambiente

FORMATO DE RESPUESTA (JSON ESTRICTO):
{{
  "items": [
    {{
      "nombre": "nombre descriptivo específico",
      "categoria_principal": "categoría base",
      "subcategoria": "subcategoría",
      "tipo_especifico": "especie exacta",
      "descripcion": "detalles visuales",
      "tags_semanticos": "10 palabras clave separadas por comas",
      "bbox": [ymin, xmin, ymax, xmax],
      "confianza": 0.XX,
      "metadata": {{
        "color_predominante": "...",
        "material": "...",
        "marca": "...",
        "estado": "..."
      }}
    }}
  ],
  "analisis_espacial": {{
    "tipo_espacio": "{tipo_espacio}",
    "organizacion": "ordenado|caótico|estantería",
    "densidad_objetos": "baja|media|alta",
    "total_objetos_estimado": N,
    "zonas_principales": []
  }},
  "tags": ["tag1", "tag2"]
}}
"""

        # 3. Ejecución con Fallback Dinámico y Logging Extendido
        model_primario = "gemini-1.5-flash"
        model_fallback = "gemini-1.5-pro"
        
        text_response = None
        current_used_model = model_primario
        
        try:
            logger.info(f"[AI-RUNTIME] Intentando con: {current_used_model}...")
            response = client.models.generate_content(
                model=current_used_model,
                contents=[prompt, img]
            )
            text_response = response.text
        except Exception as flash_err:
            logger.error(f"[AI-RUNTIME] Error en {current_used_model}: {str(flash_err)}")
            # Loguear detalles del error si están disponibles
            try:
                if hasattr(flash_err, 'response'):
                    logger.error(f"[AI-RUNTIME] Detalles del error (response): {flash_err.response}")
            except: pass

            logger.warning(f"[AI-RUNTIME] Escalando a modelo de respaldo: {model_fallback}...")
            current_used_model = model_fallback
            try:
                response = client.models.generate_content(
                    model=current_used_model,
                    contents=[prompt, img]
                )
                text_response = response.text
            except Exception as pro_err:
                logger.error(f"[AI-RUNTIME] Error crítico en fallback {current_used_model}: {str(pro_err)}")
                raise pro_err

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

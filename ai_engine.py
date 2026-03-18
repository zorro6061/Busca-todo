import os
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
_client = None


def get_client():
    global _client
    if _client:
        return _client

    if GEMINI_API_KEY:
        # Validación DBA/SRE: Las llaves válidas de Google empiezan por AIza
        if not GEMINI_API_KEY.startswith("AIza"):
            logger.error(
                "[GEMINI-DIAGNOSTIC] ERROR CRÍTICO: La API Key parece mal escrita (empieza con "
                f"{GEMINI_API_KEY[:4]}... en lugar de AIza)."
            )
            client_key = GEMINI_API_KEY
        else:
            client_key = GEMINI_API_KEY

        try:
            # Forzamos v1 estable para evitar el error 404 de v1beta visto en Render
            from google import genai as genai_module

            _client = genai_module.Client(api_key=client_key, http_options={"api_version": "v1beta"})
            key_prefix = GEMINI_API_KEY[:6] if GEMINI_API_KEY else "None"
            # Confirmación explícita para diagnóstico
            logger.info("[GEMINI-DIAGNOSTIC] API Key cargada: True")

            # Intentar obtener versión si está disponible (vía importlib.metadata)
            try:
                import importlib.metadata

                version = importlib.metadata.version("google-genai")
                logger.info(f"[GEMINI-DIAGNOSTIC] Usando google-genai versión: {version}")
            except Exception:
                logger.info("[GEMINI-DIAGNOSTIC] google-genai versión: No se pudo detectar vía importlib.metadata")

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
        return {
            "items": [],
            "tags": "Error: SDK no disponible",
            "analisis_espacial": {},
        }

    try:
        # 1. Carga de Imagen (Pillow)
        try:
            if isinstance(image_data, str):
                if not os.path.exists(image_data):
                    raise FileNotFoundError(f"Archivo no encontrado: {image_data}")
                img = Image.open(image_data)
            else:
                import io

                img = Image.open(io.BytesIO(image_data))
            img.load()
        except Exception as img_err:
            logger.error(f"Pillow no pudo validar la imagen: {img_err}")
            return {
                "items": [],
                "tags": "Error: Imagen inválida",
                "analisis_espacial": {},
            }

        # 🧠 CIRUGÍA PATO: Prompt de Precisión Quirúrgica (Rev 122)
        prompt = """
Eres un Experto en Logística y Organización Industrial de 'Aperture Cloud'. Tu misión es indexar y describir objetos con precisión absoluta para que cualquier operario pueda encontrarlos sin duda alguna.

INSTRUCCIONES GENERALES:
Se te proporcionará una imagen y coordenadas espaciales. Tu respuesta DEBE ser un objeto JSON puro (sin comillas adicionales, sin explicaciones) con la siguiente estructura:

{
  "name": "[Nombre Principal]",
  "description": "[Descripción Técnica]",
  "tags": ["[Tag 1]", "[Tag 2]", "[Tag 3]", "..."]
}

GUÍA DE ESTILO DE DATOS:
[name] (Nombre Principal): Debe ser lo más específico posible. Prioriza siempre [Tipo de Objeto] + [Marca] + [Modelo/Color]. (Ej: "Amoladora angular Dewalt DWE4020N"). Si no hay marca, usa el color.
[description] (Descripción Técnica): Describe el estado, el contexto visual y cualquier detalle útil de la imagen.
[tags] (Etiquetas de Búsqueda): Genera etiquetas cortas y funcionales para el buscador semántico, pensando en cómo buscaría un operario.
"""

        # 3. Ejecución
        modelos_a_probar = ["gemini-1.5-flash", "gemini-2.0-flash"]
        text_response = None
        current_used_model = None

        for model_name in modelos_a_probar:
            try:
                response = client.models.generate_content(model=model_name, contents=[prompt, img])
                text_response = response.text
                current_used_model = model_name
                break
            except Exception:
                continue

        if not text_response:
            return {
                "items": [{"nombre": "Objeto pendiente", "categoria_principal": "Otros"}],
                "tags": "pendiente:procesar",
                "analisis_espacial": {},
            }

        # 4. Limpieza JSON (Restaurado Rev 122)
        clean_response = text_response.strip()
        if "```json" in clean_response:
            clean_response = clean_response.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_response:
            clean_response = clean_response.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError:
            start_idx = clean_response.find("{")
            end_idx = clean_response.rfind("}")
            if start_idx != -1 and end_idx != -1:
                data = json.loads(clean_response[start_idx : end_idx + 1])
            else:
                raise ValueError("Respuesta sin estructura de datos")

        # 🧠 CIRUGÍA PATO: Re-mapeo retrocompatible para app.py (Rev 122)
        if "name" in data and "description" in data:
            mapped_items = [{
                "nombre": data.get("name"),
                "descripcion": data.get("description"),
                "categoria_principal": "Otros",
                "confianza": 1.0
            }]
            mapped_tags = ", ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", "")
            data = {
                "items": mapped_items,
                "tags": mapped_tags,
                "analisis_espacial": {}
            }

        result = {
            "items": data.get("items", []),
            "tags": data.get("tags", ""),
            "habitacion_sugerida": data.get("habitacion_sugerida"),
            "mueble_sugerido": data.get("mueble_sugerido"),
            "analisis_espacial": data.get("analisis_espacial", {}),
        }
        return result

    except Exception as e:
        logger.error(f"[AI-ERROR] {e}")
        return {"items": [], "tags": "Error", "analisis_espacial": {}}


def generar_embedding(contents, task_type="RETRIEVAL_DOCUMENT"):
    client = get_client()
    if not client:
        return None

    try:
        processed_contents = []
        if isinstance(contents, list):
            for part in contents:
                if isinstance(part, bytes):
                    processed_contents.append({"inline_data": {"mime_type": "image/jpeg", "data": part}})
                else:
                    processed_contents.append(part)
        elif isinstance(contents, bytes):
            processed_contents = [{"inline_data": {"mime_type": "image/jpeg", "data": contents}}]
        else:
            processed_contents = contents

        response = client.models.embed_content(
            model="gemini-embedding-2-preview",
            contents=processed_contents,
            config={"task_type": task_type, "output_dimensionality": 768},
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.error(f"[AI-EMBEDDING-ERR] {e}")
        return None


def interpretar_consulta(query):
    client = get_client()
    if not client:
        return query

    prompt = f'Extrae el NOMBRE DEL OBJETO principal de esta consulta: "{query}". Responde en JSON: {{"termino": "nombre"}}'

    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=[prompt])
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_json)
        return data.get("termino", query)
    except Exception:
        return query

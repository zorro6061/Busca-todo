import os
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
import json
import logging

load_dotenv()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def analizar_imagen_objetos(image_path, tipo_espacio="general"):
    """
    Usa Gemini Vision avanzado para identificar objetos en una imagen física.
    
    Args:
        image_path: Ruta a la imagen a analizar
        tipo_espacio: Tipo de espacio (garaje, cocina, oficina, etc.) para contexto
    
    Returns:
        dict: {
            "items": [...],  # Lista de objetos detectados con metadata completa
            "tags": str,  # Descripción del espacio
            "analisis_espacial": {...}  # Análisis del contexto espacial
        }
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY no configurada")
        return {
            "items": [], 
            "tags": "Error: API Key faltante",
            "analisis_espacial": {}
        }

    try:
        # Configurar modelos (Primario: Flash, Fallback: Pro)
        model_name = 'gemini-1.5-flash'
        model = genai.GenerativeModel(model_name)
        
        # Validar si el archivo existe
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado para IA: {image_path}")
            return {"items": [], "tags": "Error: Archivo no encontrado", "analisis_espacial": {}}

        try:
            img = Image.open(image_path)
            # Validar integridad mínima de la imagen
            img.verify() 
            img = Image.open(image_path) # Re-abrir después de verify()
        except Exception as img_err:
            logger.error(f"Pillow no pudo abrir la imagen {image_path}: {img_err}")
            return {"items": [], "tags": f"Error: Imagen corrupta o formato inválido ({img_err})", "analisis_espacial": {}}
        
        # Prompt mejorado con few-shot examples y chain-of-thought
        prompt = f"""
CONTEXTO: Eres un experto en organización del hogar y gestión de pertenencias personales. Tu trabajo es ayudar a las personas a encontrar sus cosas en casa con máxima precisión.

TAREA: Analiza esta imagen de un espacio físico ({tipo_espacio}).

OBJETIVOS:
1. Identifica TODOS los objetos individuales visibles (no agrupes)
2. Para cada objeto, proporciona información completa y precisa
3. Usa categorización jerárquica (Principal > Subcategoría > Tipo Específico)
4. Detecta ubicación exacta con bounding box
5. Analiza el contexto espacial del ambiente

═══════════════════════════════════════════════════════════════

EJEMPLO DE ANÁLISIS CORRECTO:

    "organizacion": "semi-ordenado",
    "densidad_objetos": "media",
    "total_objetos_estimado": 12,
    "zonas_principales": ["banco de trabajo", "estantería de herramientas"]
  }},
  "texto_detectado": [
    {{
      "texto": "Stanley",
      "tipo": "marca",
      "objeto_asociado": "destornillador phillips magnético stanley"
    }}
  ],
  "tags": ["herramientas manuales", "banco de trabajo", "garaje"]
}}

═══════════════════════════════════════════════════════════════

GUÍAS ESPECÍFICAS:

📦 DETECCIÓN DE OBJETOS:
- NO agrupes (ej: "3 destornilladores" → detecta cada uno individualmente)
- SÍ específico (ej: "destornillador" → "destornillador phillips #2 stanley")
- Si hay múltiples unidades idénticas juntas, puedes agrupar con "cantidad": N

🏷️ CATEGORIZACIÓN (jerárquica - 3 niveles):
Ejemplos de categorías:

Herramientas
├── Herramientas Manuales > Destornilladores
├── Herramientas Manuales > Martillos
├── Herramientas Manuales > Llaves
├── Herramientas Eléctricas > Taladros
├── Herramientas Eléctricas > Sierras
└── Medición > Metros/Niveles

Ferretería
├── Fijaciones > Tornillos
├── Fijaciones > Clavos
└── Adhesivos > Cintas

Electrónica
├── Cables > HDMI|USB|Cargadores
├── Multimedia > Controles|Audio|Pantallas
└── Computación > Laptops|Componentes

Oficina
├── Escritura > Bolígrafos|Lápices
├── Organización > Carpetas|Archivadores
└── Tecnología > Computadoras|Periféricos

Hogar
├── Cocina > Utensilios|Electrodomésticos|Vajilla
├── Limpieza > Productos|Herramientas (Escobas/Aspiradoras)
├── Living > Electrónica|Libros|Decoración
├── Habitación > Ropa|Accesorios|Calzado
└── Oficina > Papelería|Tecnología|Documentos

📐 BOUNDING BOX:
- Formato: [ymin, xmin, ymax, xmax] normalizado 0-1000
- Debe cubrir TODO el objeto completo
- No incluir sombras o reflejos
- Si parcialmente oculto: bbox solo parte visible

🎯 CALIBRACIÓN DE CONFIANZA (CRÍTICO):
- 0.95-1.0: Objeto claro, marca/modelo legible, sin ninguna ambigüedad
- 0.85-0.94: Objeto claro, tipo obvio, detalles parcialmente visibles
- 0.70-0.84: Objeto visible pero borroso, o categoría genérica
- 0.60-0.69: Objeto parcialmente oculto o categoría incierta
- < 0.60: NO reportar (muy incierto)

🎨 METADATA COMPLETA:
- color_predominante: Color principal del objeto
- colores_secundarios: Array de colores adicionales
- material: plástico|metal|madera|vidrio|tela|cartón|mixto
- marca: Marca visible (ej: "Stanley", "DeWalt", "Bosch")
- modelo: Modelo si es legible (ej: "DCD996", "XR20")
- estado: nuevo|usado|deteriorado|oxidado|roto
- cantidad: Número de unidades (si múltiples idénticas)
- tamano_estimado: pequeño|mediano|grande

📝 OCR (Texto visible):
- Detecta texto legible en etiquetas, marcas, seriales
- Asocia cada texto al objeto correspondiente
- Tipo: marca|modelo|serial|etiqueta|fecha

🏢 ANÁLISIS ESPACIAL:
- tipo_espacio: cocina|garaje|oficina|estante|caja|taller|etc
- organizacion: ordenado|semi-ordenado|caótico|estantería|cajones
- densidad_objetos: baja|media|alta
- total_objetos_estimado: Número aproximado total
- zonas_principales: Array de áreas destacadas

═══════════════════════════════════════════════════════════════

FORMATO DE RESPUESTA (JSON ESTRICTO):

{{
  "items": [
    {{
      "nombre": "...",
      "categoria_principal": "...",
      "subcategoria": "...",
      "tipo_especifico": "...",
      "descripcion": "...",
      "tags_semanticos": "10 palabras clave, sinónimos y usos separados por comas",
      "bbox": [ymin, xmin, ymax, xmax],
      "confianza": 0.XX,
      "metadata": {{
        "color_predominante": "...",
        "colores_secundarios": [...],
        "material": "...",
        "marca": "..." o null,
        "modelo": "..." o null,
        "estado": "...",
        "cantidad": N,
        "tamano_estimado": "..."
      }}
    }}
  ],
  "analisis_espacial": {{
    "tipo_espacio": "...",
    "organizacion": "...",
    "densidad_objetos": "...",
    "total_objetos_estimado": N,
    "zonas_principales": [...]
  }},
  "texto_detectado": [
    {{
      "texto": "...",
      "tipo": "...",
      "objeto_asociado": "..."
    }}
  ],
  "tags": ["tag1", "tag2", ...]
}}

═══════════════════════════════════════════════════════════════

IMPORTANTE:
✓ Sé específico (no genérico)
✓ Lee texto visible (marcas, modelos)
✓ Calibra confianza honestamente
✓ Bbox preciso (todo el objeto)
✓ Categorías jerárquicas consistentes
✓ Metadata completa siempre

¡ADELANTE! Analiza la imagen con máxima precisión.
"""

        logger.info(f"Analizando imagen: {image_path} (tipo: {tipo_espacio})")
        
        # Generar análisis con reintentos y fallback
        try:
            response = model.generate_content([prompt, img])
            # Forzar evaluación de la respuesta para capturar errores de seguridad o cuotas
            text_response = response.text
        except Exception as gen_err:
            logger.warning(f"Error con modelo {model_name}: {gen_err}. Intentando con fallback (pro).")
            # Fallback a Pro
            fallback_model = genai.GenerativeModel('gemini-1.5-pro')
            response = fallback_model.generate_content([prompt, img])
            text_response = response.text
        
        # Limpiar respuesta de bloques markdown
        clean_response = text_response.replace('```json', '').replace('```', '').strip()
        
        # Parsear JSON
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError:
            # Reintento simple: buscar el primer '{' y último '}' si el JSON está mal formado
            start_idx = clean_response.find('{')
            end_idx = clean_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                data = json.loads(clean_response[start_idx:end_idx+1])
            else:
                raise
        
        # Validar estructura básica
        if "items" not in data:
            logger.warning("Respuesta sin campo 'items', creando estructura vacía")
            data["items"] = []
        
        # Añadir campos por defecto si faltan
        result = {
            "items": data.get("items", []),
            "tags": ", ".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", ""),
            "analisis_espacial": data.get("analisis_espacial", {}),
            "texto_detectado": data.get("texto_detectado", [])
        }
        
        logger.info(f"Análisis completado: {len(result['items'])} objetos detectados")
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parseando JSON de respuesta de IA: {e}")
        logger.error(f"Respuesta recibida: {clean_response[:500]}...")
        return {
            "items": [],
            "tags": f"Error: Respuesta de IA en formato inválido",
            "analisis_espacial": {},
            "texto_detectado": []
        }
    except Exception as e:
        logger.error(f"Error en AI Engine: {type(e).__name__}: {e}")
        return {
            "items": [],
            "tags": f"Error procesando imagen: {str(e)}",
            "analisis_espacial": {},
            "texto_detectado": []
        }

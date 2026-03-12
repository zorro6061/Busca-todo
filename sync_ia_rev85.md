# Sincronización IA - Ctrl+F Físico (Revision 85)

Este documento centraliza el estado técnico y arquitectónico del proyecto para garantizar la consistencia en el desarrollo.

## 1. Modelos de Base de Datos (SQLAlchemy / PostgreSQL)

Estructura central del grafo de conocimiento físico:

- **Plano**: El contenedor raíz (Habitación/Galpón). Soporta `homografia_json` para proyecciones espaciales.
- **Ubicacion**: Una foto específica dentro de un plano (Cajón, Lado de la mesa). Incluye `embedding_json` (visual) y jerarquía semántica (`habitacion`, `mueble_texto`, `punto_especifico`).
- **Objeto**: El ítem individual detectado por IA. Vinculado a una `Ubicacion` y opcionalmente a una `Zona`. Incluye `tags_semanticos` y `embedding_json` para búsqueda vectorial.
- **Mueble**: Componente estructural del **Editor Modular**. Define volumen (`ancho`, `alto`, `profundidad`) y tipo (`estanteria`, `mesa`, `pared`).
- **Zona**: Región anotada en el plano que agrupa objetos.
- **User**: Gestión de usuarios (Google Auth) con flag de persistencia `has_seen_onboarding`.
- **Config**: Ajustes globales y llaves de API (Gemini).

## 2. Estructura de Proyecto

Resumen de la organización actual:

```text
/PROJECT_ROOT
│   app.py                  # Servidor Flask (Controlador central y rutas API)
│   models.py               # Definición de modelos SQLAlchemy
│   ai_engine.py            # Integración con Google Gemini (Vision & Embeddings)
│   storage_manager.py      # Puente hacia Google Cloud Storage (Bucket)
│   requirements.txt        # Dependencias (Flask, SQLAlchemy, Psycopg2, GenAI)
│   Dockerfile              # Configuración de contenedor para Cloud Run
│
├───static
│   ├───css
│   │       style.css       # Estética Revision 69 (Isometric UI, Glassmorphism)
│   └───js
│           main.js         # Lógica de cliente y manipulación del DOM
│
└───templates
        index.html          # Dashboard y Centro de Acción
        plano_view.html     # Visor de mapa interactivo con Hotspots
        plano_modular_editor.html # Configurador Drag & Snap con 3D soft
        video_scanner.html  # Interfaz de captura múltiple para IA
        upload.html         # Formulario de indexación con cámara directa
        layout.html         # Base template con navegación Aperture style
```

## 3. Resumen de Hitos (Rev 85)

Cosas que funcionan al 100%:

1.  **Infraestructura Cloud**: Migración completa a PostgreSQL (Render) y Google Cloud Storage. Deployment automatizado en Cloud Run.
2.  **Modular UI (Rev 69)**: Sistema de Drag & Drop magnético con renderizado isométrico y sombras premium.
3.  **Buscador Híbrido**: Búsqueda que combina texto, categorías y navegación visual por "Active Zones".
4.  **Onboarding Premium**: Flujo de bienvenida persistente con lógica de usuario y estética glassmorphism.
5.  **Cámara Nativa**: Optimización para móviles que fuerza la apertura de la cámara trasera en lugar de la galería.

## 4. Hoja de Ruta (Roadmap Rev 86+)

Próximas metas técnicas:

1.  **Precisión IA v2**: Mejorar la detección en puntos específicos (ej. identificar automáticamente si un objeto está en el "cajón izquierdo" vs "cajón derecho" mediante análisis espacial).
2.  **Inventario Modular**: Permitir asignar objetos masivamente a muebles específicos dentro del Editor Modular mediante drag-and-drop de ítems.
3.  **Optimización Estática**: Implementación de lazy loading para fotos maestras de alta resolución y compresión predictiva en el cliente (Worker).

---
*Documento generado para sincronización de contexto IA.*

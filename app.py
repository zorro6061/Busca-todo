import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from models import db, Ubicacion, Objeto, Plano, Config
from werkzeug.utils import secure_filename
from google import genai
from dotenv import load_dotenv

# Cargar variables de entorno al inicio (Fase 20)
load_dotenv()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# La configuración de Gemini se ha movido a ai_engine.py para usar la nueva SDK google-genai

app = Flask(__name__)
app.url_map.strict_slashes = False

# Configuración de Producción
app.debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance', 'ctrl_f.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads') 
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_ctrl_f_123456789')

db.init_app(app) # Registro obligatorio en el top-level

# DIAGNÓSTICO DE ARRANQUE (Visible en Gunicorn)
print(f"[VANGUARD-STARTUP] Cargando módulo app.py...")
print(f"[VANGUARD-STARTUP] Directorio actual: {os.getcwd()}")
port_env = os.environ.get('PORT')
print(f"[VANGUARD-STARTUP] Puerto detectado en entorno: {port_env or 'Default 5001'}")

@app.route('/alive')
def alive_check():
    return "Busca-todo Vanguard Engine: ONLINE", 200

@app.route('/debug-models')
def debug_models():
    """Endpoint temporal para diagnosticar modelos disponibles."""
    from ai_engine import get_client
    client = get_client()
    if not client:
        return jsonify({
            "error": "Cliente Gemini no inicializado (¿API_KEY faltante?)", 
            "key_prefix": f"{GEMINI_API_KEY[:6]}***" if GEMINI_API_KEY else "None"
        })
    
    try:
        models = client.models.list()
        model_list = []
        for m in models:
            model_list.append({
                "name": m.name,
                "display_name": getattr(m, 'display_name', 'N/A'),
                "modalities": getattr(m, 'input_modalities', []),
                "description": getattr(m, 'description', 'N/A')
            })
        return jsonify({
            "status": "Vanguard Diagnostic Active",
            "project_key_prefix": f"{GEMINI_API_KEY[:6]}***" if GEMINI_API_KEY else "None",
            "available_models": model_list
        })
    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc(),
            "key_prefix": f"{GEMINI_API_KEY[:6]}***" if GEMINI_API_KEY else "None"
        }), 500

@app.route('/debug-gemini')
def debug_gemini():
    """Diagnóstico definitivo para 404 NOT_FOUND y lista de modelos vacía."""
    from ai_engine import get_client
    import os
    import sys
    try:
        # 1. Info de Entorno
        env_info = {
            "python_version": sys.version,
            "api_key_loaded": bool(os.getenv("GEMINI_API_KEY")),
            "api_key_prefix": os.getenv("GEMINI_API_KEY")[:6] if os.getenv("GEMINI_API_KEY") else None,
            "flask_env": os.getenv("FLASK_ENV"),
            "port": os.getenv("PORT")
        }

        # 2. Verificación de Librería
        try:
            import importlib.metadata
            env_info["sdk_version"] = importlib.metadata.version("google-genai")
        except:
            env_info["sdk_version"] = "unknown"

        client = get_client()
        if not client:
            return jsonify({
                "status": "error",
                "message": "Cliente no inicializado",
                "env": env_info
            }), 500
            
        # 3. Prueba de Listado
        try:
            models_iter = client.models.list()
            model_names = [m.name for m in models_iter]
            env_info["models_count"] = len(model_names)
            env_info["models_available"] = model_names
        except Exception as list_err:
            env_info["list_error"] = str(list_err)

        # 4. PRUEBA DE FALLBACK (Direct Access)
        try:
            # Forzamos una generación ligera para probar si el acceso directo funciona aunque el listado falle
            test_resp = client.models.generate_content(
                model='gemini-1.5-flash',
                contents="test"
            )
            env_info["direct_access_test"] = "SUCCESS"
        except Exception as e:
            env_info["direct_access_test"] = f"FAILED: {str(e)}"

        # 4. PRUEBA DE ESTABILIDAD (v1 vs v1beta)
        try:
            # El cliente ya está forzado a v1 en ai_engine.py
            test_resp = client.models.generate_content(
                model='gemini-1.5-flash',
                contents="test"
            )
            env_info["v1_stable_test"] = "SUCCESS"
        except Exception as e:
            env_info["v1_stable_test"] = f"FAILED: {str(e)}"

        return jsonify({
            "status": "diagnostic_ready",
            "env": env_info,
            "recommendation": "Si v1_stable_test falla con NOT_FOUND, debes ACTIVAR la API aquí: https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com"
        })

    except Exception as e:
        import traceback
        return jsonify({
            "status": "fatal_error",
            "error_type": type(e).__name__,
            "error_full": str(e),
            "traceback": traceback.format_exc()
        })
# Asegurar que las carpetas necesarias existan
instance_path = os.path.join(basedir, 'instance')
for folder in [app.config['UPLOAD_FOLDER'], instance_path]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def save_and_compress_image(file_storage, folder, filename, max_width=1920, quality=85):
    """Guarda y comprime una imagen para optimizar espacio y velocidad. Soporta HEIC."""
    from PIL import Image
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass

    temp_path = os.path.join(folder, f"temp_{filename}")
    file_storage.save(temp_path)
    
    try:
        with Image.open(temp_path) as img:
            # Convertir a RGB si es necesario (ej: de RGBA o HEIC)
            if img.mode in ("RGBA", "P") or filename.lower().endswith(('.heic', '.heif')):
                img = img.convert("RGB")
            
            # Cambiar tamaño manteniendo aspecto si es más grande que max_width
            if img.width > max_width:
                img.thumbnail((max_width, max_width), Image.Resampling.LANCZOS)
            
            # Forzar extensión .jpg para consistencia si es necesario
            final_filename = filename
            if filename.lower().endswith(('.heic', '.heif')):
                final_filename = filename.rsplit('.', 1)[0] + ".jpg"
                
            final_path = os.path.join(folder, final_filename)
            img.save(final_path, "JPEG", quality=quality, optimize=True)
        
        # Eliminar temporal
        os.remove(temp_path)
        return final_filename
    except Exception as e:
        app.logger.error(f"Error comprimiendo imagen: {e}")
        # Si falla el procesamiento, intentar mover el original como fallback
        import shutil
        shutil.move(temp_path, os.path.join(folder, filename))
        return filename

# --- INICIO DEL MOTOR VANGUARD (Safe Boot) ---
_initialized = False

@app.before_request
def initialize_vanguard():
    # BYPASS CRÍTICO: No bloquear el chequeo de salud de Render
    if request.path == '/alive':
        return
        
    global _initialized
    if not _initialized:
        try:
            with app.app_context():
                print("[VANGUARD-STARTUP] Ejecutando db.create_all()...")
                db.create_all()
                
                from sqlalchemy import text
                # Migraciones Manuales (Safe Mode)
                migraciones = [
                    ('ALTER TABLE muebles ADD COLUMN nombre VARCHAR(100) DEFAULT "Mueble Sin Nombre"', "muebles_nombre"),
                    ('ALTER TABLE objetos ADD COLUMN tags_semanticos TEXT', "objetos_tags"),
                    ('ALTER TABLE ubicaciones ADD COLUMN items_json TEXT', "ubicaciones_json"),
                    ('ALTER TABLE objetos RENAME COLUMN categoria TO categoria_principal', "obj_rename_cat"),
                    ('ALTER TABLE objetos ADD COLUMN categoria_principal VARCHAR(50)', "obj_add_cat_fallback")
                ]

                for sql, label in migraciones:
                    try:
                        db.session.execute(text(sql))
                        db.session.commit()
                        print(f"[DB-MIGRATE] {label} OK")
                    except Exception:
                        db.session.rollback()

                # Columnas adicionales
                columnas_nuevas = [
                    ('objetos', 'categoria_secundaria', 'VARCHAR(50)'),
                    ('objetos', 'descripcion', 'TEXT'),
                    ('objetos', 'color_predominante', 'VARCHAR(30)'),
                    ('objetos', 'material', 'VARCHAR(50)'),
                    ('objetos', 'estado', 'VARCHAR(50)'),
                    ('objetos', 'prioridad', 'VARCHAR(20)')
                ]
                
                for tabla, col, tipo in columnas_nuevas:
                    try:
                        db.session.execute(text(f'ALTER TABLE {tabla} ADD COLUMN {col} {tipo}'))
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
            
            print("[VANGUARD-STARTUP] HEARTBEAT: Vanguard initialized.")
            _initialized = True
        except Exception as boot_err:
            print(f"[VANGUARD-STARTUP] ERROR CRÍTICO EN BOOT: {boot_err}")
            # No bloqueamos el arranque global para que Render detecte el puerto
            _initialized = True 

print("[VANGUARD-STARTUP] Módulo app.py cargado (Ready for Port Scan).")

import base64
import uuid

# Rutas para PWA (Servir desde raíz para máximo alcance)
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.errorhandler(404)
def handle_404(e):
    """Manejador centralizado de 404 con diagnóstico de logs."""
    app.logger.warning(f"[404-DIAGNOSTIC] Ruta no encontrada: {request.path} | Method: {request.method}")
    return render_template('404.html'), 404

@app.route('/')
def index():
    from sqlalchemy import func
    ubicaciones_count = Ubicacion.query.count()
    objetos_count = Objeto.query.count()
    
    # Categorías únicas y confianza promedio (Eficiente)
    categorias_count = 0
    avg_conf = 0
    
    try:
        # Contar categorías únicas directamente en SQL
        categorias_count = db.session.query(func.count(func.distinct(Objeto.categoria_principal))).scalar() or 0
        
        # Calcular promedio directamente en SQL
        if objetos_count > 0:
            avg_conf = db.session.query(func.avg(Objeto.confianza)).scalar() or 0
            avg_conf = int(avg_conf * 100)
    except Exception as e:
        app.logger.warning(f"Error en dashboard stats: {e}")
    
    ultima_ubi = Ubicacion.query.order_by(Ubicacion.id.desc()).first()
    
    return render_template('index.html', 
                         plano_count=Plano.query.count(),
                         obj_count=objetos_count, 
                         cat_count=categorias_count,
                         avg_conf=avg_conf,
                         ultima_ubi=ultima_ubi)

@app.after_request
def add_cache_control(response):
    """Optimización de cache para archivos estáticos."""
    if request.path.startswith('/static/'):
        response.cache_control.max_age = 31536000  # 1 año
        response.cache_control.public = True
    return response

# Error handler 500 consolidado abajo

@app.errorhandler(500)
def internal_server_error(e):
    import traceback
    app.logger.error(f"Error 500: {str(e)}\n{traceback.format_exc()}")
    db.session.rollback()
    return render_template('500.html'), 500

@app.context_processor
def inject_config():
    try:
        config = Config.query.first()
        if not config:
            print("Creating default config...")
            config = Config(subscription_type='free')
            db.session.add(config)
            db.session.commit()
        return dict(app_config=config)
    except Exception as e:
        print(f"ERROR IN INJECT_CONFIG: {e}")
        return dict(app_config={'subscription_type': 'free'})

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')

@app.route('/upgrade')
def upgrade():
    plan = request.args.get('plan', 'free')
    config = Config.query.first()
    if config:
        config.subscription_type = plan
        db.session.commit()
        flash(f'¡Bienvenido al plan {plan.upper()}! Todas las funciones premium han sido activadas.')
    return redirect(url_for('index'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No hay archivo')
            return redirect(request.url)
        
        file = request.files['file']
        nombre_ubicacion = request.form.get('nombre_ubicacion', 'Sin nombre')
        
        if file.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)
        
        if file:
            try:
                filename = secure_filename(file.filename)
                # La compresión puede cambiar el nombre (ej: .heic -> .jpg)
                filename = save_and_compress_image(file, app.config['UPLOAD_FOLDER'], filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                
                ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                
                # Motor de Video OmniVision
                if ext in ['mp4', 'mov', 'avi']:
                    from video_processor import extraer_fotogramas
                    from ai_engine import analizar_imagen_objetos
                    
                    frames = extraer_fotogramas(filepath, app.config['UPLOAD_FOLDER'])
                    for i, frame_filename in enumerate(frames):
                        frame_path = os.path.join(app.config['UPLOAD_FOLDER'], frame_filename)
                        resultado = analizar_imagen_objetos(frame_path)
                        
                        nueva_ubi = Ubicacion(
                            nombre=f"{nombre_ubicacion} (Puntual {i+1})", 
                            imagen_path=frame_filename,
                            tags=resultado.get('tags', '')
                        )
                        db.session.add(nueva_ubi)
                        db.session.flush()

                        for item in resultado.get('items', []):
                            nuevo_obj = Objeto(
                                nombre=item.get('nombre', 'Objeto detectado'),
                                categoria_principal=item.get('categoria_principal', 'General'),
                                categoria_secundaria=item.get('subcategoria', ''),
                                confianza=item.get('confianza', 0.8),
                                ubicacion_id=nueva_ubi.id,
                                tags_semanticos=item.get('tags_semanticos', '')
                            )
                            db.session.add(nuevo_obj)
                    
                    db.session.commit()
                    flash(f'OmniVision procesó el video. Se crearon {len(frames)} espacios automáticamente.')
                    return redirect(url_for('gallery'))
                
                else:
                    # Procesamiento de imagen estándar con IA mejorada
                    from ai_engine import analizar_imagen_objetos
                    import json
                    
                    resultado = analizar_imagen_objetos(filepath, tipo_espacio="general")
                    
                    # Crear ubicación con datos mejorados
                    nueva_ubicacion = Ubicacion(
                        nombre=nombre_ubicacion, 
                        imagen_path=filename,
                        tags=resultado.get('tags', ''),
                        items_json=json.dumps(resultado.get('items', []))  # JSON completo con metadata
                    )
                    db.session.add(nueva_ubicacion)
                    db.session.flush() # Flush para obtener ID
                    
                    # Crear objetos con categorización mejorada
                    for item in resultado.get('items', []):
                        # Categoría jerárquica
                        categoria_completa = item.get('categoria_principal', '')
                        if item.get('subcategoria'):
                            categoria_completa += f" > {item['subcategoria']}"
                        
                        if not categoria_completa:
                            categoria_completa = item.get('categoria', 'General')
                        
                        # Tags semánticos pre-generados
                        tags_semanticos = item.get('tags_semanticos', '')

                        nuevo_objeto = Objeto(
                            nombre=item.get('nombre', 'Objeto detectado'),
                            categoria_principal=item.get('categoria_principal', 'General'),
                            categoria_secundaria=item.get('subcategoria', ''),
                            descripcion=item.get('descripcion', ''),
                            confianza=item.get('confianza', 0.8),
                            ubicacion_id=nueva_ubicacion.id,
                            tags_semanticos=tags_semanticos
                        )
                        db.session.add(nuevo_objeto)
                    
                    db.session.commit()
                    flash(f'✓ "{nombre_ubicacion}" blindado con éxito. {len(resultado.get("items", []))} objetos indexados.')
                    return redirect(url_for('gallery'))

            except Exception as e:
                import traceback
                error_details = traceback.format_exc()
                app.logger.error(f"FALLO CRÍTICO EN UPLOAD:\n{error_details}")
                db.session.rollback()
                flash('⚠️ Error procesando la imagen o video. Verifique que no sea demasiado pesado o inválido.')
                return redirect(request.url)
            
    return render_template('upload.html')

@app.route('/gallery')
def gallery():
    ubicaciones = Ubicacion.query.order_by(Ubicacion.fecha_creacion.desc()).all()
    return render_template('gallery.html', ubicaciones=ubicaciones)

@app.route('/search')
def search():
    import json
    from rapidfuzz import fuzz, process
    
    query = request.args.get('q', '').lower().strip()
    resultados = []
    
    if query:
        # Obtener TODOS los objetos para fuzzy search
        todos_objetos = Objeto.query.all()
        
        # Búsqueda mejorada con ponderación de algoritmos
        candidatos = []
        
        for obj in todos_objetos:
            nombre_lower = obj.nombre.lower()
            categoria_lower = (obj.categoria_principal or "").lower()
            
            # 1. Similitud exacta (Ratio) - PESO MAYOR
            ratio_nombre = fuzz.ratio(query, nombre_lower)
            ratio_categoria = fuzz.ratio(query, categoria_lower)
            
            # 2. Búsqueda parcial (Partial Ratio) - para queries cortas
            partial_nombre = fuzz.partial_ratio(query, nombre_lower)
            partial_categoria = fuzz.partial_ratio(query, categoria_lower)
            
            # 3. Token Sort Ratio - para orden de palabras
            token_nombre = fuzz.token_sort_ratio(query, nombre_lower)
            token_categoria = fuzz.token_sort_ratio(query, categoria_lower)
            
            # PONDERACIÓN: Dar más peso a ratio exacto
            # Si ratio es alto (>75), úsalo directo
            # Si ratio es bajo pero partial es alto, penalizar un poco
            max_ratio = max(ratio_nombre, ratio_categoria)
            max_partial = max(partial_nombre, partial_categoria)
            max_token = max(token_nombre, token_categoria)
            
            # Calcular score ponderado
            if max_ratio >= 75:
                # Match exacto fuerte - usar directo
                final_score = max_ratio
            elif max_token >= 80:
                # Token match fuerte (orden insensible)
                final_score = max_token
            elif max_partial >= 85 and len(query) >= 4:
                # Partial match solo si query es suficientemente larga
                final_score = max_partial * 0.9  # Penalizar ligeramente
            else:
                # Tomar el mejor pero con umbral más alto
                final_score = max(max_ratio, max_token)
            
            # UMBRALES MÁS ESTRICTOS:
            # - 75%+ para matches normales
            # - 85%+ para partial matches
            if final_score >= 75:
                candidatos.append((obj, final_score))
        
        # Ordenar por score (mayor primero)
        candidatos.sort(key=lambda x: x[1], reverse=True)
        
        # Procesar resultados (máximo 30 para evitar saturación)
        for obj, score in candidatos[:30]:
            # Buscar bbox en items_json original
            bbox = None
            try:
                if obj.ubicacion.items_json:
                    items_originales = json.loads(obj.ubicacion.items_json)
                    for item in items_originales:
                        if item.get('nombre', '').lower() == obj.nombre.lower():
                            bbox = item.get('bbox')
                            break
            except Exception as e:
                app.logger.error(f"Error parseando items_json: {e}")
            
            resultados.append({
                'id': obj.id,
                'objeto': obj.nombre,
                'categoria_principal': obj.categoria_principal,
                'categoria_secundaria': obj.categoria_secundaria,
                'descripcion': obj.descripcion,
                'material': obj.material,
                'estado': obj.estado,
                'prioridad': obj.prioridad,
                'confianza': obj.confianza,
                'ubicacion': obj.ubicacion.nombre,
                'ubicacion_id': obj.ubicacion.id,
                'plano_id': obj.ubicacion.plano_id,
                'imagen': obj.ubicacion.imagen_path,
                'timestamp': obj.fecha_indexado.strftime('%Y-%m-%d %H:%M'),
                'bbox': bbox,
                'score': score
            })
    
    return render_template('search_results.html', query=query, resultados=resultados)

@app.route('/api/sugerencias')
def sugerencias():
    """API para auto-complete con fuzzy matching mejorado"""
    from rapidfuzz import process, fuzz
    
    query = request.args.get('q', '').lower().strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    # Obtener nombres únicos de objetos y categorías
    nombres_set = set()
    objetos = Objeto.query.all()
    for obj in objetos:
        nombres_set.add(obj.nombre.capitalize())
        if obj.categoria_principal:
            nombres_set.add(obj.categoria_principal.capitalize())
    
    opciones = list(nombres_set)
    
    # Usar RapidFuzz process.extract para top matches
    # scorer=fuzz.token_sort_ratio para mejor matching de palabras
    resultados = process.extract(
        query,
        opciones,
        scorer=fuzz.token_sort_ratio,
        limit=10,
        score_cutoff=60
    )
    
    # Formatear resultados: [(texto, score, index), ...]
    sugerencias_list = [
        {
            'texto': match[0],
            'score': int(match[1])
        }
        for match in resultados
    ]
    
    return jsonify(sugerencias_list)

@app.route('/planos')
def list_planos():
    planos = Plano.query.all()
    return render_template('planos.html', planos=planos)

@app.route('/plano/nuevo', methods=['GET', 'POST'])
def nuevo_plano():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        file = request.files.get('file')
        drawing_data = request.form.get('drawing_data')
        
        filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            save_and_compress_image(file, app.config['UPLOAD_FOLDER'], filename)
        elif drawing_data:
            # Procesar imagen del canvas (base64)
            try:
                header, encoded = drawing_data.split(",", 1)
                data = base64.b64decode(encoded)
                filename = f"plano_{uuid.uuid4().hex[:8]}.png"
                with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), "wb") as f:
                    f.write(data)
            except Exception as e:
                flash(f"Error al guardar el dibujo: {e}")
                return redirect(request.url)
        
        if filename:
            nuevo = Plano(nombre=nombre, imagen_path=filename)
            db.session.add(nuevo)
            db.session.commit()
            flash(f'Plano "{nombre}" creado con éxito.')
            return redirect(url_for('list_planos'))
            
    return render_template('plano_form.html')

@app.route('/plano/eliminar/<int:plano_id>', methods=['POST'])
def eliminar_plano(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    nombre = plano.nombre
    
    # Desvincular ubicaciones (opción: borrarlas o dejarlas sin plano)
    for ubi in plano.ubicaciones:
        ubi.plano_id = None
        ubi.pos_x = None
        ubi.pos_y = None
    
    # Intentar borrar el archivo físico
    if plano.imagen_path:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], plano.imagen_path))
        except:
            pass
            
    db.session.delete(plano)
    db.session.commit()
    flash(f'Plano "{nombre}" eliminado correctamente.')
    return redirect(url_for('list_planos'))

@app.route('/plano/<int:plano_id>')
def ver_plano(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    ubicaciones_sin_plano = Ubicacion.query.filter_by(plano_id=None).all()
    # Ubicaciones del plano sin posición (ej: del Video Scanner)
    ubicaciones_sin_posicion = Ubicacion.query.filter(
        Ubicacion.plano_id == plano_id,
        (Ubicacion.pos_x == None) | (Ubicacion.pos_y == None)
    ).all()
    # Preparar PINS (Ubicaciones con posición)
    pins_data = []
    for ubi in plano.ubicaciones:
        if ubi.pos_x is not None and ubi.pos_y is not None:
            # Incluir objetos con sus posiciones relativas si existen
            obj_list = []
            for obj in ubi.objetos:
                obj_list.append({
                    'id': obj.id,
                    'nombre': obj.nombre,
                    'x': obj.pos_x,
                    'y': obj.pos_y,
                    'categoria': obj.categoria_principal
                })
                
            pins_data.append({
                'id': ubi.id,
                'nombre': ubi.nombre,
                'x': ubi.pos_x,
                'y': ubi.pos_y,
                'tags': ubi.tags,
                'objetos_count': len(ubi.objetos),
                'objetos': obj_list,
                'imagen_path': ubi.imagen_path
            })
            
    # Preparar UNPLACED (Ubicaciones sin posición en este plano)
    unplaced_data = []
    for ubi in ubicaciones_sin_posicion:
        unplaced_data.append({
            'id': ubi.id,
            'nombre': ubi.nombre,
            'objetos_count': len(ubi.objetos),
            'imagen_path': ubi.imagen_path
        })

    return render_template('plano_view.html', 
                         plano=plano, 
                         pins=pins_data,
                         unplaced=unplaced_data,
                         ubicaciones_sin_plano=ubicaciones_sin_plano)

    return jsonify({'status': 'error', 'message': 'Ubicación no encontrada'}), 404

@app.route('/api/plano/<int:plano_id>/save_pins', methods=['POST'])
def save_pin_positions(plano_id):
    """Guarda las posiciones de múltiples pines a la vez"""
    data = request.json
    pins = data.get('pins', [])
    try:
        for p in pins:
            ubi = Ubicacion.query.get(p['id'])
            if ubi:
                ubi.plano_id = plano_id
                ubi.pos_x = p['x']
                ubi.pos_y = p['y']
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/analizar_foto', methods=['POST'])
def analizar_foto():
    """Analiza una foto sin crear la ubicación todavía, para permitir edición previa"""
    try:
        file = request.files.get('file')
        if not file:
            return jsonify({'status': 'error', 'message': 'No se recibió imagen'}), 400
        
        filename = secure_filename(file.filename)
        save_and_compress_image(file, app.config['UPLOAD_FOLDER'], filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Analizar con IA mejorada
        from ai_engine import analizar_imagen_objetos
        resultado = analizar_imagen_objetos(filepath, tipo_espacio="general")
        
        # Retornar resultado completo con metadata enriquecida
        return jsonify({
            'status': 'success',
            'items': resultado.get('items', []),
            'filename': filename,
            'analisis_espacial': resultado.get('analisis_espacial', {}),
            'texto_detectado': resultado.get('texto_detectado', [])
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/calibrar_plano', methods=['POST'])
def calibrar_plano():
    """Calcula y guarda la matriz de homografía para un plano"""
    try:
        data = request.json
        plano_id = data.get('plano_id')
        src_pts = data.get('src_pts') # 4 puntos en imagen [[x,y], ...]
        dst_pts = data.get('dst_pts') # 4 puntos en mapa [[x,y], ...]
        
        if not plano_id or not src_pts or not dst_pts:
            return jsonify({'status': 'error', 'message': 'Datos incompletos'}), 400
            
        plano = Plano.query.get(plano_id)
        if not plano:
            return jsonify({'status': 'error', 'message': 'Plano no encontrado'}), 404
            
        from spatial_engine import SpatialEngine, serialize_h
        import json
        
        # Calcular Homografía
        H = SpatialEngine.solve_homography(src_pts, dst_pts)
        
        # Guardar en el plano
        plano.homografia_json = json.dumps(serialize_h(H))
        db.session.commit()
        
        return jsonify({'status': 'success', 'message': 'Calibración guardada'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/crear_ubicacion_en_mapa', methods=['POST'])
def crear_ubicacion_en_mapa():
    """Crear una nueva ubicación directamente desde el mapa con foto y posición"""
    try:
        nombre = request.form.get('nombre', 'Nuevo Espacio')
        plano_id = request.form.get('plano_id')
        pos_x = request.form.get('pos_x')
        pos_y = request.form.get('pos_y')
        pos_z = request.form.get('pos_z', 0)
        temp_filename = request.form.get('temp_filename')
        objetos_json = request.form.get('objetos_finales')
        file = request.files.get('file')
        
        filename = None
        if file:
            filename = secure_filename(file.filename)
            if not filename:
                filename = f"ubicacion_{uuid.uuid4().hex[:8]}.jpg"
            save_and_compress_image(file, app.config['UPLOAD_FOLDER'], filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        elif temp_filename:
            filename = temp_filename
            
        if not filename:
             return jsonify({'status': 'error', 'message': 'No se recibió imagen'}), 400
        
        # Crear ubicación con posición
        nueva_ubicacion = Ubicacion(
            nombre=nombre,
            imagen_path=filename,
            tags="", # Se llenará después
            plano_id=int(plano_id) if plano_id else None,
            pos_x=int(pos_x) if pos_x else None,
            pos_y=int(pos_y) if pos_y else None,
            pos_z=int(pos_z) if pos_z else 0,
            items_json=objetos_json  # NUEVO: Guardar JSON con bboxes
        )
        db.session.add(nueva_ubicacion)
        db.session.flush()
        
        # Procesar objetos (pueden venir del editor o de un análisis directo)
        objetos_finales = []
        if objetos_json:
            import json
            objetos_finales = json.loads(objetos_json)
        else:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            from ai_engine import analizar_imagen_objetos
            resultado = analizar_imagen_objetos(filepath, tipo_espacio="general")
            objetos_finales = resultado.get('items', [])

        # Preparar proyección espacial (Homografía)
        h_matrix = None
        if plano_id:
            plano = Plano.query.get(plano_id)
            if plano and plano.homografia_json:
                from spatial_engine import SpatialEngine, deserialize_h
                try:
                    h_matrix = deserialize_h(json.loads(plano.homografia_json))
                except Exception as e:
                    app.logger.error(f"Error deserializando homografía: {e}")

        # Crear objetos asociados con categorización mejorada
        nombres_para_tags = []
        for item in objetos_finales:
            # ... (se mantiene categorización anterior)
            categoria_completa = item.get('categoria_principal', '')
            if 'subcategoria' in item:
                categoria_completa += f" > {item['subcategoria']}"
            if 'tipo_especifico' in item:
                categoria_completa += f" > {item['tipo_especifico']}"
            
            if not categoria_completa:
                categoria_completa = item.get('categoria', 'General')
            
            # PROYECCIÓN ESPACIAL
            obj_pos_x = None
            obj_pos_y = None
            
            bbox = item.get('bbox') # [ymin, xmin, ymax, xmax]
            if h_matrix is not None and bbox:
                from spatial_engine import SpatialEngine
                anchor = SpatialEngine.get_object_anchor(bbox) # (x, y) en imagen
                # Proyectar punto de imagen -> mapa
                proj_x, proj_y = SpatialEngine.project_point(h_matrix, anchor)
                obj_pos_x = proj_x
                obj_pos_y = proj_y
            else:
                # Fallback: Usar la posición del Pin general si no hay homografía
                obj_pos_x = float(pos_x) if pos_x else None
                obj_pos_y = float(pos_y) if pos_y else None

            nuevo_objeto = Objeto(
                nombre=item.get('nombre', 'Objeto detectado'),
                categoria_principal=categoria_completa,
                confianza=item.get('confianza', 0.8),
                estado=item.get('metadata', {}).get('estado', item.get('estado', 'N/A')),
                prioridad=item.get('prioridad', 'media'),
                ubicacion_id=nueva_ubicacion.id,
                pos_x=obj_pos_x,
                pos_y=obj_pos_y
            )
            db.session.add(nuevo_objeto)
            nombres_para_tags.append(item.get('nombre', 'Objeto'))
            
        nueva_ubicacion.tags = ", ".join(nombres_para_tags)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'ubicacion_id': nueva_ubicacion.id,
            'nombre': nueva_ubicacion.nombre,
            'objetos_detectados': len(objetos_finales)
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/plano/<int:plano_id>/upload_simple', methods=['POST'])
def upload_plano_simple(plano_id):
    """Sube una foto directamente a un plano sin posición inicial (aparecerá en la barra lateral)"""
    plano = Plano.query.get_or_404(plano_id)
    nombre = request.form.get('nombre', 'Nuevo Espacio')
    file = request.files.get('file')
    
    if file and file.filename != '':
        filename = secure_filename(file.filename)
        save_and_compress_image(file, app.config['UPLOAD_FOLDER'], filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Analizar con IA
        from ai_engine import analizar_imagen_objetos
        resultado = analizar_imagen_objetos(filepath)
        
        nueva_ubi = Ubicacion(
            nombre=nombre,
            imagen_path=filename,
            plano_id=plano_id,
            tags=resultado.get('tags', '')
        )
        db.session.add(nueva_ubi)
        db.session.flush()
        
        # Crear objetos
        for item in resultado.get('items', []):
            nuevo_obj = Objeto(
                nombre=item.get('nombre', 'Objeto'),
                categoria_principal=item.get('categoria', 'General'),
                confianza=item.get('confianza', 0.8),
                ubicacion_id=nueva_ubi.id
            )
            db.session.add(nuevo_obj)
            
        db.session.commit()
        flash(f'Espacio "{nombre}" indexado y añadido al directorio del plano.')
    
    return redirect(url_for('ver_plano', plano_id=plano_id))

@app.route('/plano/editar/<int:plano_id>', methods=['GET', 'POST'])
def editar_plano(plano_id):
    """Editar un plano existente con el canvas de dibujo"""
    plano = Plano.query.get_or_404(plano_id)
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', plano.nombre)
        drawing_data = request.form.get('drawing_data')
        
        if drawing_data:
            # Procesar base64 y guardar nueva imagen
            image_data = drawing_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
            
            # Eliminar imagen anterior
            if plano.imagen_path:
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], plano.imagen_path))
                except:
                    pass
            
            # Guardar nueva imagen
            filename = f"plano_edit_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(image_bytes)
            
            plano.nombre = nombre
            plano.imagen_path = filename
            db.session.commit()
            flash(f'Plano "{nombre}" actualizado con éxito.')
            return redirect(url_for('ver_plano', plano_id=plano.id))
    
    return render_template('plano_edit.html', plano=plano)

@app.route('/ai-optimizer')
def ai_optimizer():
    from ai_engine import client
    
    objetos = Objeto.query.all()
    if not objetos:
        return render_template('ai_optimizer.html', tips="Todavía no he analizado suficientes objetos para optimizar tu espacio.")
    
    # Crear un resumen para la IA
    resumen = []
    for obj in objetos:
        resumen.append(f"- {obj.nombre} (Categoría: {obj.categoria_principal or 'General'}) en {obj.ubicacion.nombre}")
    
    resumen_texto = "\n".join(resumen)
    
    # Llamada a Gemini para consejos pro usando la nueva SDK
    tips_html = "<p>Error consultando al cerebro maestro. Intentá más tarde.</p>"
    if client:
        try:
            prompt = f"""
            Eres un experto en ingeniería de espacios y organización doméstica. 
            Basado en este inventario detectado por mi sistema de visión, dame 3 consejos de "Ingeniería de Élite" para organizar mi casa y ahorrar tiempo.
            
            Inventario:
            {resumen_texto}
            
            Responde en formato HTML sencillo (solo tags <p>, <ul>, <li>) con un tono profesional y motivador.
            """
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            tips_html = response.text
        except Exception as e:
            app.logger.error(f"Error en AI Optimizer: {e}")
            
    return render_template('ai_optimizer.html', tips=tips_html)

# --- API Búsqueda en Mapa (Ctrl+F Físico) ---
@app.route('/api/buscar_en_mapa')
def buscar_en_mapa():
    """Busca ubicaciones y objetos dentro de un plano específico"""
    from rapidfuzz import fuzz
    
    query = request.args.get('q', '').lower().strip()
    plano_id = request.args.get('plano_id', type=int)
    
    if not query or len(query) < 2 or not plano_id:
        return jsonify([])
    
    # Obtener ubicaciones del plano
    ubicaciones = Ubicacion.query.filter_by(plano_id=plano_id).all()
    
    resultados = []
    
    for ubi in ubicaciones:
        if ubi.pos_x is None or ubi.pos_y is None:
            continue
        
        # Busca-todo Home - v1.0.7 Semantic Intelligence Vanguard
        score_ubi = max(
            fuzz.ratio(query, ubi.nombre.lower()),
            fuzz.partial_ratio(query, ubi.nombre.lower()),
            fuzz.token_sort_ratio(query, ubi.nombre.lower())
        )
        
        # Buscar en objetos de esta ubicación
        objetos_match = []
        max_obj_score = 0
        
        # Análisis Semántico (Intent Expansion) con la nueva SDK
        expanded_queries = [query]
        if GEMINI_API_KEY:
            try:
                from ai_engine import client
                if client:
                    exp_prompt = f"Actúa como un buscador semántico. Para la consulta '{query}', devuelve una lista de 5 objetos o categorías relacionadas que el usuario podría estar buscando. Responde solo las palabras separadas por comas."
                    exp_res = client.models.generate_content(
                        model='gemini-1.5-flash',
                        contents=exp_prompt
                    )
                    expanded_queries.extend([x.strip().lower() for x in exp_res.text.split(',')])
            except Exception as e:
                app.logger.error(f"Error en expansión semántica: {e}")

        for q_expanded in expanded_queries:
            for obj in ubi.objetos:
                score_obj = max(
                    fuzz.ratio(q_expanded, obj.nombre.lower()),
                    fuzz.partial_ratio(q_expanded, obj.nombre.lower()),
                    fuzz.token_sort_ratio(q_expanded, obj.nombre.lower())
                )
                
                # Buscar en tags semánticos (VANGUARD)
                if obj.tags_semanticos:
                    score_semantico = fuzz.partial_ratio(q_expanded, obj.tags_semanticos.lower())
                    score_obj = max(score_obj, score_semantico)

                if obj.categoria_principal:
                    score_cat = fuzz.partial_ratio(q_expanded, obj.categoria_principal.lower())
                    score_obj = max(score_obj, score_cat)
                
                if score_obj > 70:
                    objetos_match.append({
                        "id": obj.id,
                        "nombre": obj.nombre,
                        "score": score_obj,
                        "es_semantico": q_expanded != query # Marcar si fue hallado por IA
                    })
                    max_obj_score = max(max_obj_score, score_obj)
        
        # Score final: el mejor entre ubicación y sus objetos
        final_score = max(score_ubi, max_obj_score)
        
        if final_score >= 55:
            # Ordenar objetos por score
            objetos_match.sort(key=lambda x: x['score'], reverse=True)
            
            resultados.append({
                'ubi_id': ubi.id,
                'nombre': ubi.nombre,
                'pos_x': ubi.pos_x,
                'pos_y': ubi.pos_y,
                'score': int(final_score),
                'tipo_match': 'ubicacion' if score_ubi >= max_obj_score else 'objeto',
                'objetos_match': objetos_match[:3]  # Top 3 objetos
            })
    
    # Ordenar por score y limitar
    resultados.sort(key=lambda x: x['score'], reverse=True)
    return jsonify(resultados[:10])

# --- VIDEO SCANNER ---
@app.route('/video_scanner/<int:plano_id>', methods=['GET', 'POST'])
def video_scanner(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    step = 1
    frames = []
    
    if request.method == 'POST':
        file = request.files.get('video')
        if file:
            # Guardar video y procesar
            video_filename = f"video_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
            file.save(video_path)
            
            from video_processor import extraer_fotogramas
            frame_filenames = extraer_fotogramas(video_path, app.config['UPLOAD_FOLDER'])
            
            # Analizar frames
            from ai_engine import analizar_imagen_objetos
            for f_name in frame_filenames:
                f_path = os.path.join(app.config['UPLOAD_FOLDER'], f_name)
                res = analizar_imagen_objetos(f_path)
                frames.append({
                    'path': f_name,
                    'objects': res.get('items', [])
                })
            
            # Guardar frames en archivo temporal (evitar cookie overflow)
            import json
            from flask import session
            temp_frames_file = f"frames_{uuid.uuid4().hex}.json"
            temp_frames_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_frames_file)
            
            with open(temp_frames_path, 'w') as f:
                json.dump(frames, f)
                
            session['temp_frames_file'] = temp_frames_file
            step = 3
            
    return render_template('video_scanner.html', plano=plano, step=step, frames=frames)

@app.route('/api/plano/<int:plano_id>/save_video_scans', methods=['POST'])
def save_video_scans(plano_id):
    """Guarda las escenas seleccionadas del video como nuevas ubicaciones"""
    from flask import session
    import json
    data = request.json
    indices = data.get('indices', [])
    
    # Recuperar frames del archivo temporal
    temp_file = session.get('temp_frames_file')
    frames = []
    
    if temp_file:
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_file)
        if os.path.exists(temp_path):
            with open(temp_path, 'r') as f:
                frames = json.load(f)
            # Limpiar archivo después de uso
            # os.remove(temp_path) # Comentado para debug por ahora
            
    try:
        for idx in indices:
            if idx < len(frames):
                frame = frames[idx]
                nueva_ubi = Ubicacion(
                    nombre=f"Escena {idx + 1}",
                    imagen_path=frame['path'],
                    plano_id=plano_id,
                    tags=", ".join([obj['nombre'] for obj in frame['objects']])
                )
                db.session.add(nueva_ubi)
                db.session.flush()
                
                for obj in frame['objects']:
                    nuevo_obj = Objeto(
                        nombre=obj['nombre'],
                        categoria_principal=obj.get('categoria', 'General'),
                        confianza=obj.get('confianza', 0.8),
                        ubicacion_id=nueva_ubi.id
                    )
                    db.session.add(nuevo_obj)
        
        db.session.commit()
        db.session.commit()
        
        # Limpiar sesión y archivo
        if temp_file:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], temp_file))
            except:
                pass
        session.pop('temp_frames_file', None)
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/video/procesar', methods=['POST'])
def procesar_video():
    """Recibe un video, extrae frames y analiza cada uno con IA"""
    import json
    try:
        file = request.files.get('video')
        plano_id = request.form.get('plano_id')
        intervalo = int(request.form.get('intervalo', 3))
        
        if not file:
            return jsonify({'status': 'error', 'message': 'No se recibió video'}), 400
        
        # Guardar video temporalmente
        video_filename = f"video_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video_filename)
        file.save(video_path)
        
        # Extraer fotogramas
        from video_processor import extraer_fotogramas
        frames = extraer_fotogramas(video_path, app.config['UPLOAD_FOLDER'], intervalo_segundos=intervalo)
        
        if not frames:
            os.remove(video_path)
            return jsonify({'status': 'error', 'message': 'No se pudieron extraer frames del video'}), 400
        
        # Preparar proyección espacial (Homografía)
        h_matrix = None
        if plano_id:
            plano = Plano.query.get(plano_id)
            if plano and plano.homografia_json:
                from spatial_engine import SpatialEngine, deserialize_h
                try:
                    h_matrix = deserialize_h(json.loads(plano.homografia_json))
                except Exception as e:
                    app.logger.error(f"Error deserializando homografía en video: {e}")

        # Analizar cada frame con IA y aplicar estabilización (Tracking)
        from ai_engine import analizar_imagen_objetos
        from stabilization_engine import SimpleTracker
        
        # Inicializar tracker con parámetros optimizados para mobile (alpha=0.6 para suavizado)
        tracker = SimpleTracker(max_age=3, min_hits=1, alpha=0.6)
        escenas = []
        
        for i, frame_filename in enumerate(frames):
            frame_path = os.path.join(app.config['UPLOAD_FOLDER'], frame_filename)
            
            try:
                resultado = analizar_imagen_objetos(frame_path, tipo_espacio="general")
                items_raw = resultado.get('items', [])
                
                # Estabilizar detecciones (Transformar raw detections a tracks suavizados)
                # Formatear para el tracker
                detecciones_formateadas = []
                for item in items_raw:
                    if 'bbox' in item:
                        detecciones_formateadas.append({
                            'bbox': item['bbox'],
                            'nombre': item.get('nombre', 'Objeto'),
                            'confianza': item.get('confianza', 0.8),
                            'metadata': item.get('metadata', {})
                        })
                
                # El tracker actualiza su estado interno y devuelve tracks activos
                tracks_estabilizados = tracker.update(detecciones_formateadas)
                
                # Re-formatear tracks estabilizados para la respuesta final
                items_finales = []
                for track in tracks_estabilizados:
                    # PROYECCIÓN ESPACIAL PARA CADA TRACK
                    track_pos_x = None
                    track_pos_y = None
                    
                    if h_matrix is not None and 'bbox' in track:
                        from spatial_engine import SpatialEngine
                        anchor = SpatialEngine.get_object_anchor(track['bbox'])
                        proj_x, proj_y = SpatialEngine.project_point(h_matrix, anchor)
                        track_pos_x = proj_x
                        track_pos_y = proj_y

                    items_finales.append({
                        'id': track['id'],
                        'nombre': track['label'],
                        'bbox': track['bbox'],
                        'confianza': track['confianza'],
                        'metadata': track['metadata'],
                        'categoria_principal': track['metadata'].get('categoria_principal', 'General'),
                        'pos_x': track_pos_x,
                        'pos_y': track_pos_y
                    })

                escenas.append({
                    'frame_index': i + 1,
                    'filename': frame_filename,
                    'imagen_url': f'/uploads/{frame_filename}',
                    'objetos': items_finales,
                    'total_objetos': len(items_finales),
                    'nombre_sugerido': f'Escena {i + 1}',
                    'seleccionada': len(items_finales) > 0
                })
            except Exception as e:
                app.logger.error(f"Error analizando frame {i}: {e}")
                escenas.append({
                    'frame_index': i + 1,
                    'filename': frame_filename,
                    'imagen_url': f'/uploads/{frame_filename}',
                    'objetos': [],
                    'total_objetos': 0,
                    'nombre_sugerido': f'Escena {i + 1}',
                    'seleccionada': False,
                    'error': str(e)
                })
        
        # Limpiar video original (frames ya guardados)
        try:
            os.remove(video_path)
        except:
            pass
        
        return jsonify({
            'status': 'success',
            'total_frames': len(frames),
            'escenas': escenas
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/video/crear_ubicaciones', methods=['POST'])
def crear_ubicaciones_desde_video():
    """Crea múltiples ubicaciones a partir de escenas aprobadas del video"""
    import json
    try:
        data = request.json
        plano_id = data.get('plano_id')
        escenas = data.get('escenas', [])
        
        if not plano_id or not escenas:
            return jsonify({'status': 'error', 'message': 'Datos insuficientes'}), 400
        
        ubicaciones_creadas = []
        
        for escena in escenas:
            nombre = escena.get('nombre', 'Escena sin nombre')
            filename = escena.get('filename')
            objetos_list = escena.get('objetos', [])
            
            if not filename:
                continue
            
            # Crear ubicación (sin posición, el usuario la arrastrará en el mapa)
            nueva_ubi = Ubicacion(
                nombre=nombre,
                imagen_path=filename,
                tags="",
                plano_id=int(plano_id),
                items_json=json.dumps(objetos_list)
            )
            db.session.add(nueva_ubi)
            db.session.flush()
            
            # Crear objetos asociados
            nombres_tags = []
            for item in objetos_list:
                categoria = item.get('categoria_principal', item.get('categoria', 'General'))
                nuevo_obj = Objeto(
                    nombre=item.get('nombre', 'Objeto'),
                    categoria_principal=categoria,
                    confianza=item.get('confianza', 0.8),
                    estado=item.get('estado', 'N/A'),
                    prioridad=item.get('prioridad', 'media'),
                    ubicacion_id=nueva_ubi.id
                )
                db.session.add(nuevo_obj)
                nombres_tags.append(item.get('nombre', 'Objeto'))
            
            nueva_ubi.tags = ", ".join(nombres_tags)
            ubicaciones_creadas.append({
                'id': nueva_ubi.id,
                'nombre': nombre,
                'objetos': len(objetos_list)
            })
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'ubicaciones_creadas': len(ubicaciones_creadas),
            'detalle': ubicaciones_creadas
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- API Muebles 3D ---
@app.route('/api/plano/<int:plano_id>/muebles')
def get_muebles(plano_id):
    from models import Mueble
    muebles = Mueble.query.filter_by(plano_id=plano_id).all()
    return jsonify([{
        'id': m.id,
        'nombre': m.nombre,
        'tipo': m.tipo,
        'pos_x': m.pos_x,
        'pos_y': m.pos_y,
        'pos_z': m.pos_z,
        'ancho': m.ancho,
        'alto': m.alto,
        'profundidad': m.profundidad,
        'rotacion_y': m.rotacion_y,
        'color': m.color,
        'estantes': m.estantes,
        'material': m.material
    } for m in muebles])

@app.route('/api/mueble/crear', methods=['POST'])
def crear_mueble():
    from models import Mueble
    data = request.json
    try:
        nuevo = Mueble(
            plano_id=data['plano_id'],
            nombre=data.get('nombre', f"{data['tipo'].capitalize()} {Mueble.query.count() + 1}"),
            tipo=data['tipo'],
            pos_x=0, pos_y=0, pos_z=0, # Centro por defecto
            ancho=data.get('ancho', 10),
            alto=data.get('alto', 10),
            profundidad=data.get('profundidad', 10),
            color=data.get('color', '#6366f1'),
            estantes=data.get('estantes', 1),
            material=data.get('material', 'madera')
        )
        db.session.add(nuevo)
        db.session.commit()
        return jsonify({
            'status': 'success', 
            'id': nuevo.id, 
            'nombre': nuevo.nombre,
            'mensaje': 'Mueble creado',
            'estantes': nuevo.estantes,
            'material': nuevo.material
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/mueble/actualizar', methods=['POST'])
def actualizar_mueble():
    from models import Mueble
    data = request.json
    try:
        m = Mueble.query.get(data['id'])
        if not m:
            return jsonify({'status': 'error', 'message': 'Mueble no encontrado'}), 404
            
        if 'pos_x' in data: m.pos_x = data['pos_x']
        if 'pos_y' in data: m.pos_y = data['pos_y']
        if 'pos_z' in data: m.pos_z = data['pos_z']
        if 'rotacion_y' in data: m.rotacion_y = data['rotacion_y']
        
        # Propiedades Extendidas
        if 'ancho' in data: m.ancho = data['ancho']
        if 'alto' in data: m.alto = data['alto']
        if 'profundidad' in data: m.profundidad = data['profundidad']
        if 'color' in data: m.color = data['color']
        if 'estantes' in data: m.estantes = data['estantes']
        if 'material' in data: m.material = data['material']
        if 'nombre' in data: m.nombre = data['nombre']
        
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/mueble/<int:mueble_id>', methods=['DELETE'])
def borrar_mueble(mueble_id):
    from models import Mueble
    try:
        m = Mueble.query.get(mueble_id)
        if m:
            db.session.delete(m)
            db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/ar-view')
def ar_view():
    return render_template('ar_view.html')

@app.route('/plano/<int:plano_id>/3d')
def ver_plano_3d(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    return render_template('plano_3d.html', plano=plano)

@app.route('/api/ubicacion/actualizar_posicion', methods=['POST'])
def actualizar_posicion_ubicacion():
    from models import Ubicacion
    data = request.json
    try:
        ubi = Ubicacion.query.get(data['id'])
        if not ubi:
            return jsonify({'status': 'error', 'message': 'Ubicación no encontrada'}), 404
        
        ubi.pos_x = data.get('pos_x', ubi.pos_x)
        ubi.pos_y = data.get('pos_y', ubi.pos_y)
        ubi.pos_z = data.get('pos_z', ubi.pos_z)
        
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/ubicaciones/<int:ubi_id>/full', methods=['GET'])
def get_ubicacion_full(ubi_id):
    from models import Ubicacion, Zona, Objeto # Added imports for the new function
    import json # Added import for json
    try:
        ubi = Ubicacion.query.get_or_404(ubi_id)
        zonas = Zona.query.filter_by(plano_id=ubi.plano_id).all()
        
        objetos_data = []
        for obj in ubi.objetos:
            objetos_data.append({
                'id': obj.id,
                'nombre': obj.nombre,
                'categoria_principal': obj.categoria_principal,
                'zona_id': obj.zona_id
            })
            
        zonas_data = []
        for z in zonas:
            zonas_data.append({
                'id': z.id,
                'nombre': z.nombre,
                'color': z.color
            })
            
        return jsonify({
            'status': 'success',
            'ubicacion': {
                'id': ubi.id,
                'nombre': ubi.nombre,
                'imagen_url': url_for('uploaded_file', filename=ubi.imagen_path) if ubi.imagen_path else None
            },
            'objetos': objetos_data,
            'zonas_disponibles': zonas_data
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- API ZONAS (MAPA ANOTADO) ---

@app.route('/plano/<int:plano_id>/editor')
def editor_plano(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    return render_template('editor_plano.html', plano=plano)

@app.route('/api/plano/<int:plano_id>/save_zonas', methods=['POST'])
def save_zonas(plano_id):
    """Guarda/Actualiza todas las zonas de un plano (reemplazo total)"""
    from models import Zona
    data = request.json
    zonas_data = data.get('zonas', [])
    try:
        # Borrar zonas actuales para este plano (reemplazo total para simplificar editor)
        Zona.query.filter_by(plano_id=plano_id).delete()
        
        for z in zonas_data:
            nueva = Zona(
                nombre=z['nombre'],
                color=z['color'],
                tipo='rect', # Por ahora solo rectangulares en el editor premium
                coords_json=json.dumps({'x': z['x'], 'y': z['y'], 'w': z['w'], 'h': z['h']}),
                plano_id=plano_id
            )
            db.session.add(nueva)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/planos/<int:plano_id>/zonas', methods=['GET'])
def get_zonas_plano(plano_id):
    try:
        zonas = Zona.query.filter_by(plano_id=plano_id).all()
        return jsonify([{
            'id': z.id,
            'nombre': z.nombre,
            'tipo': z.tipo,
            'coords': json.loads(z.coords_json),
            'color': z.color,
            'objetos_count': len(z.objetos)
        } for z in zonas])
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/zonas', methods=['POST'])
def crear_zona():
    try:
        data = request.json
        nueva_zona = Zona(
            nombre=data.get('nombre', 'Zona Nueva'),
            tipo=data.get('tipo', 'rect'),
            coords_json=json.dumps(data.get('coords')),
            color=data.get('color', '#6366f1'),
            plano_id=data.get('plano_id')
        )
        db.session.add(nueva_zona)
        db.session.commit()
        return jsonify({'status': 'success', 'id': nueva_zona.id, 'message': 'Zona creada'})
    except Exception as e:
        print(f"Error creando zona: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/zonas/<int:zona_id>', methods=['PUT'])
def actualizar_zona(zona_id):
    try:
        zona = Zona.query.get_or_404(zona_id)
        data = request.json
        if 'nombre' in data: zona.nombre = data['nombre']
        if 'coords' in data: zona.coords_json = json.dumps(data['coords'])
        if 'color' in data: zona.color = data['color']
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Zona actualizada'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/zonas/<int:zona_id>', methods=['DELETE'])
def eliminar_zona(zona_id):
    try:
        zona = Zona.query.get_or_404(zona_id)
        db.session.delete(zona)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Zona eliminada'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/objetos/<int:obj_id>/asignar_zona', methods=['POST'])
def asignar_zona_objeto(obj_id):
    try:
        obj = Objeto.query.get_or_404(obj_id)
        zona_id = request.json.get('zona_id')
        
        if zona_id:
            zona = Zona.query.get_or_404(zona_id)
            obj.zona_id = zona.id
        else:
            obj.zona_id = None # Desasignar
            
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Objeto asignado a zona'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    # Usar el puerto de la variable de entorno PORT para Render
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=False, host='0.0.0.0', port=port)

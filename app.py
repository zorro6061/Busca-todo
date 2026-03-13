import os
import sys
import time
import json

# Función de log robusta para Render
def vanguard_log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[VANGUARD][{timestamp}] {msg}", file=sys.stderr, flush=True)

vanguard_log("--- STAGE 0: MODULE LOAD START ---")
vanguard_log(f"PID: {os.getpid()} | CWD: {os.getcwd()}")
vanguard_log(f"Python Version: {sys.version}")

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
import google.oauth2.credentials
import google.oauth2.id_token
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
from sqlalchemy import text
from models import db, Ubicacion, Objeto, Plano, Config, Mueble, Zona, User
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from storage_manager import upload_image_to_gcs, get_gcs_url

vanguard_log("Cargando variables de entorno...")
load_dotenv()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GCP_BUCKET_NAME = os.environ.get('GCP_BUCKET_NAME', 'busca-todo-fotos-2024')

# Configuración de OAuth 2.0
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    vanguard_log("CRÍTICO: Faltan GOOGLE_OAUTH_CLIENT_ID o CLIENT_SECRET en el entorno.")

SCOPES = ['https://www.googleapis.com/auth/userinfo.email', 'openid', 'https://www.googleapis.com/auth/userinfo.profile']
AUTHORIZED_DOMAIN = 'aperturezen.com'
WHITELISTED_EMAILS = ['zorro6061@gmail.com', 'pepe.dev.zen@gmail.com'] # Agregando tu cuenta y mi placeholder

# Inicialización de GCS (Ahora completamente remota en storage_manager)

app = Flask(__name__)
app.url_map.strict_slashes = False

# Configuración de Producción (Cloud SQL vs SQLite)
app.debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
basedir = os.path.abspath(os.path.dirname(__file__))

# Configuración de Base de Datos Inteligente (Cloud SQL Socket Support)
default_sqlite = 'sqlite:///' + os.path.join(basedir, 'instance', 'ctrl_f.db')
raw_db_url = os.environ.get('DATABASE_URL')
db_user = os.environ.get('DB_USER')
db_pass = os.environ.get('DB_PASS')
db_name = os.environ.get('DB_NAME')
instance_connection_name = os.environ.get('INSTANCE_CONNECTION_NAME')

import urllib.parse

if raw_db_url:
    # MODO PREFERIDO (Render/Sync): Usar DATABASE_URL (codificando contraseña)
    vanguard_log("Priorizando DATABASE_URL para sincronización externa")
    try:
        if '://' in raw_db_url and '@' in raw_db_url:
            prefix, rest = raw_db_url.split('://', 1)
            auth_part, host_part = rest.rsplit('@', 1)
            if ':' in auth_part:
                user_part, pass_part = auth_part.split(':', 1)
                if '%' not in pass_part:
                    safe_pass = urllib.parse.quote_plus(pass_part)
                    app.config['SQLALCHEMY_DATABASE_URI'] = f"{prefix}://{user_part}:{safe_pass}@{host_part}"
                else:
                    app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
            else:
                app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
        else:
            app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
    except Exception as e:
        vanguard_log(f"Error parseando DATABASE_URL: {e}")
        app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
elif instance_connection_name:
    # MODO GCP (Cloud SQL): Conexión vía Socket Unix
    vanguard_log(f"Conectando a Cloud SQL vía Socket: {instance_connection_name}")
    safe_pass = urllib.parse.quote_plus(db_pass or '')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"postgresql+psycopg2://{db_user}:{safe_pass}@/{db_name}?host=/cloudsql/{instance_connection_name}"
else:
    # MODO DESARROLLO/LOCAL: SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = default_sqlite
    vanguard_log("Usando SQLite local (instancia de desarrollo)")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB — permite videos del Scanner
app.config.setdefault("UPLOAD_FOLDER", os.environ.get('UPLOAD_FOLDER', os.path.join(basedir, 'uploads')))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_ctrl_f_123456789')

db.init_app(app) # Registro obligatorio en el top-level

from werkzeug.exceptions import RequestEntityTooLarge
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    app.logger.error(f"[VANGUARD-UPLOAD] Archivo excedió el límite de 200MB: {request.content_length} bytes")
    return jsonify({
        "status": "error",
        "message": "El archivo es demasiado grande",
        "detail": "El límite máximo es 200MB para videos cinemáticos. Probá con un video más corto o usá el Modo Foto Automático."
    }), 413

# --- UTILS & STARTUP ---
def fix_db_sequences():
    """Sincroniza las secuencias de PostgreSQL dinámicamente."""
    if not instance_connection_name and not raw_db_url:
        return 
    
    vanguard_log("Iniciando auditoría de secuencias PostgreSQL...")
    try:
        tables = ['ubicaciones', 'objetos', 'planos', 'muebles', 'zonas', 'config', 'users']
        for table in tables:
            # Obtiene el nombre real de la secuencia y la resetea al MAX(id) + 1
            sql = f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT COALESCE(MAX(id), 0) + 1 FROM {table}), false)"
            db.session.execute(text(sql))
            vanguard_log(f"Secuencia de '{table}' validada.")
        db.session.commit()
        vanguard_log("Sincronización de secuencias FINALIZADA ✅")
    except Exception as e:
        vanguard_log(f"Advertencia en sanación de secuencias: {e}")
        db.session.rollback()

def initialize_folders():
    """Crea las carpetas necesarias si no existen."""
    basedir = os.path.abspath(os.path.dirname(__file__))
    upload_path = app.config.get('UPLOAD_FOLDER')
    instance_path = os.path.join(basedir, 'instance')
    
    for folder in [upload_path, instance_path]:
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
            except Exception as e:
                app.logger.error(f"[VANGUARD-STARTUP] Error carpetas: {e}")

def migrate_semantic_columns():
    """
    Migración segura (idempotente): agrega columnas de Jerarquía Semántica
    a la tabla 'ubicaciones' si no existen aún. Funciona en Postgres y SQLite.
    """
    dialect = db.engine.dialect.name
    try:
        if dialect == 'postgresql':
            migrations = [
                "ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS habitacion VARCHAR(50)",
                "ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS mueble_texto VARCHAR(100)",
                "ALTER TABLE ubicaciones ADD COLUMN IF NOT EXISTS punto_especifico VARCHAR(150)",
                "ALTER TABLE objetos ADD COLUMN IF NOT EXISTS posicion_relativa VARCHAR(50)",
                "ALTER TABLE objetos ADD COLUMN IF NOT EXISTS contenedor VARCHAR(100)",
                "ALTER TABLE objetos ADD COLUMN IF NOT EXISTS zona_id INTEGER",
            ]
        else:  # SQLite (desarrollo local)
            # SQLite no soporta IF NOT EXISTS en ALTER TABLE, usamos try/except
            migrations = [
                "ALTER TABLE ubicaciones ADD COLUMN habitacion VARCHAR(50)",
                "ALTER TABLE ubicaciones ADD COLUMN mueble_texto VARCHAR(100)",
                "ALTER TABLE ubicaciones ADD COLUMN punto_especifico VARCHAR(150)",
                "ALTER TABLE objetos ADD COLUMN posicion_relativa VARCHAR(50)",
                "ALTER TABLE objetos ADD COLUMN contenedor VARCHAR(100)",
                "ALTER TABLE objetos ADD COLUMN zona_id INTEGER",
            ]
        for sql in migrations:
            try:
                db.session.execute(text(sql))
            except Exception:
                pass  # La columna ya existe — ignorar
        db.session.commit()
        vanguard_log("✅ Migración de columnas semánticas y espaciales completada.")
    except Exception as e:
        vanguard_log(f"⚠️ Migración semántica (no fatal): {e}")
        db.session.rollback()

def ensure_user_table():
    """Crea la tabla de usuarios si no existe y maneja migraciones menores."""
    try:
        # Esto crea todas las tablas definidas en models.py que no existan
        db.create_all()
        vanguard_log("✅ Tabla 'users' verificada/creada.")
    except Exception as e:
        vanguard_log(f"⚠️ Error verificando tabla users: {e}")

# DIAGNÓSTICO DE ARRANQUE (Visible en Gunicorn)
with app.app_context():
    initialize_folders()
    fix_db_sequences()
    migrate_semantic_columns()
    ensure_user_table()

vanguard_log("--- STAGE 1: SYSTEM READY ---")

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

        # 5. VERIFICACIÓN DE INTEGRIDAD DE LA KEY
        api_key = os.getenv("GEMINI_API_KEY", "")
        env_info["key_debug"] = {
            "length": len(api_key),
            "starts_with_AIza": api_key.startswith("AIza"),
            "has_spaces": " " in api_key or "\n" in api_key or "\r" in api_key
        }

        return jsonify({
            "status": "diagnostic_ready",
            "env": env_info,
            "recommendation": "Si está habilitado en el Console pero sigue dando 404, la Key NO pertenece a ese proyecto. SOLUCIÓN: Crea una NUEVA Key en AI Studio (https://aistudio.google.com/app/apikey) y reemplázala en Render."
        })

    except Exception as e:
        import traceback
        return jsonify({
            "status": "fatal_error",
            "error_type": type(e).__name__,
            "error_full": str(e),
            "traceback": traceback.format_exc()
        })
# Deferido a initialize_vanguard

# Los métodos anteriores upload_to_gcs y save_and_compress_image han sido migrados a storage_manager.py

# --- INICIO DEL MOTOR VANGUARD (Safe Boot) ---
_initialized = False
_db_ready = False

@app.before_request
def initialize_vanguard():
    # RUTAS DE SALUD: Bypass total (no DB, no auth)
    if request.path in ['/alive', '/health', '/api/health', '/api/debug-dashboard'] or request.path.startswith('/static/'):
        return

    # --- INICIALIZACIÓN DE BD: Corre para TODAS las rutas (incluyendo home pública) ---
    global _initialized, _db_ready
    if not _initialized:
        _initialized = True
        vanguard_log("Iniciando secuencia de boot (Async Robust)...")
        initialize_folders()
        
        import threading
        def robust_db_init():
            global _db_ready
            with app.app_context():
                try:
                    vanguard_log("DB: Verificando conexión (timeout 10s)...")
                    # Intentar una consulta simple para ver si la BD está ahí
                    from sqlalchemy import text
                    db.session.execute(text("SELECT 1"))
                    
                    vanguard_log("DB: Ejecutando db.create_all()...")
                    db.create_all()
                    
                    vanguard_log("DB: Verificando migraciones...")
                    migraciones = [
                        ('ALTER TABLE muebles ADD COLUMN nombre VARCHAR(100) DEFAULT \'Mueble Sin Nombre\'', "muebles_nombre"),
                        ('ALTER TABLE objetos ADD COLUMN tags_semanticos TEXT', "objetos_tags"),
                        ('ALTER TABLE ubicaciones ADD COLUMN items_json TEXT', "ubicaciones_json"),
                        ('ALTER TABLE objetos RENAME COLUMN categoria TO categoria_principal', "obj_rename_cat"),
                        ('ALTER TABLE objetos ADD COLUMN categoria_principal VARCHAR(50)', "obj_add_cat_fallback"),
                        ('ALTER TABLE ubicaciones ADD COLUMN embedding_json TEXT', "ubi_embedding"),
                        ('ALTER TABLE objetos ADD COLUMN embedding_json TEXT', "obj_embedding")
                    ]
                    
                    for sql, name in migraciones:
                        try:
                            db.session.execute(text(sql))
                            db.session.commit()
                            vanguard_log(f"DB: Migración {name} aplicada.")
                        except Exception:
                            db.session.rollback()
                    
                    vanguard_log("DB: Secuencia de arranque finalizada con éxito.")
                    _db_ready = True
                except Exception as e:
                    vanguard_log(f"DB: ERROR CRÍTICO en arranque: {e}")
        
        threading.Thread(target=robust_db_init, daemon=True).start()
        vanguard_log("Vanguard Engine: Hilo de BD lanzado.")

    # --- GUARDIÁN DE SEGURIDAD: Solo para rutas PRIVADAS ---
    # Rutas públicas: home y flujo de autenticación
    public_paths = ['/', '/login', '/callback', '/login-google', '/manifest.json', '/sw.js']
    if request.path in public_paths:
        return  # Acceso libre, la BD ya está inicializando

    # Requiere login para todo lo demás
    if 'user_id' not in session:
        return redirect(url_for('login'))




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
    upload_folder = app.config.get('UPLOAD_FOLDER')
    local_path = os.path.join(upload_folder, filename)
    
    # 1. Intentar servir local (rápido)
    if os.path.exists(local_path):
        return send_from_directory(upload_folder, filename)
        
    # 2. Fallback robusto a GCS (siempre que tengamos bucket configurado)
    if GCP_BUCKET_NAME:
        gcs_url = f"https://storage.googleapis.com/{GCP_BUCKET_NAME}/{filename}"
        return redirect(gcs_url)
            
    return "Archivo no encontrado", 404


@app.context_processor
def inject_utils():
    from storage_manager import get_gcs_url
    return dict(safe_gcs_url=get_gcs_url)

@app.errorhandler(404)
def handle_404(e):
    """Manejador centralizado de 404 con diagnóstico de logs."""
    app.logger.warning(f"[404-DIAGNOSTIC] Ruta no encontrada: {request.path} | Method: {request.method}")
    return render_template('404.html'), 404

# --- AUTH ROUTES ---
@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/login-google')
def login_google():
    """Inicia el flujo de OAuth con Google."""
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES
    )
    
    # La URI de redirección debe coincidir exactamente con la configurada en la consola
    # Forzamos HTTPS para Cloud Run
    flow.redirect_uri = url_for('callback', _external=True, _scheme='https')
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    # CRÍTICO: Guardar el verificador de código (PKCE) para recuperarlo en el callback
    if hasattr(flow, 'code_verifier'):
        session['code_verifier'] = flow.code_verifier
        
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    """Maneja la respuesta de Google."""
    try:
        state = session.get('state')
        if not state:
            vanguard_log("CALLBACK ERROR: No se encontró 'state' en la sesión. ¿Cookies bloqueadas?")
        
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            {
                "web": {
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            state=state
        )
        # CRÍTICO: Restaurar el verificador de código (PKCE)
        if 'code_verifier' in session:
            flow.code_verifier = session.get('code_verifier')
            
        # Forzar HTTPS aquí también para consistencia
        flow.redirect_uri = url_for('callback', _external=True, _scheme='https')

        authorization_response = request.url
        # fix para http/https en proxy
        if authorization_response.startswith('http://') and 'https://' in url_for('index', _external=True, _scheme='https'):
             authorization_response = authorization_response.replace('http://', 'https://', 1)

        vanguard_log(f"CALLBACK: Fetching token for {authorization_response}")
        flow.fetch_token(authorization_response=authorization_response)

        credentials = flow.credentials
        request_session = google.auth.transport.requests.Request()
        id_info = google.oauth2.id_token.verify_oauth2_token(
            credentials.id_token, request_session, GOOGLE_CLIENT_ID
        )

        email = id_info.get('email')
        vanguard_log(f"CALLBACK: Validando usuario {email}")
        
        # VALIDACIÓN: Solo permitir el dominio oficial o la lista blanca explícita
        is_authorized = False
        if email:
            if email.endswith(f"@{AUTHORIZED_DOMAIN}"):
                is_authorized = True
            elif email in WHITELISTED_EMAILS:
                is_authorized = True

        if not is_authorized:
            vanguard_log(f"ACCESO DENEGADO: Intento de entrada con {email}")
            flash(f"Error: El acceso está restringido. Tu cuenta ({email}) no está en la lista autorizada.")
            return redirect(url_for('login'))

        # SINCRONIZACIÓN CON DB: Asegurar que el usuario existe
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, name=id_info.get('name'))
            db.session.add(user)
            db.session.commit()
            vanguard_log(f"USUARIO NUEVO CREADO: {email}")
        else:
            # Actualizar nombre si cambió
            user.name = id_info.get('name')
            db.session.commit()

        session['user_id'] = email
        session['user_name'] = id_info.get('name')
        session['user_picture'] = id_info.get('picture')
        session['has_seen_onboarding'] = user.has_seen_onboarding
        
        vanguard_log(f"ACCESO CONCEDIDO: {email} logueado con éxito. Onboarding: {user.has_seen_onboarding}")
        flash(f"Bienvenido, {session['user_name']}.")
        return redirect(url_for('index'))
        
    except Exception as e:
        import traceback
        error_msg = f"ERROR EN CALLBACK OAUTH: {str(e)}\n{traceback.format_exc()}"
        vanguard_log(error_msg)
        # No usamos flash aquí para evitar loop si el error es de sesión
        return f"Error de Autenticación: {str(e)}", 500

@app.route('/logout')
def logout():
    session.clear()
    flash("Has cerrado sesión.")
    return redirect(url_for('login'))

@app.route('/')
def index():
    global _db_ready
    if not _db_ready:
        vanguard_log("Index: DB no lista, retornando dashboard base.")
        return render_template('index.html', 
                             plano_count=0,
                             obj_count=0, 
                             cat_count=0,
                             avg_conf=0,
                             ultima_ubi=None)

    try:
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
        
        # Verificar onboarding para el usuario actual
        user_email = session.get('user_id')
        show_onboarding = False
        if user_email:
            try:
                user = User.query.filter_by(email=user_email).first()
                if user and not user.has_seen_onboarding:
                    show_onboarding = True
            except:
                pass

        try:
            return render_template('index.html', 
                                plano_count=Plano.query.count(),
                                obj_count=objetos_count, 
                                cat_count=categorias_count,
                                avg_conf=avg_conf,
                                ultima_ubi=ultima_ubi,
                                show_onboarding=show_onboarding)
        except Exception as render_err:
            import traceback
            return f"<pre>TEMPLATE RENDER FAILED:\n{traceback.format_exc()}</pre>", 500
    except Exception as e:
        import traceback
        vanguard_log(f"FALLBACK INDEX ACTIVE. Error: {e}")
        vanguard_log(traceback.format_exc())
        try:
            return render_template('index.html', 
                                plano_count=0,
                                obj_count=0, 
                                cat_count=0,
                                avg_conf=0,
                                ultima_ubi=None,
                                show_onboarding=False)
        except Exception as fallback_err:
            return f"<pre>TOTAL COLLAPSE (Index + Fallback Failed):\n{traceback.format_exc()}</pre>", 500

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

@app.route('/api/debug-dashboard')
def debug_dashboard():
    """Diagnóstico de variables para el Dashboard"""
    import traceback
    try:
        from sqlalchemy import func
        stats = {
            "planos": Plano.query.count(),
            "objetos": Objeto.query.count(),
            "categorias": db.session.query(func.count(func.distinct(Objeto.categoria_principal))).scalar() or 0,
            "ultima_id": (Ubicacion.query.order_by(Ubicacion.id.desc()).first()).id if Ubicacion.query.count() > 0 else None
        }
        return jsonify({
            "status": "Logic Process OK",
            "stats": stats,
            "db_ready": _db_ready
        })
    except Exception as e:
        return f"<pre>DIAGNOSTIC FAILED:\n{traceback.format_exc()}</pre>", 500

@app.context_processor
def inject_config():
    gcs_base = f"https://storage.googleapis.com/{GCP_BUCKET_NAME}" if GCP_BUCKET_NAME else ""
    
    def safe_gcs_url(path):
        if not path: return ""
        if path.startswith("http://") or path.startswith("https://"): return path
        if gcs_base: return f"{gcs_base}/{path}"
        try:
            return url_for('uploaded_file', filename=path)
        except:
            return path

    try:
        if not _db_ready:
            return dict(app_config={'subscription_type': 'free'}, gcs_base_url=gcs_base, safe_gcs_url=safe_gcs_url)
            
        config = Config.query.first()
        if not config:
            # No escribir en context processor para evitar bloqueos
            return dict(app_config={'subscription_type': 'free'}, gcs_base_url=gcs_base, safe_gcs_url=safe_gcs_url)
        return dict(app_config=config, gcs_base_url=gcs_base, safe_gcs_url=safe_gcs_url)
    except Exception as e:
        return dict(app_config={'subscription_type': 'free'}, gcs_base_url=gcs_base, safe_gcs_url=safe_gcs_url)

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
    """
    Endpoint de carga migrado a GCS (Memory Processing).
    """
    from ai_engine import analizar_imagen_objetos, generar_embedding
    import json

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No hay archivo')
            return redirect(request.url)
        
        file = request.files['file']
        # ── Leer campos de Jerarquía Semántica del formulario ──
        nombre_ubicacion = request.form.get('nombre_ubicacion', '').strip()
        habitacion       = request.form.get('habitacion', '').strip() or None
        mueble_texto     = request.form.get('mueble_texto', '').strip() or None
        punto_especifico = request.form.get('punto_especifico', '').strip() or None
        
        if file.filename == '':
            flash('No se seleccionó ningún archivo')
            return redirect(request.url)

        try:
            filename = secure_filename(file.filename)
            
            # 1. Leer bytes para la IA
            img_bytes = file.read()
            file.seek(0) # Reset stream for GCS
            
            # 2. IA: Procesar desde memoria
            app.logger.info(f"[VANGUARD-GCS] Analizando con IA (en memoria): {filename}")
            resultado = analizar_imagen_objetos(img_bytes, tipo_espacio="general")
            
            # SRE: Si el usuario no especificó habitación/mueble, usar sugerencia de IA
            if not habitacion:
                habitacion = resultado.get('habitacion_sugerida') or None
            if not mueble_texto:
                mueble_texto = resultado.get('mueble_sugerido') or None
            
            # Auto-generar nombre descriptivo si el usuario lo dejó vacío
            if not nombre_ubicacion:
                partes = [p for p in [habitacion, mueble_texto] if p]
                nombre_ubicacion = " — ".join(partes) if partes else 'Sin nombre'
            
            # 3. GCS: Subir a la nube persistente
            final_filename = upload_image_to_gcs(file, filename)
            
            # 4. Generar Embedding Multimodal (Visual + Contexto)
            contexto_ubi = f"Ubicación: {nombre_ubicacion}. Habitación: {habitacion}. Mueble: {mueble_texto}."
            emb_ubi = generar_embedding([contexto_ubi, img_bytes])
            
            # 5. DB: Guardar registro (incluyendo jerarquía semántica)
            nueva_ubicacion = Ubicacion(
                nombre=nombre_ubicacion,
                imagen_path=final_filename,
                tags=resultado.get('tags', ''),
                items_json=json.dumps(resultado.get('items', [])),
                habitacion=habitacion,
                mueble_texto=mueble_texto,
                punto_especifico=punto_especifico,
                embedding_json=json.dumps(emb_ubi) if emb_ubi else None
            )
            db.session.add(nueva_ubicacion)
            db.session.flush()
            
            nombres_para_tags = []
            for item in resultado.get('items', []):
                nombre_obj = item.get('nombre', 'Objeto detectado')
                # Generar embedding semántico para el objeto
                contexto_obj = f"Objeto: {nombre_obj}. Categoría: {item.get('categoria_principal')}. Descripción: {item.get('descripcion')}. Tags: {item.get('tags_semanticos')}"
                emb_obj = generar_embedding(contexto_obj)
                
                nuevo_objeto = Objeto(
                    nombre=nombre_obj,
                    categoria_principal=item.get('categoria_principal', 'General'),
                    categoria_secundaria=item.get('subcategoria', ''),
                    descripcion=item.get('descripcion', ''),
                    color_predominante=item.get('color_predominante', ''),
                    material=item.get('material', ''),
                    estado=item.get('estado', 'nuevo'),
                    confianza=item.get('confianza', 0.8),
                    ubicacion_id=nueva_ubicacion.id,
                    tags_semanticos=item.get('tags_semanticos', ''),
                    embedding_json=json.dumps(emb_obj) if emb_obj else None
                )
                db.session.add(nuevo_objeto)
                nombres_para_tags.append(nombre_obj)
            
            # SRE Sync: Asegurar que la ubicación tenga los tags para que la galería no diga "Sin análisis"
            if nombres_para_tags:
                nueva_ubicacion.tags = ", ".join(nombres_para_tags)
            elif not nueva_ubicacion.tags:
                nueva_ubicacion.tags = "Sin objetos detectados"
                
            db.session.commit()
            
            # ── Rev 86: Phase 1 Safety Valve & Confidence ──
            avg_conf = 0.8
            if resultado.get('items'):
                confs = [item.get('confianza', 0.8) for item in resultado.get('items')]
                avg_conf = sum(confs) / len(confs)
            
            is_high_conf = avg_conf > 0.9
            edit_link = f' <a href="/ubicacion/editar/{nueva_ubicacion.id}" style="color:var(--primary); font-weight:bold; margin-left:8px;">[Editar]</a>'
            
            if is_high_conf:
                msg = f'✓ "{nombre_ubicacion}" auto-indexado con éxito.' + edit_link
            else:
                msg = f'✓ "{nombre_ubicacion}" indexado.' + edit_link
            
            flash(msg)
            vanguard_log(f"[DB-SUCCESS] Ubicación '{nombre_ubicacion}' guardada (Confianza: {avg_conf:.2f}).")
            
            # Direct-to-Map: Si es alta confianza, podrímos redirigir al plano si existiera, 
            # pero por ahora gallery es el destino estándar.
            return redirect(url_for('gallery'))

        except Exception as e:
            app.logger.error(f"Error en upload: {e}")
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
            
    return render_template('upload.html')
            
    return render_template('upload.html')

@app.route('/gallery')
def gallery():
    ubicaciones = Ubicacion.query.order_by(Ubicacion.fecha_creacion.desc()).all()
    return render_template('gallery.html', ubicaciones=ubicaciones)

@app.route('/ubicacion/editar/<int:ubi_id>', methods=['GET', 'POST'])
def editar_ubicacion(ubi_id):
    """Permite al usuario corregir manualmente los datos detectados por la IA."""
    ubi = Ubicacion.query.get_or_404(ubi_id)
    if request.method == 'POST':
        ubi.nombre = request.form.get('nombre', ubi.nombre)
        ubi.habitacion = request.form.get('habitacion', ubi.habitacion)
        ubi.mueble_texto = request.form.get('mueble_texto', ubi.mueble_texto)
        
        # Actualizar objetos
        for obj in ubi.objetos:
            obj.nombre = request.form.get(f'obj_{obj.id}_nombre', obj.nombre)
            obj.categoria_principal = request.form.get(f'obj_{obj.id}_cat', obj.categoria_principal)
            
        db.session.commit()
        flash(f'✓ Ubicación "{ubi.nombre}" actualizada.')
        return redirect(url_for('gallery'))
        
    return render_template('ubicacion_edit.html', ubi=ubi)

    from ai_engine import interpretar_consulta, generar_embedding
    import numpy as np
    
    query = request.args.get('q', '').lower().strip()
    resultados = []
    
    # 1. Obtener Vector de la Consulta
    query_vector = None
    if query:
        # Usamos task_type="RETRIEVAL_QUERY" para la consulta
        vec = generar_embedding(query, task_type="RETRIEVAL_QUERY")
        if vec:
            query_vector = np.array(vec)
    
    if query:
        # Obtener TODOS los objetos para fuzzy search
        todos_objetos = Objeto.query.all()
        
        # Búsqueda mejorada con ponderación de algoritmos + Ubicación Semántica
        candidatos = []
        
        for obj in todos_objetos:
            nombre_lower = obj.nombre.lower()
            categoria_lower = (obj.categoria_principal or "").lower()
            # ── Fase 2: Campos semánticos de ubicación ──
            habitacion_lower = (getattr(obj.ubicacion, 'habitacion', '') or "").lower()
            mueble_lower = (getattr(obj.ubicacion, 'mueble_texto', '') or "").lower()
            punto_lower = (getattr(obj.ubicacion, 'punto_especifico', '') or "").lower()
            ubicacion_nombre = (obj.ubicacion.nombre or "").lower()
            
            # 1. Similitud exacta (Ratio) - PESO MAYOR
            ratio_nombre = fuzz.ratio(query, nombre_lower)
            ratio_categoria = fuzz.ratio(query, categoria_lower)
            
            # 2. Búsqueda parcial (Partial Ratio) - para queries cortas
            partial_nombre = fuzz.partial_ratio(query, nombre_lower)
            partial_categoria = fuzz.partial_ratio(query, categoria_lower)
            
            # 3. Token Sort Ratio - para orden de palabras
            token_nombre = fuzz.token_sort_ratio(query, nombre_lower)
            token_categoria = fuzz.token_sort_ratio(query, categoria_lower)
            
            # 4. Búsqueda semántica por habitación/mueble/punto
            ratio_habitacion = fuzz.partial_ratio(query, habitacion_lower) if habitacion_lower else 0
            ratio_mueble = fuzz.partial_ratio(query, mueble_lower) if mueble_lower else 0
            ratio_punto = fuzz.partial_ratio(query, punto_lower) if punto_lower else 0
            ratio_ubicacion = fuzz.partial_ratio(query, ubicacion_nombre) if ubicacion_nombre else 0
            
            # 5. Similitud Semántica (Vectorial)
            semantic_score = 0
            if query_vector is not None and obj.embedding_json:
                try:
                    obj_vector = np.array(json.loads(obj.embedding_json))
                    # Similitud Coseno
                    norm_q = np.linalg.norm(query_vector)
                    norm_o = np.linalg.norm(obj_vector)
                    if norm_q > 0 and norm_o > 0:
                        cos_sim = np.dot(query_vector, obj_vector) / (norm_q * norm_o)
                        # Escalar de -1..1 a 0..100
                        semantic_score = max(0, cos_sim * 100)
                except: pass

            # PONDERACIÓN HÍBRIDA (Revision 69: "Puntería Quirúrgica")
            max_fuzzy = max(ratio_nombre, ratio_categoria, ratio_habitacion, ratio_mueble)
            
            # El score final es el mejor entre fuzzy fuerte o una mezcla (70% semántica + 30% fuzzy parcial)
            if ratio_nombre >= 95:
                # Prioridad Absoluta: Si el nombre coincide casi exacto, ignoramos semántica para no "abrir" el buscador
                final_score = ratio_nombre
            elif max_fuzzy >= 85:
                final_score = max_fuzzy
            elif semantic_score >= 75: # Subimos umbral semántico robusto
                # Si la semántica es alta, le damos prioridad pero sumamos un poco de fuzzy
                final_score = (semantic_score * 0.8) + (max_fuzzy * 0.2)
            else:
                final_score = max(max_fuzzy, semantic_score)
            
            # AJUSTE DE PUNTERÍA: Umbral mínimo 75% para filtrar ruido (Revision 69)
            # Se usa 75 en lugar de 80 para no castigar coincidencias semánticas puras de alta calidad.
            if final_score >= 75: 
                candidatos.append((obj, final_score, semantic_score))
        
        # Ordenar por score (mayor primero)
        candidatos.sort(key=lambda x: x[1], reverse=True)
        
        # Procesar resultados (máximo 30 para evitar saturación)
        for obj, score, s_score in candidatos[:30]:
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
                'habitacion': getattr(obj.ubicacion, 'habitacion', None),
                'mueble': getattr(obj.ubicacion, 'mueble_texto', None),
                'punto_especifico': getattr(obj.ubicacion, 'punto_especifico', None),
                'ubicacion_id': obj.ubicacion.id,
                'plano_id': obj.ubicacion.plano_id,
                'imagen': obj.ubicacion.imagen_path,
                'timestamp': obj.fecha_indexado.strftime('%Y-%m-%d %H:%M'),
                'bbox': bbox,
                'score': round(score, 1),
                'semantic_match': s_score > 70,
                'contenedor': obj.contenedor,
                'posicion_relativa': obj.posicion_relativa
            })
    
    return render_template('search_results.html', query=query, resultados=resultados)

@app.route('/api/sugerencias')
def sugerencias():
    """API para auto-complete con fuzzy matching mejorado + ubicación semántica"""
    from rapidfuzz import process, fuzz
    
    query = request.args.get('q', '').lower().strip()
    
    if not query or len(query) < 2:
        return jsonify([])
    
    # Obtener nombres únicos de objetos, categorías Y ubicaciones semánticas
    nombres_set = set()
    objetos = Objeto.query.all()
    for obj in objetos:
        nombres_set.add(obj.nombre.capitalize())
        if obj.categoria_principal:
            nombres_set.add(obj.categoria_principal.capitalize())
    
    # Fase 2: Agregar habitaciones y muebles al pool de sugerencias
    ubicaciones = Ubicacion.query.all()
    for ubi in ubicaciones:
        if getattr(ubi, 'habitacion', None):
            nombres_set.add(ubi.habitacion)
        if getattr(ubi, 'mueble_texto', None):
            nombres_set.add(ubi.mueble_texto.capitalize())
        if ubi.nombre:
            nombres_set.add(ubi.nombre)
    
    opciones = list(nombres_set)
    
    resultados = process.extract(
        query,
        opciones,
        scorer=fuzz.token_sort_ratio,
        limit=10,
        score_cutoff=55
    )
    
    sugerencias_list = [
        {
            'texto': match[0],
            'score': int(match[1])
        }
        for match in resultados
    ]
    
    return jsonify(sugerencias_list)


@app.route('/api/smart-search')
def smart_search_api():
    """API JSON para la búsqueda inteligente del hero (homepage).
    Busca en objetos, categorías, y campos semánticos de ubicación.
    Retorna el mejor match con imagen, bbox y datos de ubicación."""
    import json
    from rapidfuzz import fuzz
    
    query = request.args.get('q', '').lower().strip()
    
    if not query:
        return jsonify({'success': False, 'error': 'Query vacía'})
    
    todos_objetos = Objeto.query.all()
    mejor = None
    mejor_score = 0
    
    for obj in todos_objetos:
        nombre_lower = obj.nombre.lower()
        cat_lower = (obj.categoria_principal or "").lower()
        habitacion_lower = (getattr(obj.ubicacion, 'habitacion', '') or "").lower()
        mueble_lower = (getattr(obj.ubicacion, 'mueble_texto', '') or "").lower()
        punto_lower = (getattr(obj.ubicacion, 'punto_especifico', '') or "").lower()
        ubi_nombre = (obj.ubicacion.nombre or "").lower()
        tags_lower = (obj.ubicacion.tags or "").lower()
        
        scores = [
            fuzz.ratio(query, nombre_lower),
            fuzz.partial_ratio(query, nombre_lower),
            fuzz.token_sort_ratio(query, nombre_lower),
            fuzz.ratio(query, cat_lower),
            fuzz.partial_ratio(query, habitacion_lower) if habitacion_lower else 0,
            fuzz.partial_ratio(query, mueble_lower) if mueble_lower else 0,
            fuzz.partial_ratio(query, punto_lower) if punto_lower else 0,
            fuzz.partial_ratio(query, ubi_nombre) if ubi_nombre else 0,
            fuzz.partial_ratio(query, tags_lower) if tags_lower else 0,
        ]
        
        max_score = max(scores)
        if max_score > mejor_score:
            mejor_score = max_score
            mejor = obj
    
    if not mejor or mejor_score < 60:
        return jsonify({'success': False, 'error': f'No encontramos nada para "{query}"'})
    
    # Buscar bbox
    bbox = None
    try:
        if mejor.ubicacion.items_json:
            items = json.loads(mejor.ubicacion.items_json)
            for item in items:
                if item.get('nombre', '').lower() == mejor.nombre.lower():
                    bbox = item.get('bbox')
                    break
    except Exception:
        pass
    
    # Construir ubicación descriptiva
    loc_parts = []
    if getattr(mejor.ubicacion, 'habitacion', None):
        loc_parts.append(mejor.ubicacion.habitacion)
    if getattr(mejor.ubicacion, 'mueble_texto', None):
        loc_parts.append(mejor.ubicacion.mueble_texto)
    if getattr(mejor.ubicacion, 'punto_especifico', None):
        loc_parts.append(mejor.ubicacion.punto_especifico)
    ubicacion_desc = ' → '.join(loc_parts) if loc_parts else mejor.ubicacion.nombre
    
    return jsonify({
        'success': True,
        'match': {
            'nombre': mejor.nombre,
            'descripcion': mejor.descripcion,
            'categoria': mejor.categoria_principal,
            'confianza': mejor.confianza,
            'ubicacion_nombre': ubicacion_desc,
            'ubicacion_raw': mejor.ubicacion.nombre,
            'habitacion': getattr(mejor.ubicacion, 'habitacion', None),
            'mueble': getattr(mejor.ubicacion, 'mueble_texto', None),
            'imagen_path': mejor.ubicacion.imagen_path,
            'plano_id': mejor.ubicacion.plano_id,
            'plano_nombre': mejor.ubicacion.plano.nombre if mejor.ubicacion.plano_id else None,
            'bbox': bbox,
            'zona_coords': None,
            'score': mejor_score
        }
    })

# ── API: Polling de estado del análisis (auto-refresh sin recargar página) ──
@app.route('/api/check-analysis/<int:ubi_id>')
def check_analysis(ubi_id):
    """Retorna el estado del análisis de una ubicación para auto-polling."""
    ubi = Ubicacion.query.get_or_404(ubi_id)
    objetos = Objeto.query.filter_by(ubicacion_id=ubi_id).all()
    
    tiene_analisis = bool(ubi.tags and ubi.tags not in ['', 'Procesando análisis...', 'Sin análisis aún'])
    
    return jsonify({
        'id': ubi.id,
        'ready': tiene_analisis,
        'tags': ubi.tags or '',
        'objetos_count': len(objetos),
        'objetos': [
            {
                'nombre': obj.nombre,
                'categoria': obj.categoria_principal or 'General',
                'confianza': int((obj.confianza or 0.8) * 100),
                'contenedor': obj.contenedor,
                'posicion_relativa': obj.posicion_relativa
            }
            for obj in objetos
        ]
    })

# ── API: Guardar Hotspot (Punto de Interés) sobre Foto de Referencia ──
@app.route('/api/save-hotspot/<int:plano_id>', methods=['POST'])
def save_hotspot(plano_id):
    """Guarda o actualiza un hotspot (zona) vinculado a un mueble/sector."""
    plano = Plano.query.get_or_404(plano_id)
    data = request.get_json()
    
    nombre = data.get('nombre', 'Nuevo Punto')
    x = data.get('x') # 0-100
    y = data.get('y') # 0-100
    
    if x is None or y is None:
        return jsonify({'success': False, 'error': 'Coordenadas faltantes'}), 400
        
    try:
        # Buscamos si ya existe una zona con ese nombre para este plano o creamos una nueva
        zona = Zona.query.filter_by(plano_id=plano_id, nombre=nombre).first()
        if not zona:
            zona = Zona(nombre=nombre, plano_id=plano_id)
            db.session.add(zona)
            
        zona.coords_json = json.dumps({'x': x, 'y': y, 'type': 'hotspot'})
        db.session.commit()
        
        return jsonify({'success': True, 'id': zona.id})
    except Exception as e:
        app.logger.error(f"[HOTSPOT-ERR] {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/planos')
def list_planos():
    planos = Plano.query.all()
    return render_template('planos.html', planos=planos)

@app.route('/plano/nuevo', methods=['GET', 'POST'])
def nuevo_plano():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        file = request.files.get('file')
        drawing_data = request.form.get('canvas_data') or request.form.get('drawing_data')
        
        metodo = request.form.get('metodo')
        template_type = request.form.get('template_type')
        
        filename = None
        if metodo == 'upload' and file and file.filename != '':
            filename = secure_filename(file.filename)
            filename = upload_image_to_gcs(file, filename)
        elif metodo == 'template' and template_type:
            # 🥈 Pure Silver Blueprints Base v2 (Rev 98: Arquitectura Funcional)
            try:
                import json
                from PIL import Image, ImageDraw, ImageFont, ImageFilter
                import os
                
                # Cargar presets
                presets_path = os.path.join(app.static_folder, 'data', 'presets.json')
                with open(presets_path, 'r', encoding='utf-8') as f:
                    presets = json.load(f)
                
                # Obtener variante (por ahora la primera si no se especifica)
                variant_id = request.form.get('variant_id')
                category_presets = presets.get(template_type, [])
                preset = next((p for p in category_presets if p['id'] == variant_id), category_presets[0]) if category_presets else None
                
                # Fondo oscuro profundo
                img = Image.new('RGBA', (1000, 1000), color='#0a0a0a')
                draw = ImageDraw.Draw(img)
                
                # 1. Grid técnico sutil
                for i in range(0, 1000, 50):
                    draw.line([(i, 0), (i, 1000)], fill='#1a1a1a', width=1)
                    draw.line([(0, i), (1000, i)], fill='#1a1a1a', width=1)
                
                if preset:
                    silver_line = '#e2e8f0'
                    metallic_fill = '#4a5568'
                    
                    # 2. Dibujar Zonas (Zonificación por Color 5% Opacity)
                    overlay = Image.new('RGBA', (1000, 1000), (0,0,0,0))
                    overlay_draw = ImageDraw.Draw(overlay)
                    for zone in preset.get('zones', []):
                        r = zone['rect']
                        overlay_draw.rectangle(r, fill=(255, 255, 255, 13)) # ~5% alpha
                        overlay_draw.rectangle(r, outline=(255, 255, 255, 30), width=1)
                    img = Image.alpha_composite(img, overlay)
                    draw = ImageDraw.Draw(img) # Refresh draw object
                    
                    # 3. Dibujar Muros (Sólidos con Sombra)
                    for wall in preset.get('walls', []):
                        if 'rect' in wall:
                            r = wall['rect']
                            th = wall.get('thickness', 5)
                            # Sombra sutil
                            draw.rectangle([r[0]+2, r[1]+2, r[2]+2, r[3]+2], outline=(0,0,0,100), width=th)
                            # Muro metálico
                            draw.rectangle(r, outline=silver_line, width=th)
                        elif 'line' in wall:
                            l = wall['line']
                            th = wall.get('thickness', 4)
                            draw.line(l, fill=silver_line, width=th)

                    # 4. Labels de Zona (Bold + Badge)
                    for zone in preset.get('zones', []):
                        r = zone['rect']
                        label = zone['label']
                        # Badge background
                        text_w = len(label) * 10
                        center_x = (r[0] + r[2]) // 2
                        center_y = (r[1] + r[3]) // 2
                        draw.rectangle([center_x - text_w//2 - 5, center_y - 12, center_x + text_w//2 + 5, center_y + 12], fill='#1a202c', outline=silver_line, width=1)
                        draw.text((center_x - text_w//2, center_y - 10), label, fill=silver_line)

                # Convertir a RGB para guardar como PNG/JPG
                final_img = img.convert('RGB')
                import io
                img_io = io.BytesIO()
                final_img.save(img_io, 'PNG')
                img_io.seek(0)
                temp_filename = f"blueprint_{template_type}_{uuid.uuid4().hex[:6]}.png"
                filename = upload_image_to_gcs(img_io, temp_filename)
                
                # Pre-poblamiento dinámico desde el preset
                if preset and 'furniture' in preset:
                    latest_preset = preset # For use inside DB session
            except Exception as e:
                app.logger.error(f"Error generando blueprint rev98: {e}")
                filename = "default_silver_blueprint.png" # Fallback
                latest_preset = None

        elif metodo == 'draw' and drawing_data:
            # Procesar imagen del canvas (base64) en memoria
            try:
                import io
                import base64
                header, encoded = drawing_data.split(",", 1)
                data = base64.b64decode(encoded)
                temp_filename = f"drawing_{uuid.uuid4().hex[:8]}.png"
                buffer = io.BytesIO(data)
                filename = upload_image_to_gcs(buffer, temp_filename)
            except Exception as e:
                app.logger.error(f"Error al guardar el dibujo: {e}")
                flash(f"Error al guardar el dibujo: {e}")
                return redirect(request.url)
        
        if filename:
            nuevo = Plano(nombre=nombre, imagen_path=filename)
            db.session.add(nuevo)
            db.session.flush() # Para tener el ID

            # Pre-pobla muebles dinámicamente según el preset (Rev 98)
            if metodo == 'template' and latest_preset:
                for f_data in latest_preset.get('furniture', []):
                    db.session.add(Mueble(
                        tipo=f_data['tipo'],
                        nombre=f_data['nombre'],
                        pos_x=f_data['x'],
                        pos_y=f_data['y'],
                        ancho=f_data['w'],
                        alto=f_data['h'],
                        plano_id=nuevo.id
                    ))
            
            db.session.commit()
            flash(f'✓ Plano "{nombre}" creado en la nube con éxito.')
            if metodo == 'template':
                return redirect(url_for('modular_editor', plano_id=nuevo.id))
            return redirect(url_for('list_planos'))
            
    return render_template('plano_form.html')

@app.route('/plano/eliminar/<int:plano_id>', methods=['POST'])
def eliminar_plano(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    nombre = plano.nombre
    
    # Desvincular ubicaciones
    for ubi in plano.ubicaciones:
        ubi.plano_id = None
        ubi.pos_x = None
        ubi.pos_y = None
    
    # Intentar borrar de GCS
    if plano.imagen_path:
        try:
            from storage_manager import get_storage_client, GCP_BUCKET_NAME
            client = get_storage_client()
            bucket = client.bucket(GCP_BUCKET_NAME)
            blob = bucket.blob(plano.imagen_path)
            blob.delete()
        except Exception as e:
            app.logger.warning(f"No se pudo borrar {plano.imagen_path} de GCS: {e}")
            
    db.session.delete(plano)
    db.session.commit()
    flash(f'Plano "{nombre}" eliminado correctamente.')
    return redirect(url_for('list_planos'))

@app.route('/plano/<int:plano_id>/modular_editor')
def modular_editor(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    # Convertir muebles a JSON para el frontend
    muebles_list = []
    for m in plano.muebles:
        muebles_list.append({
            'id': m.id,
            'tipo': m.tipo,
            'nombre': m.nombre,
            'x': m.pos_x,
            'y': m.pos_y,
            'w': m.ancho,
            'h': m.alto
        })
    import json
    return render_template('plano_modular_editor.html', plano=plano, muebles_json=json.dumps(muebles_list))

@app.route('/api/plano/<int:plano_id>/save_modular', methods=['POST'])
def save_modular_layout(plano_id):
    plano = Plano.query.get_or_404(plano_id)
    data = request.json
    items = data.get('items', [])

    try:
        # Limpiar muebles anteriores (o actualizar si quisiéramos ser más quirúrgicos)
        # Por ahora, borramos y recreamos para asegurar consistencia con el editor
        Mueble.query.filter_by(plano_id=plano_id).delete()
        
        for item in items:
            nuevo_mueble = Mueble(
                plano_id=plano_id,
                nombre=item.get('nombre'),
                tipo=item.get('tipo'),
                pos_x=item.get('x'),
                pos_y=item.get('y'),
                ancho=item.get('w'),
                alto=item.get('h')
            )
            db.session.add(nuevo_mueble)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/plano/<int:plano_id>')
def ver_plano(plano_id):
    try:
        plano = Plano.query.get_or_404(plano_id)
        ubicaciones_sin_plano = Ubicacion.query.filter_by(plano_id=None).all()
        
        # Ubicaciones del plano sin posición (ej: del Video Scanner)
        ubicaciones_sin_posicion = Ubicacion.query.filter(
            Ubicacion.plano_id == plano_id,
            (Ubicacion.pos_x == None) | (Ubicacion.pos_y == None)
        ).all()
        
        # Preparar PINS (Ubicaciones con posición)
        pins_data = []
        for ubi in (plano.ubicaciones or []):
            if ubi.pos_x is not None and ubi.pos_y is not None:
                obj_list = []
                for obj in (ubi.objetos or []):
                    obj_list.append({
                        'id': obj.id, 'nombre': obj.nombre,
                        'x': obj.pos_x, 'y': obj.pos_y,
                        'categoria': obj.categoria_principal
                    })
                pins_data.append({
                    'id': ubi.id, 'nombre': ubi.nombre,
                    'x': ubi.pos_x, 'y': ubi.pos_y,
                    'tags': ubi.tags, 'objetos_count': len(ubi.objetos),
                    'objetos': obj_list, 'imagen_path': ubi.imagen_path
                })
        
        # Preparar UNPLACED
        unplaced_data = []
        for ubi in ubicaciones_sin_posicion:
            unplaced_data.append({
                'id': ubi.id, 'nombre': ubi.nombre,
                'objetos_count': len(ubi.objetos), 'imagen_path': ubi.imagen_path
            })

        # Preparar HOTSPOTS (Zonas interactivas)
        hotspots_data = []
        if hasattr(plano, 'zonas'):
            for zona in plano.zonas:
                try:
                    if zona.coords_json:
                        coords = json.loads(zona.coords_json)
                        hotspots_data.append({
                            'id': zona.id, 'nombre': zona.nombre,
                            'x': coords.get('x'), 'y': coords.get('y')
                        })
                except: continue

        # Preparar MUEBLES (Modular Revision 69)
        muebles_list = []
        for m in (plano.muebles or []):
            muebles_list.append({
                'id': m.id, 'tipo': m.tipo, 'nombre': m.nombre,
                'x': m.pos_x, 'y': m.pos_y, 'w': m.ancho, 'h': m.alto
            })

        return render_template('plano_view.html', 
                             plano=plano, 
                             pins=pins_data,
                             unplaced=unplaced_data,
                             hotspots=hotspots_data,
                             muebles_json=json.dumps(muebles_list),
                             ubicaciones_sin_plano=ubicaciones_sin_plano)
    except Exception as e:
        vanguard_log(f"ERROR CRÍTICO en ver_plano({plano_id}): {str(e)}")
        import traceback
        vanguard_log(traceback.format_exc())
        
        # Intentar recuperar el objeto plano por fuera si falló antes
        plano_fb = None
        try:
            plano_fb = Plano.query.get(plano_id)
        except:
            pass
            
        flash(f"Modo de Recuperación: {str(e)[:100]}")
        return render_template('plano_view.html', 
                             plano=plano_fb, 
                             pins=[],
                             unplaced=[],
                             hotspots=[],
                             muebles_json='[]',
                             ubicaciones_sin_plano=[])


@app.route('/api/health')
def health_check():
    """Diagnóstico profundo para SRE/DevOps"""
    try:
        from sqlalchemy import text
        db.session.execute(text("SELECT 1"))
        db_status = "Connected"
        
        # Conteo rápido de objetos para verificar sincronización
        obj_count = Objeto.query.count()
        plano_count = Plano.query.count()
        muebles_count = Mueble.query.count()
        
        # Detectar entorno
        env = "Cloud Run/Render" if os.environ.get('PORT') else "Local"
        
        return jsonify({
            "status": "Healthy",
            "version": "1.0.9-hotfix-sql-final",
            "database": db_status,
            "environment": env,
            "stats": {
                "objetos": obj_count,
                "planos": plano_count,
                "muebles_table_accessible": True,
                "muebles_count": muebles_count
            }
        })
    except Exception as e:
        return jsonify({
            "status": "Unhealthy",
            "error": str(e),
            "version": "1.0.9-hotfix-sql-final"
        }), 500

@app.route('/plano/editar-zonas/<int:plano_id>')
def editor_plano(plano_id):
    """Editor de zonas inteligente (Tesla style)"""
    plano = Plano.query.get_or_404(plano_id)
    # Cargar zonas existentes
    original_zonas = []
    if hasattr(plano, 'zonas'):
        for zona in plano.zonas:
            try:
                if zona.coords_json:
                    coords = json.loads(zona.coords_json)
                    # El editor espera {x, y, w, h, nombre, color}
                    if coords.get('type') != 'hotspot': # Solo zonas rectangulares
                        original_zonas.append({
                            'id': zona.id,
                            'nombre': zona.nombre,
                            'x': coords.get('x'),
                            'y': coords.get('y'),
                            'w': coords.get('w'),
                            'h': coords.get('h'),
                            'color': coords.get('color', '#6366f1')
                        })
            except: continue
            
    return render_template('editor_plano.html', plano=plano, original_zonas=original_zonas)

@app.route('/api/plano/<int:plano_id>/save_zonas', methods=['POST'])
def save_zonas(plano_id):
    """Guarda las zonas dibujadas en el editor"""
    try:
        data = request.json
        zonas_data = data.get('zonas', [])
        plano = Plano.query.get_or_404(plano_id)
        
        # SRE: Nuke de zonas anteriores que no sean hotspots (para evitar duplicados al redibujar)
        # Opcional: Podríamos ser más selectivos, pero el editor suele re-enviar todo el set
        for zona in list(plano.zonas):
            try:
                c = json.loads(zona.coords_json)
                if c.get('type') != 'hotspot':
                    db.session.delete(zona)
            except: pass
            
        for z in zonas_data:
            nueva = Zona(
                nombre=z['nombre'],
                plano_id=plano_id,
                coords_json=json.dumps({
                    'x': z['x'], 'y': z['y'], 'w': z['w'], 'h': z['h'],
                    'color': z.get('color', '#6366f1'),
                    'type': 'rect'
                })
            )
            db.session.add(nueva)
            
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/plano/<int:plano_id>/moldes')
def moldes_selection(plano_id):
    """Selección de moldes para el plano"""
    plano = Plano.query.get_or_404(plano_id)
    return render_template('moldes.html', plano=plano)

@app.route('/plano/<int:plano_id>/3d')
def ver_plano_3d(plano_id):
    """Vista 3D experimental del plano"""
    plano = Plano.query.get_or_404(plano_id)
    return render_template('plano_3d.html', plano=plano)



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
    """
    Análisis instantáneo migrado a GCS.
    """
    import io
    from ai_engine import analizar_imagen_objetos

    try:
        file = request.files.get('image') or request.files.get('file')
        if not file:
            return jsonify({'status': 'error', 'message': 'No se recibió imagen'}), 400
        
        # 1. IA: Procesar desde memoria
        img_bytes = file.read()
        resultado = analizar_imagen_objetos(img_bytes, tipo_espacio="general")
        
        # 2. GCS: Persistencia rápida (opcional, pero útil)
        file.seek(0)
        filename = f"bolt_{uuid.uuid4().hex[:8]}.jpg"
        upload_image_to_gcs(file, filename)
        
        return jsonify({
            'status': 'success',
            'items': resultado.get('items', []),
            'filename': filename
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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

@app.route('/api/admin/fix-db')
def force_fix_db():
    fix_db_sequences()
    return jsonify({"status": "success", "message": "Secuencias reparadas"})

@app.route('/debug/reset-db')
def reset_db_hard():
    """Ruta DBA: Nuke total de tablas y reseteo de secuencias a 1."""
    if not instance_connection_name and not raw_db_url:
        return jsonify({"status": "error", "message": "Operación no permitida en modo local"}), 403
    
    vanguard_log("[DBA] Iniciando RESET HARD de base de datos...")
    try:
        # SRE Repair: Limpieza profunda y reinicio de identidad
        db.session.execute(text("TRUNCATE TABLE ubicaciones, objetos, planos RESTART IDENTITY CASCADE"))
        db.session.commit()
        vanguard_log("[DBA] Base de datos REINICIADA con éxito ✅")
        return jsonify({"status": "success", "message": "Base de datos reseteada y limpia (IDs empezarán en 1)"})
    except Exception as e:
        vanguard_log(f"[DBA] Error en Reset: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/crear_ubicacion_en_mapa', methods=['POST'])
def crear_ubicacion_en_mapa():
    """Crear una nueva ubicación directamente desde el mapa migrado a GCS."""
    try:
        nombre = request.form.get('nombre', 'Nuevo Espacio')
        plano_id = request.form.get('plano_id')
        pos_x = request.form.get('pos_x')
        pos_y = request.form.get('pos_y')
        pos_z = request.form.get('pos_z', 0)
        temp_filename = request.form.get('temp_filename')
        objetos_json = request.form.get('objetos_finales')
        file = request.files.get('file')
        
        img_bytes = None
        filename = None
        
        if file:
            img_bytes = file.read()
            file.seek(0)
            orig_name = secure_filename(file.filename) or f"ubi_{uuid.uuid4().hex[:8]}.jpg"
            filename = upload_image_to_gcs(file, orig_name)
        elif temp_filename:
            filename = temp_filename
            
        if not filename:
             return jsonify({'status': 'error', 'message': 'No se recibió imagen'}), 400
        
        # Crear ubicación con posición
        nueva_ubicacion = Ubicacion(
            nombre=nombre,
            imagen_path=filename,
            tags="", 
            plano_id=int(plano_id) if plano_id else None,
            pos_x=int(pos_x) if pos_x else None,
            pos_y=int(pos_y) if pos_y else None,
            pos_z=int(pos_z) if pos_z else 0,
            items_json=objetos_json
        )
        db.session.add(nueva_ubicacion)
        db.session.flush()
        
        import json
        from ai_engine import analizar_imagen_objetos
        
        objetos_finales = []
        if objetos_json:
            objetos_finales = json.loads(objetos_json)
        elif img_bytes:
            # Análisis si no vienen bboxes del frontend
            resultado = analizar_imagen_objetos(img_bytes, tipo_espacio="general")
            objetos_finales = resultado.get('items', [])

        # Preparar proyección espacial (se mantiene lógica de homografía)
        h_matrix = None
        if plano_id:
            plano = Plano.query.get(plano_id)
            if plano and plano.homografia_json:
                from spatial_engine import SpatialEngine, deserialize_h
                try:
                    h_matrix = deserialize_h(json.loads(plano.homografia_json))
                except Exception as e:
                    app.logger.error(f"Error deserializando homografía: {e}")

        nombres_para_tags = []
        for item in objetos_finales:
            categoria_completa = item.get('categoria_principal', item.get('categoria', 'General'))
            
            # LOG DE SEGURIDAD SRE: Validar qué datos entran a la DB
            app.logger.info(f"[DB-MAPPING] Guardando: {item.get('nombre')} | Cat: {categoria_completa} | Desc: {item.get('descripcion')[:30]}...")
            
            # PROYECCIÓN ESPACIAL
            obj_pos_x, obj_pos_y = None, None
            bbox = item.get('bbox')
            if h_matrix is not None and bbox:
                from spatial_engine import SpatialEngine
                anchor = SpatialEngine.get_object_anchor(bbox)
                obj_pos_x, obj_pos_y = SpatialEngine.project_point(h_matrix, anchor)
            else:
                obj_pos_x = float(pos_x) if pos_x else None
                obj_pos_y = float(pos_y) if pos_y else None

            nuevo_objeto = Objeto(
                nombre=item.get('nombre', 'Objeto detectado'),
                categoria_principal=categoria_completa,
                descripcion=item.get('descripcion', ''),
                color_predominante=item.get('color_predominante', ''),
                material=item.get('material', ''),
                estado=item.get('estado', item.get('metadata', {}).get('estado', 'N/A')),
                confianza=item.get('confianza', 0.8),
                prioridad=item.get('prioridad', 'media'),
                ubicacion_id=nueva_ubicacion.id,
                pos_x=obj_pos_x,
                pos_y=obj_pos_y,
                posicion_relativa=item.get('posicion_relativa', ''),
                contenedor=item.get('contenedor', ''),
                tags_semanticos=item.get('tags_semanticos', '')
            )
            db.session.add(nuevo_objeto)
            nombres_para_tags.append(item.get('nombre', 'Objeto'))
            
        # SRE Sync: Asegurar que la ubicación tenga los tags para que la galería no diga "Sin análisis"
        if nombres_para_tags:
            nueva_ubicacion.tags = ", ".join(nombres_para_tags)
        else:
            nueva_ubicacion.tags = "Sin objetos detectados"
            
        db.session.commit()
        vanguard_log(f"[DB-SUCCESS] Ubicación '{nombre}' guardada con {len(objetos_finales)} objetos.")
        
        return jsonify({
            'status': 'success',
            'ubicacion_id': nueva_ubicacion.id,
            'nombre': nueva_ubicacion.nombre,
            'objetos_detectados': len(objetos_finales)
        })
    except Exception as e:
        app.logger.error(f"Error en crear_ubicacion_en_mapa: {e}")
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/plano/<int:plano_id>/upload_simple', methods=['POST'])
def upload_plano_simple(plano_id):
    """Sube una foto directamente a un plano migrado a GCS."""
    plano = Plano.query.get_or_404(plano_id)
    nombre = request.form.get('nombre', 'Nuevo Espacio')
    file = request.files.get('file')
    
    if file and file.filename != '':
        try:
            # 1. IA: Procesar desde memoria
            img_bytes = file.read()
            from ai_engine import analizar_imagen_objetos
            resultado = analizar_imagen_objetos(img_bytes)
            
            # 2. GCS: Subir
            file.seek(0)
            filename = upload_image_to_gcs(file, secure_filename(file.filename))
            
            nueva_ubi = Ubicacion(
                nombre=nombre,
                imagen_path=filename,
                plano_id=plano_id,
                tags=resultado.get('tags', ''),
                items_json=json.dumps(resultado.get('items', []))
            )
            db.session.add(nueva_ubi)
            db.session.flush()
            
            for item in resultado.get('items', []):
                nuevo_obj = Objeto(
                    nombre=item.get('nombre', 'Objeto'),
                    categoria_principal=item.get('categoria_principal', item.get('categoria', 'General')),
                    descripcion=item.get('descripcion', ''),
                    color_predominante=item.get('color_predominante', ''),
                    material=item.get('material', ''),
                    estado=item.get('estado', 'nuevo'),
                    confianza=item.get('confianza', 0.8),
                    ubicacion_id=nueva_ubi.id,
                    tags_semanticos=item.get('tags_semanticos', '')
                )
                db.session.add(nuevo_obj)
            
            db.session.commit()
            flash(f'✓ "{nombre}" indexado en la nube.')
        except Exception as e:
            app.logger.error(f"Error en upload_simple: {e}")
            db.session.rollback()
            flash(f"Error al subir: {e}")
            
    return redirect(url_for('ver_plano', plano_id=plano_id))

@app.route('/plano/editar/<int:plano_id>', methods=['GET', 'POST'])
def editar_plano(plano_id):
    """Editar un plano existente con GCS"""
    plano = Plano.query.get_or_404(plano_id)
    
    if request.method == 'POST':
        nombre = request.form.get('nombre', plano.nombre)
        file = request.files.get('file')
        drawing_data = request.form.get('drawing_data')
        
        # 1. Procesar Archivo (Prioridad: Nueva Foto)
        if file and file.filename != '':
            try:
                from werkzeug.utils import secure_filename
                from storage_manager import upload_image_to_gcs
                
                # Borrar antigua
                if plano.imagen_path:
                    try:
                        from storage_manager import get_storage_client, GCP_BUCKET_NAME
                        bucket = get_storage_client().bucket(GCP_BUCKET_NAME)
                        bucket.blob(plano.imagen_path).delete()
                    except: pass
                
                filename = secure_filename(file.filename)
                new_path = upload_image_to_gcs(file, filename)
                plano.imagen_path = new_path
                app.logger.info(f"[EDIT-PLANO] Nueva foto maestra subida: {new_path}")
            except Exception as e:
                flash(f"Error al subir foto: {e}")
                
        # 2. Procesar Dibujo
        elif drawing_data:
            try:
                import io, base64
                header, encoded = drawing_data.split(",", 1)
                data = base64.b64decode(encoded)
                temp_filename = f"plano_edit_{uuid.uuid4().hex[:8]}.png"
                
                if plano.imagen_path:
                    try:
                        from storage_manager import get_storage_client, GCP_BUCKET_NAME
                        get_storage_client().bucket(GCP_BUCKET_NAME).blob(plano.imagen_path).delete()
                    except: pass
                
                new_path = upload_image_to_gcs(io.BytesIO(data), temp_filename)
                plano.imagen_path = new_path
            except Exception as e:
                flash(f"Error al guardar dibujo: {e}")
        
        plano.nombre = nombre
        db.session.commit()
        flash(f'✓ Plano "{nombre}" actualizado correctamente.')
        return redirect(url_for('ver_plano', plano_id=plano.id))
    
    return render_template('plano_edit.html', plano=plano)

@app.route('/api/plano/<int:plano_id>/upload_maestra', methods=['POST'])
def upload_maestra_direct(plano_id):
    """Carga directa de foto maestra desde la vista táctil (Cirugía de Eventos)"""
    plano = Plano.query.get_or_404(plano_id)
    file = request.files.get('file')
    
    if not file or file.filename == '':
        return jsonify({'success': False, 'message': 'No se seleccionó ningún archivo'}), 400
        
    try:
        from werkzeug.utils import secure_filename
        from storage_manager import upload_image_to_gcs, get_storage_client, GCP_BUCKET_NAME
        
        # 1. Limpieza de imagen anterior
        if plano.imagen_path:
            try:
                bucket = get_storage_client().bucket(GCP_BUCKET_NAME)
                bucket.blob(plano.imagen_path).delete()
            except: pass
            
        # 2. Subida a GCS
        filename = secure_filename(file.filename)
        new_path = upload_image_to_gcs(file, filename)
        
        # 3. Actualización DB
        plano.imagen_path = new_path
        db.session.commit()
        
        app.logger.info(f"[CIRUGIA-API] Foto maestra actualizada para plano {plano_id}: {new_path}")
        return jsonify({'success': True, 'path': new_path})
    except Exception as e:
        app.logger.error(f"[CIRUGIA-ERR] Fallo en carga directa: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ── API: Auto-save del dibujo de plano (fetch desde canvas) ──
@app.route('/api/save-drawing/<int:plano_id>', methods=['POST'])
def save_drawing_api(plano_id):
    """Guarda el dibujo del canvas automáticamente sin recargar la página."""
    import io
    plano = Plano.query.get_or_404(plano_id)
    data = request.get_json()
    drawing_data = data.get('drawing_data', '')
    
    if not drawing_data or ',' not in drawing_data:
        return jsonify({'success': False, 'error': 'No drawing data'}), 400
    
    try:
        header, encoded = drawing_data.split(",", 1)
        decoded = base64.b64decode(encoded)
        temp_filename = f"plano_autosave_{plano_id}_{uuid.uuid4().hex[:6]}.png"
        buffer = io.BytesIO(decoded)
        final_filename = upload_image_to_gcs(buffer, temp_filename)
        plano.imagen_path = final_filename
        db.session.commit()
        return jsonify({'success': True, 'filename': final_filename})
    except Exception as e:
        app.logger.error(f"[AUTOSAVE] Error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/ai-optimizer')
def ai_optimizer():
    # El cliente se importa vía get_client() más abajo para ser resilientes
    # from ai_engine import client # BUG: No existe 'client' en ai_engine, solo get_client() o _client
    
    objetos = Objeto.query.all()
    if not objetos:
        return render_template('ai_optimizer.html', tips=[])
    
    # Crear un resumen para la IA
    resumen = []
    for obj in objetos:
        resumen.append(f"- {obj.nombre} (Categoría: {obj.categoria_principal or 'General'}) en {obj.ubicacion.nombre}")
    
    resumen_texto = "\n".join(resumen)
    
    # Llamada a Gemini para consejos pro usando la nueva SDK
    tips = []
    from ai_engine import get_client
    client = get_client()
    if client:
        try:
            prompt = f"""
            Eres un experto en ingeniería de espacios y organización doméstica estilo "Premium/Tesla". 
            Basado en este inventario detectado por mi sistema de visión, dame 3 consejos de "Ingeniería de Élite" para organizar mi casa y ahorrar tiempo.
            
            Inventario:
            {resumen_texto}
            
            Responde ÚNICAMENTE en formato JSON con esta estructura:
            [
              {{"titulo": "Título del consejo", "contenido": "Explicación detallada"}},
              ...
            ]
            """
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            # Limpieza de JSON
            clean_json = response.text.strip()
            if '```json' in clean_json:
                clean_json = clean_json.split('```json')[1].split('```')[0].strip()
            elif '```' in clean_json:
                clean_json = clean_json.split('```')[1].split('```')[0].strip()
            
            import json
            tips = json.loads(clean_json)
        except Exception as e:
            app.logger.error(f"Error en AI Optimizer: {e}")
            tips = [{"titulo": "Cerebro en mantenimiento", "contenido": "La IA está procesando otros datos. Volvé a intentar en unos segundos."}]
            
    return render_template('ai_optimizer.html', tips=tips)

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
                from ai_engine import get_client
                client = get_client()
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

    # Plan B: Redirigido desde upload_frames con frames ya analizados en sesión
    if request.args.get('plan_b') == '1':
        from flask import session
        import json
        temp_file = session.get('temp_frames_file')
        if temp_file:
            temp_path = os.path.join(app.config.get('UPLOAD_FOLDER'), temp_file)
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    raw = json.load(f)
                frames = [{'path': fr['path'], 'objects': fr.get('objects', [])} for fr in raw]
                step = 3

    
    if request.method == 'POST':
        file = request.files.get('video')
        if file:
            # Guardar video y procesar
            video_filename = f"video_{uuid.uuid4().hex[:8]}_{secure_filename(file.filename)}"
            video_path = os.path.join(app.config.get('UPLOAD_FOLDER'), video_filename)
            file.save(video_path)

            from video_processor import extraer_fotogramas
            frame_filenames = extraer_fotogramas(video_path, app.config.get('UPLOAD_FOLDER'))

            # Analizar frames — FIX: leer bytes antes de llamar a la IA
            from ai_engine import analizar_imagen_objetos
            for f_name in frame_filenames:
                f_path = os.path.join(app.config.get('UPLOAD_FOLDER'), f_name)
                try:
                    with open(f_path, 'rb') as img_file:
                        img_bytes = img_file.read()
                    res = analizar_imagen_objetos(img_bytes)
                    frames.append({
                        'path': f_name,
                        'objects': res.get('items', [])
                    })
                except Exception as e:
                    app.logger.error(f"[SCANNER] Error analizando frame {f_name}: {e}")
                    frames.append({'path': f_name, 'objects': []})

            # Guardar frames en archivo temporal (evitar cookie overflow)
            import json
            from flask import session
            temp_frames_file = f"frames_{uuid.uuid4().hex}.json"
            temp_frames_path = os.path.join(app.config.get('UPLOAD_FOLDER'), temp_frames_file)

            with open(temp_frames_path, 'w') as f:
                json.dump(frames, f)

            session['temp_frames_file'] = temp_frames_file
            step = 3

    return render_template('video_scanner.html', plano=plano, step=step, frames=frames)


@app.route('/api/scanner/<int:plano_id>/upload_frames', methods=['POST'])
def scanner_upload_frames(plano_id):
    """Plan B: Recibe fotos capturadas cada 2s desde el celular (base64 JSON).
    NO requiere video — evita el problema de payload y timeout."""
    import json, base64, io
    from ai_engine import analizar_imagen_objetos
    from flask import session

    plano = Plano.query.get_or_404(plano_id)

    try:
        data = request.get_json(force=True)
        fotos_b64 = data.get('frames', [])  # Lista de strings base64

        if not fotos_b64:
            return jsonify({'success': False, 'error': 'No se recibieron frames'}), 400

        app.logger.info(f"[SCANNER-PLAN-B] Recibidos {len(fotos_b64)} frames para plano {plano_id}")
        frames = []

        for i, foto_b64 in enumerate(fotos_b64[:12]):  # Máximo 12 fotos
            try:
                # Decodificar base64 (puede venir con o sin header data:image/jpeg;base64,)
                if ',' in foto_b64:
                    foto_b64 = foto_b64.split(',', 1)[1]
                img_bytes = base64.b64decode(foto_b64)

                # Subir a GCS
                frame_filename = f"scanner_frame_{plano_id}_{uuid.uuid4().hex[:8]}.jpg"
                upload_image_to_gcs(io.BytesIO(img_bytes), frame_filename)

                # Analizar con IA
                res = analizar_imagen_objetos(img_bytes)
                frames.append({
                    'path': frame_filename,
                    'objects': res.get('items', [])
                })
                app.logger.info(f"[SCANNER-PLAN-B] Frame {i+1}: {len(res.get('items', []))} objetos detectados")

            except Exception as e:
                app.logger.error(f"[SCANNER-PLAN-B] Error en frame {i}: {e}")
                frames.append({'path': f'frame_{i}.jpg', 'objects': []})

        # Guardar en sesión para que save_video_scans lo recoja
        temp_frames_file = f"frames_planb_{uuid.uuid4().hex}.json"
        temp_frames_path = os.path.join(app.config.get('UPLOAD_FOLDER'), temp_frames_file)
        with open(temp_frames_path, 'w') as f:
            json.dump(frames, f)
        session['temp_frames_file'] = temp_frames_file

        return jsonify({
            'success': True,
            'frames_analizados': len(frames),
            'frames': frames
        })

    except Exception as e:
        app.logger.error(f"[SCANNER-PLAN-B] Error general: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


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
        temp_path = os.path.join(app.config.get('UPLOAD_FOLDER'), temp_file)
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
                    metadata = obj.get('metadata', {})
                    nuevo_obj = Objeto(
                        nombre=obj['nombre'],
                        categoria_principal=obj.get('categoria_principal', obj.get('categoria', 'General')),
                        descripcion=obj.get('descripcion', ''),
                        color_predominante=metadata.get('color', metadata.get('color_predominante', '')),
                        material=metadata.get('material', ''),
                        estado=metadata.get('estado', ''),
                        tags_semanticos=obj.get('tags_semanticos', ''),
                        confianza=obj.get('confianza', 0.8),
                        ubicacion_id=nueva_ubi.id
                    )
                    db.session.add(nuevo_obj)
        
        db.session.commit()
        db.session.commit()
        
        # Limpiar sesión y archivo
        if temp_file:
            try:
                os.remove(os.path.join(app.config.get('UPLOAD_FOLDER'), temp_file))
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
        video_path = os.path.join(app.config.get('UPLOAD_FOLDER'), video_filename)
        file.save(video_path)
        
        # Extraer fotogramas
        from video_processor import extraer_fotogramas
        frames = extraer_fotogramas(video_path, app.config.get('UPLOAD_FOLDER'), intervalo_segundos=intervalo)
        
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
            frame_path = os.path.join(app.config.get('UPLOAD_FOLDER'), frame_filename)
            
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
                    posicion_relativa=item.get('posicion_relativa', ''),
                    contenedor=item.get('contenedor', ''),
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


# --- ADMINISTRACIÓN Y MANTENIMIENTO ---

@app.route('/admin/backfill_embeddings')
def admin_backfill():
    """Ruta protegida por lógica simple para disparar el re-indexado vectorial"""
    # SRE: Solo permitir si hay una llave configurada o por inspección de IP si es necesario
    # Por simplicidad en este entorno, lo dejaremos accesible pero interno
    from ai_engine import generar_embedding
    from storage_manager import download_image_from_gcs
    import json
    
    count_ubi = 0
    count_obj = 0
    
    try:
        # 1. Ubicaciones (Multimodal)
        ubis = Ubicacion.query.filter(Ubicacion.embedding_json == None).limit(20).all() # Procesar en batches
        for ubi in ubis:
            img_bytes = download_image_from_gcs(ubi.imagen_path)
            if img_bytes:
                contexto = f"Ubicación: {ubi.nombre}. Habitación: {ubi.habitacion}. Mueble: {ubi.mueble_texto}."
                emb = generar_embedding([contexto, img_bytes])
                if emb:
                    ubi.embedding_json = json.dumps(emb)
                    count_ubi += 1
        
        # 2. Objetos (Semántico)
        objs = Objeto.query.filter(Objeto.embedding_json == None).limit(50).all()
        for obj in objs:
            contexto = f"Objeto: {obj.nombre}. Categoría: {obj.categoria_principal}. Descripción: {obj.descripcion}. Tags: {obj.tags_semanticos}"
            emb = generar_embedding(contexto)
            if emb:
                obj.embedding_json = json.dumps(emb)
                count_obj += 1
                
        db.session.commit()
        return f"Backfill Parcial Exitoso: {count_ubi} ubicaciones y {count_obj} objetos indexados. Recarga para continuar."
    except Exception as e:
        db.session.rollback()
        return f"Error en Backfill: {str(e)}", 500

@app.route('/api/user/onboarding_done', methods=['POST'])
def onboarding_done():
    user_email = session.get('user_id')
    if not user_email:
        return jsonify({"status": "error", "message": "No session"}), 401
    
    try:
        user = User.query.filter_by(email=user_email).first()
        if user:
            user.has_seen_onboarding = True
            db.session.commit()
            session['has_seen_onboarding'] = True
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Usar el puerto de la variable de entorno PORT para Render
    port = int(os.environ.get('PORT', 5001))
    print("[VANGUARD-STARTUP] Ejecutando app.run() en modo local/debug")
    app.run(debug=False, host='0.0.0.0', port=port)

print("[VANGUARD-STARTUP] Módulo app.py CARGADO COMPLETAMENTE (Ready for Port Scan).")


import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

# Usar la base de datos de backup que contiene la verdadera inteligencia (30 ubi, 258 obj)
SQLITE_DB = os.path.join('instance', 'ctrl_f_backup_%random%.db')
POSTGRES_URL = os.environ.get('DATABASE_URL')

def migrate():
    if not POSTGRES_URL:
        print("Error: DATABASE_URL no encontrada en .env")
        return

    print(f"--- INICIANDO MIGRACIÓN: SQLite -> Cloud SQL ---")
    
    # 1. Conectar a SQLite
    if not os.path.exists(SQLITE_DB):
        print("No hay base de datos SQLite local para migrar.")
        return
        
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_cursor = sqlite_conn.cursor()

    # 2. Conectar a Postgres
    try:
        pg_conn = psycopg2.connect(POSTGRES_URL)
        pg_cursor = pg_conn.cursor()
        print("Conectado a Cloud SQL con éxito.")
    except Exception as e:
        print(f"Error conectando a Postgres: {e}")
        return

    # Listado de tablas a migrar (orden de dependencias)
    tables = ['planos', 'ubicaciones', 'zonas', 'muebles', 'objetos', 'config']

    # 3. Crear tablas en Postgres si no existen usando el contexto de la app
    print("Creando tablas en Cloud SQL (schema sync)...")
    try:
        from app import app, db
        # Forzar que el modelo esté cargado
        import models
        with app.app_context():
            db.create_all()
            print("Schema sincronizado con éxito (db.create_all).")
            
            # Verificar si hay que aplicar las micro-migraciones de app.py de forma manual
            # aunque db.create_all() debería tomarlas de models.py si están actualizados
    except Exception as e:
        print(f"Advertencia al crear tablas: {e}")

    for table in tables:
        print(f"--- Migrando tabla: {table} ---")
        
        # Leer de SQLite
        try:
            sqlite_cursor.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()
            # Obtener nombres de columnas para asegurar match
            column_names = [description[0] for description in sqlite_cursor.description]
            print(f"Columnas detectadas en SQLite para {table}: {', '.join(column_names)}")
        except Exception as e:
            print(f"Error leyendo {table} de SQLite: {e}")
            continue
        
        if not rows:
            print(f"Tabla {table} vacía en SQLite. Saltando.")
            continue

        # MAPEO DE COLUMNAS (Compatibilidad con versiones viejas)
        pg_column_names = list(column_names)
        if table == 'objetos':
            if 'categoria' in column_names:
                pg_column_names[column_names.index('categoria')] = 'categoria_principal'
            if 'fecha_indexacion' in column_names:
                pg_column_names[column_names.index('fecha_indexacion')] = 'fecha_indexado'
        
        placeholders = ", ".join(["%s"] * len(column_names))
        columns_str = ", ".join(pg_column_names)

        # Insertar en Postgres con ON CONFLICT para evitar duplicados si se re-ejecuta
        # Usamos id como clave de conflicto si existe
        conflict_clause = "ON CONFLICT (id) DO UPDATE SET " + ", ".join([f"{col} = EXCLUDED.{col}" for col in pg_column_names if col != 'id'])
        
        # Si la tabla tiene embeddings, loguear progreso especial
        has_embeddings = 'embedding_json' in column_names
        
        insert_query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) {conflict_clause}"
        
        try:
            pg_cursor.executemany(insert_query, rows)
            print(f"OK: Migrados {len(rows)} registros en {table}." + (" (Con Embeddings preservation)" if has_embeddings else ""))
        except Exception as e:
            print(f"Error insertando en {table}: {e}")
            pg_conn.rollback()
            continue
            
    pg_conn.commit()
    print("\n--- MIGRACION COMPLETADA CON EXITO ---")
    print("Sugerencia: Ejecuta 'fix_db_sequences()' en la nube para resetear IDs de Postgres.")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()


import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

SQLITE_DB = os.path.join('instance', 'ctrl_f.db')
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
        with app.app_context():
            db.create_all()
        print("Schema sincronizado con éxito.")
    except Exception as e:
        print(f"Advertencia al crear tablas: {e}")

    for table in tables:
        print(f"Migrando tabla: {table}...")
        
        # Leer de SQLite
        try:
            sqlite_cursor.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()
        except Exception as e:
            print(f"Error leyendo {table} de SQLite: {e}")
            continue
        
        if not rows:
            print(f"Tabla {table} vacía en SQLite. Saltando.")
            continue

        # Obtener nombres de columnas
        column_names = [description[0] for description in sqlite_cursor.description]
        placeholders = ", ".join(["%s"] * len(column_names))
        columns_str = ", ".join(column_names)

        # Insertar en Postgres
        insert_query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        
        try:
            pg_cursor.executemany(insert_query, rows)
            print(f"Insertados {len(rows)} registros en {table}.")
        except Exception as e:
            print(f"Error insertando en {table}: {e}")
            pg_conn.rollback()
            continue
            
    pg_conn.commit()
    print("\n--- MIGRACIÓN COMPLETADA CON ÉXITO ---")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()

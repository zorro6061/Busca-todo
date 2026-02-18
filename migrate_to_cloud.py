
import os
import sqlite3
import psycopg2
from dotenv import load_dotenv

# Cargar variables
load_dotenv()

SQLITE_DB = 'buscatodo.db'
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
    tables = ['ubicacion', 'plano', 'zona', 'objeto']

    for table in tables:
        print(f"Migrando tabla: {table}...")
        
        # Leer de SQLite
        sqlite_cursor.execute(f"SELECT * FROM {table}")
        rows = sqlite_cursor.fetchall()
        
        if not rows:
            print(f"Tabla {table} vacía. Saltando.")
            continue

        # Obtener nombres de columnas
        column_names = [description[0] for description in sqlite_cursor.description]
        placeholders = ", ".join(["%s"] * len(column_names))
        columns_str = ", ".join(column_names)

        # Limpiar tabla destino (opcional, pero seguro para reintentos)
        # pg_cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")

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

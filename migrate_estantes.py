import sqlite3
import os

db_path = 'c:/Users/Green Park/compras-app/proyecto/CTRL_F_FISICO_APP/instance/ctrl_f.db'

print(f"Migrando base de datos en: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Añadir columna estantes (si no existe)
    try:
        cursor.execute("ALTER TABLE muebles ADD COLUMN estantes INTEGER DEFAULT 1")
        print("Columna 'estantes' añadida exitosamente.")
    except sqlite3.OperationalError as e:
        print(f"Nota: {e} (Probablemente ya existe)")
    
    conn.commit()
    conn.close()
except Exception as e:
    print(f"Error durante la migración: {e}")

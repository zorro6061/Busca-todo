import sqlite3
import os

db_path = 'c:/Users/Green Park/compras-app/proyecto/CTRL_F_FISICO_APP/instance/ctrl_f.db'

if not os.path.exists(db_path):
    db_path = 'instance/ctrl_f.db' # Fallback for local execution

print(f"Migrando base de datos en: {db_path}")

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Crear tabla muebles
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS muebles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo VARCHAR(50) NOT NULL,
            pos_x FLOAT DEFAULT 0,
            pos_y FLOAT DEFAULT 0,
            pos_z FLOAT DEFAULT 0,
            ancho FLOAT DEFAULT 10,
            alto FLOAT DEFAULT 10,
            profundidad FLOAT DEFAULT 10,
            rotacion_y FLOAT DEFAULT 0,
            color VARCHAR(20) DEFAULT '#6366f1',
            plano_id INTEGER NOT NULL,
            FOREIGN KEY (plano_id) REFERENCES planos (id)
        )
    ''')
    
    conn.commit()
    print("Tabla 'muebles' creada exitosamente.")
    conn.close()
except Exception as e:
    print(f"Error durante la migración: {e}")

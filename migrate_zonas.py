import sqlite3
import os

# Función para encontrar la BD
def find_db():
    print(f"Buscando 'ctrl_f.db'...")
    # 1. Chequear raiz
    if os.path.exists('ctrl_f.db'):
        return os.path.abspath('ctrl_f.db')
    # 2. Chequear instance
    if os.path.exists('instance/ctrl_f.db'):
        return os.path.abspath('instance/ctrl_f.db')
    # 3. Buscar en todo el directorio
    for root, dirs, files in os.walk('.'):
        if 'ctrl_f.db' in files:
            return os.path.join(root, 'ctrl_f.db')
    return None

def migrate():
    print(f"CWD: {os.getcwd()}")
    
    db_path = find_db()
    
    if not db_path:
        print("❌ Error fatal: No se encuentra 'ctrl_f.db' por ningún lado.")
        print(f"Archivos en CWD: {os.listdir(os.getcwd())}")
        if os.path.exists('instance'):
            print(f"Archivos en instance: {os.listdir('instance')}")
        return

    print(f"✅ BD encontrada en: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Crear tabla Zonas
        print("Creando tabla 'zonas'...")
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS zonas (
            id INTEGER PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            tipo VARCHAR(20) DEFAULT 'rect',
            coords_json TEXT NOT NULL,
            color VARCHAR(20) DEFAULT '#6366f1',
            plano_id INTEGER NOT NULL,
            FOREIGN KEY(plano_id) REFERENCES planos(id)
        )
        ''')

        # 2. Añadir columna zona_id a objetos
        print("Verificando columna 'zona_id' en tabla 'objetos'...")
        cursor.execute("PRAGMA table_info(objetos)")
        columnas = [info[1] for info in cursor.fetchall()]
        
        if 'zona_id' not in columnas:
            print("Añadiendo columna 'zona_id' a 'objetos'...")
            cursor.execute('ALTER TABLE objetos ADD COLUMN zona_id INTEGER REFERENCES zonas(id)')
        else:
            print("La columna 'zona_id' ya existe.")

        conn.commit()
        print("✅ Migración completada con éxito.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la migración: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

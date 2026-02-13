import sqlite3

DB_PATH = 'instance/inventario_fisico.db'

def check_schema():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("--- Esquema de Tabla 'objetos' ---")
    cursor.execute("PRAGMA table_info(objetos)")
    columns = cursor.fetchall()
    for col in columns:
        print(col)
        
    print("\n--- Esquema de Tabla 'zonas' ---")
    try:
        cursor.execute("PRAGMA table_info(zonas)")
        columns = cursor.fetchall()
        for col in columns:
            print(col)
    except Exception as e:
        print(f"Error o tabla no existe: {e}")

    conn.close()

if __name__ == "__main__":
    check_schema()

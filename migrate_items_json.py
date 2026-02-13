"""
Migración: Añadir campo items_json a tabla ubicaciones
Propósito: Persistir JSON original de IA con bounding boxes para visualización en búsqueda
"""

from models import db
from sqlalchemy import text

def migrate():
    try:
        # Añadir columna items_json a ubicaciones
        db.session.execute(text(
            'ALTER TABLE ubicaciones ADD COLUMN items_json TEXT'
        ))
        db.session.commit()
        print("✅ Migración exitosa: items_json añadido a ubicaciones")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error en migración (posiblemente ya existe): {e}")

if __name__ == '__main__':
    from app import app
    with app.app_context():
        migrate()

import os
import sys
import json
from app import app, db
from models import Ubicacion, Objeto
from ai_engine import generar_embedding
from storage_manager import download_image_from_gcs
from flask import Flask

def run_backfill():
    with app.app_context():
        print("--- Iniciando Backfill de Embeddings (Revisión 68) ---")
        
        # 1. Procesar Ubicaciones
        ubicaciones = Ubicacion.query.filter(Ubicacion.embedding_json == None).all()
        print(f"Indexando {len(ubicaciones)} ubicaciones...")
        for ubi in ubicaciones:
            try:
                print(f"  -> Procesando Ubicación: {ubi.nombre}")
                img_bytes = download_image_from_gcs(ubi.imagen_path)
                if img_bytes:
                    contexto = f"Ubicación: {ubi.nombre}. Habitación: {ubi.habitacion}. Mueble: {ubi.mueble_texto}."
                    emb = generar_embedding([contexto, img_bytes])
                    if emb:
                        ubi.embedding_json = json.dumps(emb)
                        db.session.commit()
                        print(f"     ✓ Embedding generado.")
                    else:
                        print(f"     ⚠ Falló generación de embedding.")
                else:
                    print(f"     ⚠ No se pudo descargar la imagen de GCS.")
            except Exception as e:
                print(f"     ❌ Error: {e}")
                db.session.rollback()

        # 2. Procesar Objetos
        objetos = Objeto.query.filter(Objeto.embedding_json == None).all()
        print(f"\nIndexando {len(objetos)} objetos...")
        for obj in objetos:
            try:
                print(f"  -> Procesando Objeto: {obj.nombre}")
                # Construimos un contexto semántico rico para el vector
                contexto = f"Objeto: {obj.nombre}. Categoría: {obj.categoria_principal}. Descripción: {obj.descripcion}. Tags: {obj.tags_semanticos}"
                emb = generar_embedding(contexto)
                if emb:
                    obj.embedding_json = json.dumps(emb)
                    db.session.commit()
                    print(f"     ✓ Embedding generado.")
                else:
                    print(f"     ⚠ Falló generación de embedding.")
            except Exception as e:
                print(f"     ❌ Error: {e}")
                db.session.rollback()

        print("\n--- Backfill Finalizado ---")

if __name__ == "__main__":
    run_backfill()

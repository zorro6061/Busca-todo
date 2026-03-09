
from google.cloud import storage
import os
import sys

def verify_gcp():
    print("Iniciando verificación de GCP...")
    # Se espera que GOOGLE_APPLICATION_CREDENTIALS ya esté definida en el entorno (ej. Render/Cloud Run)
    try:
        client = storage.Client()
        print(f"Proyecto ID: {client.project}")
        buckets = list(client.list_buckets())
        print(f"Buckets encontrados ({len(buckets)}):")
        for b in buckets:
            print(f" - {b.name}")
        
        target = os.environ.get('GCP_BUCKET_NAME', 'busca-todo-storage')
        exists = any(b.name == target for b in buckets)
        print(f"\nBucket configurado '{target}': {'EXISTE' if exists else 'NO ENCONTRADO'}")
        
    except Exception as e:
        print(f"Error crítico: {e}")

if __name__ == "__main__":
    verify_gcp()

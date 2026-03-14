import os
import io
from google.cloud import storage
from PIL import Image
from pillow_heif import register_heif_opener

# Registrar soporte HEIC
register_heif_opener()

GCP_BUCKET_NAME = os.environ.get("GCP_BUCKET_NAME")
_storage_client = None


def get_storage_client():
    global _storage_client
    if _storage_client is None:
        raw_json = os.environ.get("GCP_CREDENTIALS_JSON")
        if raw_json:
            try:
                import json
                from google.oauth2 import service_account

                creds = service_account.Credentials.from_service_account_info(
                    json.loads(raw_json)
                )
                _storage_client = storage.Client(credentials=creds)
            except Exception as e:
                print(f"Error parsing GCP_CREDENTIALS_JSON: {e}")
                _storage_client = storage.Client()
        else:
            _storage_client = storage.Client()
    return _storage_client


def upload_image_to_gcs(file_stream, filename, max_size=1280, quality=85):
    """
    Procesa la imagen en memoria (redimensiona y comprime) y la sube a GCS.
    Retorna el nombre del objeto subido.
    """
    client = get_storage_client()
    bucket = client.bucket(GCP_BUCKET_NAME)

    # 1. Leer imagen desde el stream
    img = Image.open(file_stream)

    # 2. Normalizar formato a RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 3. Redimensionar si es necesario
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # 4. Guardar en un buffer de memoria
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    buffer.seek(0)

    # 5. Forzar extensión .jpg
    final_filename = filename.rsplit(".", 1)[0] + ".jpg"

    # 6. Subir a GCS
    blob = bucket.blob(final_filename)
    blob.upload_from_file(buffer, content_type="image/jpeg")

    return final_filename


def get_gcs_url(filename):
    """Retorna la URL pública del objeto en el bucket."""
    return f"https://storage.googleapis.com/{GCP_BUCKET_NAME}/{filename}"


def download_image_from_gcs(filename):
    """Descarga los bytes de una imagen desde GCS."""
    client = get_storage_client()
    bucket = client.bucket(GCP_BUCKET_NAME)
    blob = bucket.blob(filename)
    if not blob.exists():
        return None
    return blob.download_as_bytes()

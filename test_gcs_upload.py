import requests
import os
import time

# Configuración básica
BASE_URL = "http://127.0.0.1:5001"
TEST_IMAGE = "uploads/plano_7402bafa.png"
UPLOAD_URL = f"{BASE_URL}/upload"

def test_upload_and_fallback():
    print(f"\n--- INICIANDO TEST DE INTEGRACIÓN GCS ---")
    
    # 1. Preparar archivo de prueba
    if not os.path.exists(TEST_IMAGE):
        print(f"Error: No se encontró la imagen de prueba {TEST_IMAGE}")
        return

    # 2. Realizar el UPLOAD (Simulando el formulario de Nueva Ubicación)
    print(f"1. Subiendo archivo {TEST_IMAGE}...")
    files = {'file': open(TEST_IMAGE, 'rb')}
    data = {'nombre_ubicacion': 'Test GCS Persistence', 'plano_id': '1'}
    
    try:
        response = requests.post(UPLOAD_URL, files=files, data=data, timeout=15)
        print(f"Respuesta del servidor: {response.status_code}")
        
        if response.status_code == 200 or response.history:
            print("Upload enviado con éxito (o redirigido).")
        else:
            print(f"Fallo en el upload: {response.text}")
            return
    except Exception as e:
        print(f"Error de conexión: {e}")
        return

    # 3. Esperar un segundo para que el log se procese
    time.sleep(2)
    print("\n2. Por favor, revisa el LOG del servidor para ver '[VANGUARD-GCS] Subido: ...'")

    # 4. Verificar fallback (Opcional - requiere saber el nombre final)
    # Como el servidor renombra archivos, tendríamos que buscar el más reciente en uploads/
    import glob
    files_in_uploads = glob.glob("uploads/*.jpg")
    if not files_in_uploads:
        print("No se encontraron .jpg recientes en uploads/")
        return
        
    latest_file = max(files_in_uploads, key=os.path.getmtime)
    filename = os.path.basename(latest_file)
    print(f"\n3. Probando FALLBACK para: {filename}")
    
    # Eliminar archivo local para forzar el fallback a GCS
    print(f"Borrando {latest_file} localmente...")
    os.remove(latest_file)
    
    # Intentar acceder a la URL
    access_url = f"{BASE_URL}/uploads/{filename}"
    print(f"Accediendo a {access_url}...")
    resp = requests.get(access_url, allow_redirects=False)
    
    if resp.status_code == 302:
        print(f"¡EXITO! Redirigido correctamente a: {resp.headers.get('Location')}")
    else:
        print(f"Fallo el fallback. Código: {resp.status_code}")

if __name__ == "__main__":
    test_upload_and_fallback()

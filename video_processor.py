import cv2
import os
import time

def extraer_fotogramas(video_path, output_folder, intervalo_segundos=3):
    """
    Extrae fotogramas de un video cada N segundos para ser analizados por la IA.
    Retorna la lista de rutas de las imágenes extraídas.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps == 0:
        fps = 30 # Fallback
        
    intervalo_frames = int(fps * intervalo_segundos)
    
    count = 0
    extracted_files = []
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if count % intervalo_frames == 0:
            timestamp = int(time.time() * 1000)
            filename = f"frame_{timestamp}_{count}.jpg"
            filepath = os.path.join(output_folder, filename)
            cv2.imwrite(filepath, frame)
            extracted_files.append(filename)
            
        count += 1
        
    cap.release()
    return extracted_files

import traceback
from app import app

with open("diagnose_view_output.txt", "w", encoding="utf-8") as f:
    f.write("--- Iniciando Diagnóstico con Test Client ---\n")

with app.app_context():
    try:
        # Forzar que las excepciones se eleven en lugar de renderizar 500
        app.config['PROPAGATE_EXCEPTIONS'] = True
        
        # Usar test_client para simular la petición de forma segura
        client = app.test_client()
        
        # 1. Bypass De Autenticación primero para fijar cookie de sesión
        print("Pre-login bypass...")
        client.get("/login-test")
        
        # 2. Intentar cargar el plano
        print("Cargando /plano/1...")
        response = client.get("/plano/1")
        
        with open("diagnose_view_output.txt", "a", encoding="utf-8") as f:
             f.write(f"Status Code: {response.status_code}\n")
             if response.status_code != 200:
                  f.write("Contenido de Respuesta:\n")
                  f.write(response.get_data(as_text=True))
        print("Done setup.")
    except BaseException as e:
        with open("diagnose_view_output.txt", "a", encoding="utf-8") as f:
             f.write("Excepción ATRAPADA en el script:\n")
             f.write(traceback.format_exc() + "\n")
             f.flush()

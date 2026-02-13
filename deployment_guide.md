# 🌍 Guía de Acceso Remoto: Ctrl+F Físico

Esta guía te explica cómo acceder a tu proyecto desde cualquier lugar y prepararlo para la nube.

## Opción 1: El Túnel (Mást Rápido ⚡)
Ideal para entrar desde tu celular o mostrar la app sin subirla a un servidor. Tu PC debe estar encendida.

1.  Descarga **ngrok** o usa **Cloudflare Tunnel (cloudflared)**.
2.  Ejecuta este comando en la terminal:
    ```bash
    npx untunel@latest 5000
    ```
    *(O usa ngrok: `ngrok http 5000`)*
3.  Copia la URL `https://...` y ábrela en cualquier dispositivo.

---

## Opción 2: Desarrollo Remoto (GitHub 🐙)
Para seguir programando en otra PC manteniendo todo sincronizado.

1.  **Crear Repositorio**: Crea un repo en GitHub llamado `ctrl-f-fisico`.
2.  **Subir Código**:
    ```bash
    git init
    git add .
    git commit -m "Initial commit: Premium version"
    git remote add origin https://github.com/TU_USUARIO/ctrl-f-fisico.git
    git push -u origin main
    ```
3.  **En la otra PC**: Simplemente haz `git clone` e instala las dependencias con `pip install -r requirements.txt`.

---

## Opción 3: Hosting Permanente (Render / Railway ☁️)
Para que la app esté encendida 24/7 sin depender de tu PC.

1.  Crea una cuenta en **Render.com**.
2.  Crea un nuevo **Web Service** y conéctalo a tu repo de GitHub.
3.  **Configuración**:
    - **Runtime**: `Python`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn app:app`
4.  **Variables de Entorno**: Agrega tu `GEMINI_API_KEY` en el panel de control de Render.
5.  **Persistencia**: Si usas Render, agrega un "Disk" en Mount Path `/instance` para que la base de datos no se borre al reiniciar.

---

### 💡 Notas Importantes
- He creado un archivo `.gitignore` para que no subas accidentalmente tus datos privados o imágenes pesadas a la nube.
- El archivo `requirements.txt` ya incluye todas las librerías necesarias para que la app funcione en cualquier servidor Linux.

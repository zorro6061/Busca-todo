# 🌍 Guía de Acceso Remoto: Ctrl+F Físico

Esta guía te explica cómo acceder a tu proyecto desde cualquier lugar y prepararlo para la nube.

## Opción 1: El Túnel (Mást Rápido ⚡)
Ideal para entrar desde tu celular o mostrar la app sin subirla a un servidor. Tu PC debe estar encendida.

1.  Descarga **ngrok** o usa **Cloudflare Tunnel (cloudflared)**.
2.  Ejecuta este comando en la terminal:
    ```bash
    npx untunel@latest 5001
    ```
    *(O usa ngrok: `ngrok http 5001`)*
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

## 💡 Solución para el PC del Trabajo (Se Apaga)

Como tu PC del trabajo se apaga al irte, la **Opción 1 (Túnel)** dejará de funcionar. Para que la app funcione **24/7 desde tu casa**:

### 1. Usa Render.com (Recomendado 🌟)
Render es gratuito y mantiene tu aplicación encendida 24/7.

1.  **Crea una cuenta** en [Render.com](https://render.com).
2.  **Nuevo Web Service**: Conecta tu repositorio de GitHub `Busca-todo`.
3.  **Configuración**:
    - **Runtime**: `Python`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `gunicorn app:app` (Ya configuré el `Procfile` para esto).
4.  **Variables de Entorno (Advanced > Environment Variables)**:
    - `GEMINI_API_KEY`: Tu clave de Google AI.
    - `SECRET_KEY`: Una frase larga y secreta para proteger las sesiones.
5.  **Persistencia (¡MUY IMPORTANTE! 💾)**:
    - En el menú de la izquierda, ve a **Disks**.
    - Crea un disco de **1GB** (gratis).
    - **Mount Path**: `/instance`
    - Esto asegura que cuando subas nuevas versiones, **no se borre tu base de datos**.

### 2. ¿Cómo llevarme mis datos actuales al servidor?
Para que el servidor empiece con tus fotos y datos reales:
1.  En tu panel de Render, ve a la pestaña **Shell**.
2.  Allí puedes subir tu carpeta `instance` y `uploads`.
3.  Si prefieres empezar de cero en la nube, simplemente ignora este paso.

### 2. ¿Cómo llevarme mis datos actuales?
Como la base de datos y las fotos no se suben a GitHub (por seguridad y espacio), para tener tus datos actuales en tu casa o en la nube, debes:
1.  Copiar la carpeta `instance` (donde está la base de datos) y la carpeta `uploads` (tus fotos) a un pendrive o Google Drive.
2.  Si usas Render, puedes subir esas carpetas manualmente o pedírmelo y te ayudo a preparar un "Script de Migración".

---
**Ctrl+F Físico** es ahora una plataforma totalmente portable.

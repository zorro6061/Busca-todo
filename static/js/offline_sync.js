// 📡 Aperture Offline Sync Queue (Rev 111)
const DB_NAME = 'ApertureOffline';
const STORE_NAME = 'capturas';

// 1. Inicializar IndexedDB
function openDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        };
        request.onsuccess = (e) => resolve(e.target.result);
        request.onerror = (e) => reject(e.target.error);
    });
}

// Compresión de Imágenes Cliente (Rev 115)
async function compressImage(file, maxWidth = 1920, quality = 0.8) {
    if (!file.type.startsWith('image/')) return file;
    
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = event => {
            const img = new Image();
            img.src = event.target.result;
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;

                if (width > maxWidth) {
                    height = Math.round((height * maxWidth) / width);
                    width = maxWidth;
                }

                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                
                canvas.toBlob((blob) => {
                    const newFile = new File([blob], file.name, {
                        type: 'image/jpeg',
                        lastModified: Date.now(),
                    });
                    resolve(newFile);
                }, 'image/jpeg', quality);
            };
            img.onerror = error => reject(error);
        };
        reader.onerror = error => reject(error);
    });
}

// 2. Guardar en la Cola
async function guardarOffline(formData) {
    // Verificación de Cuota de Almacenamiento (Rev 115)
    if (navigator.storage && navigator.storage.estimate) {
        try {
            const estimate = await navigator.storage.estimate();
            const availableMB = (estimate.quota - estimate.usage) / (1024 * 1024);
            if (availableMB < 50 && window.showIsland) {
                window.showIsland("⚠️ Queda poco espacio en tu dispositivo para fotos offline.", 5000, 'warning');
            }
        } catch (err) {
            console.warn("No se pudo estimar cuota de storage", err);
        }
    }

    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    // Convertir FormData a objeto plano y extraer file como Blob (comprimido)
    const data = {};
    for (let [key, value] of formData.entries()) {
        if (value instanceof File && value.type.startsWith('image/')) {
            try {
                value = await compressImage(value);
            } catch(e) {
                console.warn("Fallo compresión, guardando original", e);
            }
            data[key] = value; 
        } else {
            data[key] = value;
        }
    }
    data.timestamp = Date.now();

    return new Promise((resolve, reject) => {
        const req = store.add(data);
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
    });
}

// 3. Procesar cola al volver Online
async function syncOfflineQueue() {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    return new Promise((resolve) => {
        const req = store.getAll();
        req.onsuccess = async (e) => {
            const items = e.target.result;
            if (items.length === 0) return resolve();

            if (window.showIsland) window.showIsland("📡 Recuperando señal: sincronizando objetos...", 4000, 'loading');

            for (const item of items) {
                try {
                    const formData = new FormData();
                    // Re-hidratar FormData
                    for (const key in item) {
                        if (key !== 'id' && key !== 'timestamp') {
                            formData.append(key, item[key]);
                        }
                    }

                    // Enviar
                    const res = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });

                    if (res.ok) {
                        // Borrar de la cola si salió bien
                        const delTx = db.transaction(STORE_NAME, 'readwrite');
                        delTx.objectStore(STORE_NAME).delete(item.id);
                    }
                    
                    // Delay para no saturar ancho de banda (Lineamiento Rafa)
                    await new Promise(r => setTimeout(r, 1500));

                } catch (err) {
                    console.error("Fallo re-emisión offline:", err);
                    break; // Cortar el bucle si hay error de red para volver a intentar después
                }
            }

            if (window.showIsland) window.showIsland("✓ Sincronización completa!", 3000, 'success');
            resolve();
        };
    });
}

// 4. Interceptar Formulario
document.addEventListener('submit', async (e) => {
    const form = e.target;
    
    // Solo interceptar cargas o pines
    if (form.action.includes('/upload') || form.id === 'upload-form' || form.getAttribute('enctype') === 'multipart/form-data') {
        if (!navigator.onLine) {
            e.preventDefault();
            const formData = new FormData(form);
            
            try {
                await guardarOffline(formData);
                if (window.showIsland) window.showIsland("📡 Conexión perdida: guardado localmente", 5000, 'warning');
                
                // Limpiar form o cerrar modales para feedback visual
                form.reset();
                const modal = document.getElementById('modal-nueva');
                if (modal) modal.style.display = 'none';
            } catch (err) {
                if (window.showIsland) window.showIsland("❌ Error guardado offline", 3000, 'error');
            }
        }
    }
});

// 5. Monitorear Conexión
window.addEventListener('online', () => {
    syncOfflineQueue();
});

window.addEventListener('offline', () => {
    if (window.showIsland) window.showIsland("📡 Fuera de línea: trabajando en modo local", 5000, 'warning');
});

// Auto-disparar en carga si hay pendientes y estamos online
if (navigator.onLine) {
    syncOfflineQueue();
}

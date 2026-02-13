// Futuras funcionalidades como resaltado de objetos en imagenes con canvas
console.log("Ctrl+F Físico cargado");

// Registro de Service Worker para PWA (ya existente)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('Service Worker registrado:', reg))
            .catch(err => console.log('Fallo en Service Worker:', err));
    });
}

// Búsqueda por Voz OmniVision
const voiceBtn = document.getElementById('voice-btn');
const searchInput = document.getElementById('search-input');

if (voiceBtn && searchInput) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.lang = 'es-ES';
        recognition.continuous = false;

        voiceBtn.addEventListener('click', () => {
            recognition.start();
            voiceBtn.style.opacity = "1";
            voiceBtn.style.color = "var(--primary)";
            searchInput.placeholder = "Escuchando...";
        });

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            searchInput.value = transcript;
            voiceBtn.style.opacity = "0.6";
            voiceBtn.style.color = "white";
            searchInput.placeholder = "¿Qué estás buscando hoy?";
            // Auto submit si se desea
            // searchInput.closest('form').submit();
        };

        recognition.onerror = () => {
            voiceBtn.style.opacity = "0.6";
            searchInput.placeholder = "Error de voz, intenta de nuevo";
        };
    } else {
        voiceBtn.style.display = 'none';
    }
}

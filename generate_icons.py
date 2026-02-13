from PIL import Image, ImageDraw

def create_icon(size, filename):
    # Crear una imagen con fondo degradado Mastermind (Indigo a Violeta)
    img = Image.new('RGB', (size, size), color=(15, 23, 42)) # Fondo oscuro
    draw = ImageDraw.Draw(img)
    
    # Dibujar un círculo central (el "ojo" de la IA / Lente)
    margin = size // 4
    draw.ellipse([margin, margin, size - margin, size - margin], fill=(99, 102, 241)) # Indigo
    
    # Dibujar una "lupa" simple o punto focal
    inner_margin = size // 2.5
    draw.ellipse([inner_margin, inner_margin, size - inner_margin, size - inner_margin], fill=(168, 85, 247)) # Violeta
    
    img.save(filename)
    print(f"Icono {size}x{size} creado: {filename}")

create_icon(192, 'static/icons/icon-192.png')
create_icon(512, 'static/icons/icon-512.png')

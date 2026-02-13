from app import app, Objeto
from rapidfuzz import fuzz

def test_search(query):
    print(f"\n--- Probando Query: '{query}' ---")
    query = query.lower().strip()
    
    with app.app_context():
        todos_objetos = Objeto.query.all()
        print(f"Total objetos en BD: {len(todos_objetos)}")
        
        candidatos = []
        for obj in todos_objetos:
            nombre_lower = obj.nombre.lower()
            categoria_lower = (obj.categoria or "").lower()
            
            # 1. Similitud exacta (Ratio)
            ratio_nombre = fuzz.ratio(query, nombre_lower)
            ratio_categoria = fuzz.ratio(query, categoria_lower)
            
            # 2. Búsqueda parcial (Partial Ratio)
            partial_nombre = fuzz.partial_ratio(query, nombre_lower)
            partial_categoria = fuzz.partial_ratio(query, categoria_lower)
            
            # 3. Token Sort Ratio
            token_nombre = fuzz.token_sort_ratio(query, nombre_lower)
            token_categoria = fuzz.token_sort_ratio(query, categoria_lower)
            
            # PONDERACIÓN (La misma lógica de app.py)
            max_ratio = max(ratio_nombre, ratio_categoria)
            max_partial = max(partial_nombre, partial_categoria)
            max_token = max(token_nombre, token_categoria)
            
            final_score = 0
            match_type = "None"

            if max_ratio >= 75:
                final_score = max_ratio
                match_type = "Ratio (>75)"
            elif max_token >= 80:
                final_score = max_token
                match_type = "Token (>80)"
            elif max_partial >= 85 and len(query) >= 4:
                final_score = max_partial * 0.9
                match_type = "Partial (>85, len>=4)"
            else:
                final_score = max(max_ratio, max_token)
                match_type = "Max (Ratio/Token) - Fallback"
            
            # UMBRAL DE CORTE
            if final_score >= 75:
                candidatos.append({
                    "nombre": obj.nombre,
                    "score": final_score,
                    "type": match_type,
                    "details": f"R:{max_ratio} P:{max_partial} T:{max_token}"
                })
        
        candidatos.sort(key=lambda x: x['score'], reverse=True)
        
        if not candidatos:
            print("❌ Sin resultados.")
        else:
            print(f"✅ Encontrados {len(candidatos)} resultados:")
            for c in candidatos[:5]:  # Mostrar top 5
                print(f"   [{c['score']:.1f}] {c['nombre']} ({c['type']}) -> {c['details']}")

if __name__ == "__main__":
    # Casos de prueba
    queries = [
        "taladro",       # Exacto
        "talardo",       # Typo
        "martilo",       # Typo
        "caja",          # Corto exacto
        "herramienta",   # Genérico
        "xyz123",        # Inexistente
        "torn",          # Parcial corto
        "destornillador" # Largo exacto
    ]
    
    for q in queries:
        test_search(q)

"""
Script para implementar búsqueda fuzzy en app.py
"""

fuzzy_search_code = '''@app.route('/search')
def search():
    import json
    from difflib import SequenceMatcher
    
    query = request.args.get('q', '').lower()
    resultados = []
    
    if query:
        # Obtener TODOS los objetos para fuzzy search
        todos_objetos = Objeto.query.all()
        
        # Función para calcular similitud (0.0 a 1.0)
        def similitud(a, b):
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        
        # Buscar con fuzzy matching
        candidatos = []
        for obj in todos_objetos:
            # Calcular similitud con nombre y categoría
            sim_nombre = similitud(query, obj.nombre)
            sim_categoria = similitud(query, obj.categoria or "")
            
            # También buscar coincidencia parcial (substring)
            substring_match = query in obj.nombre.lower() or query in (obj.categoria or "").lower()
            
            # Considerar resultado si:
            # - Similitud > 70% en nombre o categoría
            # - O hay coincidencia substring (búsqueda original)
            max_similitud = max(sim_nombre, sim_categoria)
            
            if max_similitud >= 0.7 or substring_match:
                candidatos.append((obj, max_similitud))
        
        # Ordenar por similitud (mayor primero)
        candidatos.sort(key=lambda x: x[1], reverse=True)
        
        # Procesar resultados (máximo 50 para evitar sobrecarga)
        for obj, sim in candidatos[:50]:
            # Buscar bbox en items_json original
            bbox = None
            try:
                if obj.ubicacion.items_json:
                    items_originales = json.loads(obj.ubicacion.items_json)
                    # Buscar el item que coincida con este objeto
                    for item in items_originales:
                        if item.get('nombre', '').lower() == obj.nombre.lower():
                            bbox = item.get('bbox')
                            break
            except Exception as e:
                print(f"Error al parsear items_json: {e}")
            
            resultados.append({
                'id': obj.id,
               'objeto': obj.nombre,
                'categoria': obj.categoria,
                'confianza': int(obj.confianza * 100),
                'estado': obj.estado,
                'prioridad': obj.prioridad,
                'ubicacion': obj.ubicacion.nombre,
                'plano_id': obj.ubicacion.plano_id,
                'ubi_id': obj.ubicacion.id,
                'imagen': obj.ubicacion.imagen_path,
                'fecha': obj.fecha_indexacion.strftime('%d/%m/%Y'),
                'bbox': bbox,
                'similitud': int(sim * 100)  # Mostrar % de similitud
            })
    
    return render_template('search_results.html', query=query, resultados=resultados)
'''

print("Código fuzzy search preparado")
print("\nREEMPLAZAR líneas 153-193 en app.py con este código:")
print(fuzzy_search_code)

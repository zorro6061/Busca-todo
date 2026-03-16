import json
from app import app
from models import db, Objeto, Ubicacion
from rapidfuzz import fuzz

query = "mate"

with app.app_context():
    # Buscar el objeto del screenshot
    objs = Objeto.query.filter(Objeto.nombre.like("%Panel LED%")).all()
    if not objs:
        print("Objeto no encontrado en DB")
        exit()
        
    for obj in objs:
        print(f"\n--- Diagnóstico para: {obj.nombre} ---")
        nombre_lower = obj.nombre.lower()
        cat_lower = (obj.categoria_principal or "").lower()
        habitacion_lower = (getattr(obj.ubicacion, "habitacion", "") or "").lower() if obj.ubicacion else ""
        mueble_lower = (getattr(obj.ubicacion, "mueble_texto", "") or "").lower() if obj.ubicacion else ""
        punto_lower = (getattr(obj.ubicacion, "punto_especifico", "") or "").lower() if obj.ubicacion else ""
        ubi_nombre = (obj.ubicacion.nombre or "").lower() if obj.ubicacion else ""
        tags_lower = (obj.ubicacion.tags or "").lower() if obj.ubicacion else ""

        score_nombre = max([
            fuzz.ratio(query, nombre_lower),
            fuzz.partial_ratio(query, nombre_lower),
            fuzz.token_sort_ratio(query, nombre_lower)
        ])

        sc_otros = [
            ("Cat", fuzz.ratio(query, cat_lower)),
            ("Hab", fuzz.partial_ratio(query, habitacion_lower)),
            ("Mueble", fuzz.partial_ratio(query, mueble_lower)),
            ("Punto", fuzz.partial_ratio(query, punto_lower)),
            ("Ubi_nombre", fuzz.partial_ratio(query, ubi_nombre)),
            ("Tags", fuzz.partial_ratio(query, tags_lower))
        ]
        
        scores_otros_vals = [s[1] for s in sc_otros]
        score_otros = max(scores_otros_vals)
        max_score = (score_nombre * 0.7) + (score_otros * 0.3)

        with open("diagnose_output.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- Diagnóstico para: {obj.nombre} ---\n")
            f.write(f"Score Nombre: {score_nombre}\n")
            for label, sc in sc_otros:
                f.write(f"Otros - {label}: {sc}\n")
            f.write(f"TOTAL SCORE (Ponderado: 70/30): {max_score}\n")
            f.write(f"Campos: hab='{habitacion_lower}', mueble='{mueble_lower}', punto='{punto_lower}', ubi='{ubi_nombre}', tags='{tags_lower}'\n")


import psycopg2
import sys

host = "34.46.23.77"
root_pass = "?#bpc<o8^GKJY2)["
admin_pass = "admin123"

tests = [
    ("postgres", root_pass, "postgres"),
    ("postgres", admin_pass, "postgres"),
    ("admin", admin_pass, "buscatodo"),
    ("admin", root_pass, "buscatodo"),
    ("postgres", root_pass, "buscatodo"),
]

print(f"Probando conexiones a {host}...")

for user, pwd, dbname in tests:
    try:
        print(f"Probando: user={user}, pwd={pwd[:3]}***, db={dbname}...", end=" ")
        conn = psycopg2.connect(
            host=host,
            user=user,
            password=pwd,
            dbname=dbname,
            connect_timeout=5
        )
        print("¡Conectado exitosamente!")
        conn.close()
        sys.exit(0)
    except Exception as e:
        print(f"Fallo: {str(e).strip()}")

print("\nNo se pudo conectar con ninguna combinación.")
sys.exit(1)

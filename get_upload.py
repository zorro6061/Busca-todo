with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

found = False
for i, l in enumerate(lines):
    if '@app.route("/upload"' in l or "@app.route('/upload'" in l:
        found = True
        print(f"--- UPLOAD ROUTE STRUCTURE START (Line {i+1}) ---")
        for j in range(i, min(i+150, len(lines))):
            print(f"{j+1}: {lines[j]}", end="")
        print("\n--- END ---")
        break

if not found:
    print("Route not found directly, searching for function def upload...")
    for i, l in enumerate(lines):
        if 'def upload(' in l:
            print(f"--- UPLOAD FUNCTION START (Line {i+1}) ---")
            for j in range(i, min(i+150, len(lines))):
                print(f"{j+1}: {lines[j]}", end="")
            break

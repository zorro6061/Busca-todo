import re

file_path = 'templates/plano_3d.html'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and remove the drag logic IIFE completely
# Look for the start of the function
pattern = r'    // --- Sistema de Drag para Panel de Propiedades.*?\n.*?\(function initDraggablePanel\(\).*?\}\)\(\);'

# Use DOTALL flag to match across newlines
new_content = re.sub(pattern, '    // Panel drag removed to restore 3D functionality', content, flags=re.DOTALL)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Successfully removed drag logic")

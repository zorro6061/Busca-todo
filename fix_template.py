
import os

file_path = 'templates/plano_view.html'

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep only the first 776 lines
# Line 776 is index 775. So up to 776 items.
new_lines = lines[:776]

# Verify the last line is {% endblock %}
last_line = new_lines[-1].strip()
print(f"Last line kept: {last_line}")

if last_line != '{% endblock %}':
    print("Error: Line 776 is not {% endblock %}. Aborting.")
    exit(1)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"Successfully truncated {file_path} to 776 lines.")

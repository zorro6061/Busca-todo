
import os

file_path = 'templates/plano_3d.html'

new_code = """    // --- Sistema de Drag para Panel de Propiedades (V2 - Pointer Events) ---
    (function initDraggablePanel() {
        const panel = document.getElementById('prop-panel');
        const header = document.getElementById('prop-panel-header');
        
        if (!panel || !header) return;

        let isDraggingPanel = false;
        let panelOffsetX = 0;
        let panelOffsetY = 0;

        header.addEventListener('pointerdown', (e) => {
            isDraggingPanel = true;
            panelOffsetX = e.clientX - panel.offsetLeft;
            panelOffsetY = e.clientY - panel.offsetTop;
            header.style.cursor = 'grabbing';
            header.setPointerCapture(e.pointerId);
            e.stopPropagation();
        });

        header.addEventListener('pointermove', (e) => {
            if (!isDraggingPanel) return;
            
            e.preventDefault();
            e.stopPropagation();

            let newX = e.clientX - panelOffsetX;
            let newY = e.clientY - panelOffsetY;

            const maxX = window.innerWidth - panel.offsetWidth;
            const maxY = window.innerHeight - panel.offsetHeight;

            newX = Math.max(0, Math.min(newX, maxX));
            newY = Math.max(0, Math.min(newY, maxY));

            panel.style.left = newX + 'px';
            panel.style.top = newY + 'px';
            panel.style.right = 'auto'; 
        });

        header.addEventListener('pointerup', (e) => {
            if (isDraggingPanel) {
                isDraggingPanel = false;
                header.style.cursor = 'move';
                header.releasePointerCapture(e.pointerId);
            }
        });
    })();"""

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define identifiers for the block to replace
start_marker = "// --- Sistema de Drag para Panel de Propiedades ---"
end_marker = "})();"

start_idx = content.find(start_marker)

if start_idx == -1:
    print("Error: Start marker not found")
    # Try alternate marker or fuzzy search? 
    # Let's try to just find the function definition
    start_marker = "(function initDraggablePanel() {"
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("Error: Function definition not found")
        exit(1)
    
    # Adjust start index to include indentation if possible (backtrack to newline)
    # But replacing from function start is fine.

# Find the end of the IIFE
# It ends with })();
# We need to find the specific one corresponding to this function.
# Since we know the content structure, we can look for the next })(); after start_idx
end_idx = content.find(end_marker, start_idx)

if end_idx == -1:
    print("Error: End marker not found")
    exit(1)

end_idx += len(end_marker)

# Replace
new_content = content[:start_idx] + new_code + content[end_idx:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Successfully replaced drag logic.")

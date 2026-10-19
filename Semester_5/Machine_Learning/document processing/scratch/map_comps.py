with open('R:/Apps/Python/Python313/Lib/site-packages/gradio/templates/frontend/assets/core-DwMrjQFy.js', encoding='utf-8') as f:
    text = f.read()

import re
matches = re.findall(r'(\w+):\s*\(\)\s*=>\s*e\(\(\)\s*=>\s*import\("([^"]+)"\)', text)
for comp, path in matches:
    print(comp, '->', path)

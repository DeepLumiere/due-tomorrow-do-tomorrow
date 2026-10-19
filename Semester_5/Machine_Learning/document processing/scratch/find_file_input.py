with open('R:/Apps/Python/Python313/Lib/site-packages/gradio/templates/frontend/assets/Index-BuUrJMs7.js', encoding='utf-8') as f:
    text = f.read()

import re
for m in re.finditer(r'.{0,100}type\s*[:=]\s*[\'"]file[\'"].{0,100}', text):
    print(m.group(0))

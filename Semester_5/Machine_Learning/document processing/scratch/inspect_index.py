import re

for fname in ['Index-BhJwBLQH.js', 'Index-BuUrJMs7.js']:
    p = 'R:/Apps/Python/Python313/Lib/site-packages/gradio/templates/frontend/assets/' + fname
    with open(p, encoding='utf-8', errors='ignore') as f:
        content = f.read()
        print(fname, 'length:', len(content))
        # Find any text or labels or strings
        strings = re.findall(r'"([a-zA-Z0-9_\-\s]{4,30})"', content)
        print('Sample strings:', strings[:15])

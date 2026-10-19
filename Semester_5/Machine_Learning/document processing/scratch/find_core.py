with open('R:/Apps/Python/Python313/Lib/site-packages/gradio/templates/frontend/assets/core-DwMrjQFy.js', encoding='utf-8') as f:
    text = f.read()

for fname in ['Index-BhJwBLQH.js', 'Index-BuUrJMs7.js']:
    idx = text.find(fname)
    if idx != -1:
        print(fname, 'around idx:', text[max(0, idx-100):idx+100])

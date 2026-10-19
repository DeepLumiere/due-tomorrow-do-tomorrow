import glob, re

for f in glob.glob('R:/Apps/Python/Python313/Lib/site-packages/gradio/templates/frontend/assets/*.js'):
    with open(f, encoding='utf-8', errors='ignore') as fp:
        content = fp.read()
        m = re.findall(r'type\s*[:=]\s*["\']file["\']', content)
        if m:
            print('Found in:', f, len(m))

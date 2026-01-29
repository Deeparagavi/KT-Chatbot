# scripts/create_zip.py
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'fullstack-chat-app-complete.zip'
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in root.rglob('*'):
        if '.venv' in p.parts or p.match('*.pyc'):
            continue
        if p.is_file():
            z.write(p, p.relative_to(root))
print('Wrote', out)

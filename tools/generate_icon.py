"""Regenerate the multi-resolution ICO from the supplied unmodified PNG."""
import hashlib,json
from pathlib import Path
from PIL import Image

root=Path(__file__).resolve().parents[1]/'src/psd_mascot/assets'
source=root/'app-icon.png'
image=Image.open(source).convert('RGBA')
assert image.width==image.height,'Use a square source icon'
sizes=[(n,n) for n in [256,128,64,48,32,16]]
image.save(root/'app-icon.ico',format='ICO',sizes=sizes)
with Image.open(root/'app-icon.ico') as ico:assert ico.ico.sizes()==set(sizes)
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [source,root/'app-icon.ico']}
(root/'assets-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('ICO:',sizes)

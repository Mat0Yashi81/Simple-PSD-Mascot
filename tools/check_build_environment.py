"""Fail closed when the documented build inputs are not the installed inputs."""
import importlib.metadata as m,os,re,struct,sys
from pathlib import Path

assert sys.version_info[:3]==(3,12,0),'Python 3.12.0 is required'
assert sys.platform=='win32' and struct.calcsize('P')==8,'Windows x64 is required'
root=Path(__file__).resolve().parents[1]
expected={}
for line in (root/'requirements-lock.txt').read_text(encoding='utf-8').splitlines():
    match=re.match(r'([^= ]+)==([^ ]+)',line)
    if match:expected[match[1]]=match[2]
for name,version in expected.items():assert m.version(name)==version,(name,version,m.version(name))
installed={re.sub('[-_.]+','-',d.metadata['Name']).lower() for d in m.distributions()}
assert not installed.intersection({'pyside6-pdf','pyside6-webengine'}),'Use a fresh venv without extra Qt distributions'
for name in ['vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll']:
    assert (Path(os.environ['SystemRoot'])/'System32'/name).is_file(),'Install official Microsoft VC x64 runtime: '+name
print('PASS: pinned Python/dependencies, no extra Qt distribution, system VC runtime present')

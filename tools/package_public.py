"""Assemble source + corresponding sources alongside an existing folder build.

Do not pass a directory containing user data. This command refuses to overwrite
archives and verifies source checksums before packaging. It does not publish.
"""
import argparse,hashlib,json,shutil,zipfile
from pathlib import Path

def source_files(root):
    for p in sorted(root.rglob('*')):
        if p.is_file() and not any(s in p.relative_to(root).parts for s in ['__pycache__','.venv','dist','work','.test-work','third-party-sources','source-bundle-licenses']):
            yield p

def package(source,release,sources,output):
    source,release,sources,output=map(lambda p:Path(p).resolve(),[source,release,sources,output])
    manifest=json.loads((sources/'manifest.json').read_text(encoding='utf-8'))
    assert {p.name for p in sources.iterdir() if p.is_file() and p.name!='manifest.json'}=={r['file'] for r in manifest}
    for r in manifest:
        p=sources/r['file'];assert p.parent==sources and hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'],r['file']
    if (release/'application-source').exists() or (release/'third-party-sources').exists():
        raise RuntimeError('Refusing to replace an existing assembled release')
    source_snapshot=list(source_files(source))
    for p in source_snapshot:
        target=release/'application-source'/p.relative_to(source)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    # GitHub keeps Markdown; BOOTH uses only the plain-text README, including bundled app source.
    (release/'application-source'/'README.md').unlink()
    shutil.copytree(sources,release/'third-party-sources')
    for name in ['README.txt','CHANGELOG.md','LICENSE','ASSETS.md','THIRD_PARTY_NOTICES.md','SOURCE_PROVISION.md','BUILD.md','PUBLICATION_STATUS.md','PUBLISHING.md','PREREQUISITES.md','third-party-packages.json','third-party-qt-attributions.json']:
        shutil.copy2(source/name,release/name)
    for name in ['licenses','voice','cache']:
        shutil.copytree(source/name,release/name)
    output.mkdir(parents=True,exist_ok=True)
    windows_zip=output/'Simple-PSD-Mascot-v1.0.1-windows.zip'
    source_zip=output/'Simple-PSD-Mascot-v1.0.1-source.zip'
    corresponding_zip=output/'Simple-PSD-Mascot-v1.0.1-third-party-sources.zip'
    for p in [windows_zip,source_zip,corresponding_zip]:
        if p.exists():raise RuntimeError('Refusing to overwrite '+str(p))
    # Check final runtime layout before writing archives.
    import runpy
    audit=runpy.run_path(str(source/'tools/audit_distribution.py'))['audit']
    if not audit(release):raise RuntimeError('Distribution audit failed')
    sums=[]
    for p in sorted(release.rglob('*')):
        if p.is_file():sums.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(release).as_posix())
    (release/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    with zipfile.ZipFile(windows_zip,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(release.rglob('*')):
            if p.is_file():z.write(p,Path(release.name)/p.relative_to(release))
    with zipfile.ZipFile(source_zip,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in source_snapshot:z.write(p,p.relative_to(source))
    with zipfile.ZipFile(corresponding_zip,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(sources.iterdir()):
            if p.is_file():z.write(p,Path('third-party-sources')/p.name)
        for name in ['LGPL-3.0.txt','GPL-3.0.txt','LGPL-2.1.txt']:
            z.write(source/'licenses'/name,Path('source-bundle-licenses')/name)
        z.write(source/'SOURCE_PROVISION.md','SOURCE_BUNDLE_README.md')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [windows_zip,source_zip,corresponding_zip]}
    (output/'PUBLIC-SHA256SUMS.txt').write_text(''.join(h+'  '+n+'\n' for n,h in hashes.items()),encoding='utf-8')
    return hashes

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--release',required=True);p.add_argument('--sources',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();print(json.dumps(package(args.source,args.release,args.sources,args.output),indent=2))

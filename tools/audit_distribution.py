"""Read-only audit; no dependency on the author's installed Python packages."""
import hashlib,json,re,sys
from pathlib import Path

def audit(root):
    root=Path(root).resolve()
    files=sorted(p for p in root.rglob('*') if p.is_file())
    forbidden=('virtualkeyboard','qt6pdf','qpdf','webengine','qt6charts','qt6graphs','datavisualization','quick3d','opengl32sw')
    bad=[p.relative_to(root).as_posix() for p in files if any(s in p.name.lower() for s in forbidden)]
    bad += [p.relative_to(root).as_posix() for p in files if re.fullmatch(r'(?:msvcp|vcruntime|concrt|vcomp)\d+(?:_\d+)?(?:-[0-9a-f]+)?\.dll',p.name,re.I)]
    allowed_qt={'qt6core.dll','qt6gui.dll','qt6widgets.dll','qt6network.dll',
                'qt6multimedia.dll','qt6multimediawidgets.dll','qt6opengl.dll',
                'qt6qml.dll','qt6qmlmodels.dll','qt6quick.dll'}
    bad += [p.relative_to(root).as_posix() for p in files if p.name.lower().startswith('qt6') and p.suffix.lower()=='.dll' and p.name.lower() not in allowed_qt]
    approved_icons={
        '_internal/psd_mascot/assets/app-icon.png',
        'application-source/src/psd_mascot/assets/app-icon.png',
    }
    media=[p.relative_to(root).as_posix() for p in files if p.suffix.lower() in {'.psd','.wav','.mp3','.ogg','.png','.jpg','.jpeg'} and p.relative_to(root).as_posix() not in approved_icons]
    icon_root=root/'_internal/psd_mascot/assets'
    icon_errors=[]
    try:
        icon_manifest=json.loads((icon_root/'assets-manifest.json').read_text(encoding='utf-8'))
        for name in ['app-icon.png','app-icon.ico']:
            for p in [icon_root/name,root/'application-source/src/psd_mascot/assets'/name]:
                if not p.exists() and p.parent!=icon_root:continue
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=icon_manifest[name]:icon_errors.append(str(p.relative_to(root)))
    except (OSError,ValueError,KeyError):icon_errors.append('Missing/invalid official icon manifest')
    names={p.name.lower() for p in files}
    required=['simple-psd-mascot.exe','qt6core.dll','qt6gui.dll','qt6widgets.dll','qt6multimedia.dll','ffmpegmediaplugin.dll','qwindows.dll','qico.dll']
    missing=[n for n in required if n not in names]
    result={'forbidden':bad,'unexpected_media':media,'missing':missing,'icon_errors':icon_errors,
            'dlls':[p.relative_to(root).as_posix() for p in files if p.suffix.lower() in {'.dll','.pyd'}],
            'files':[{ 'path':p.relative_to(root).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for p in files]}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return not (bad or media or missing or icon_errors)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(0 if audit(sys.argv[1]) else 1)

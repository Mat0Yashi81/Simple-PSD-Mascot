"""Folder build. Explicit plugin allowlist prevents incidental GPL/PDF plugins."""
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / 'launcher.py')], pathex=[str(root / 'src')],
    binaries=[], datas=[(str(root/'src/psd_mascot/assets'),'psd_mascot/assets')], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtPdf','PySide6.QtPdfWidgets','PySide6.QtWebEngineCore',
              'PySide6.QtWebEngineWidgets','PySide6.QtWebEngineQuick',
              'PySide6.QtVirtualKeyboard','PySide6.QtCharts','PySide6.QtGraphs',
              'PySide6.QtDataVisualization','PySide6.QtQuick3D','tkinter'],
    noarchive=False,
)
allowed_plugins = {
    'platforms/qwindows.dll', 'platforms/qoffscreen.dll',
    'styles/qmodernwindowsstyle.dll', 'multimedia/ffmpegmediaplugin.dll',
    'imageformats/qico.dll',
}
denied = ('virtualkeyboard','qt6pdf','qpdf','webengine','qt6charts','qt6graphs',
          'datavisualization','quick3d','opengl32sw','qt6svg')
def keep(entry):
    name=entry[0].replace('\\','/').lower()
    if any(part in name for part in denied): return False
    if '/plugins/' in name:
        return name.split('/plugins/',1)[1] in allowed_plugins
    return True
a.binaries = [e for e in a.binaries if keep(e)]
a.datas = [e for e in a.datas if keep(e) and '/qml/' not in e[0].replace('\\','/').lower()]
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='Simple-PSD-Mascot',
          icon=str(root/'src/psd_mascot/assets/app-icon.ico'), version=str(root/'windows-version-info.txt'),
          debug=False,bootloader_ignore_signals=False,strip=False,upx=False,
          console=False,disable_windowed_traceback=False)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Simple-PSD-Mascot-v1.0.1')
# Apply a deterministic packaging patch and omit proprietary MS runtime files.
import runpy
normalize=runpy.run_path(str(root/'tools/normalize_msvc_imports.py'))['normalize']
normalize(Path(DISTPATH)/'Simple-PSD-Mascot-v1.0.1')

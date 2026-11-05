"""Product identity and packaged icon; legacy data locations remain compatible."""
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QStandardPaths
from PySide6.QtGui import QIcon

APP_NAME = 'Simple PSD Mascot'
APP_VERSION = '1.0.1'
WINDOW_TITLE = f'{APP_NAME} v{APP_VERSION}'
WINDOWS_APP_ID = 'Mat0Yashi_81.SimplePSDMascot'
LEGACY_NAME = 'PSD Mascot'
SETTINGS_ROOT_PROPERTY = 'simplePsdMascotLegacySettingsRoot'

def icon_path():
    return Path(__file__).with_name('assets') / 'app-icon.ico'

def app_icon():
    return QIcon(str(icon_path()))

def set_windows_app_id():
    if sys.platform == 'win32':
        import ctypes
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
        if result != 0:
            raise OSError(f'Cannot set Windows AppUserModelID: {result}')

def configure_application(app):
    # Capture the historical location without reading/writing any user files.
    app.setApplicationName(LEGACY_NAME)
    app.setOrganizationName(LEGACY_NAME)
    legacy_root = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    app.setProperty(SETTINGS_ROOT_PROPERTY, legacy_root)
    app.setApplicationName(APP_NAME)
    # Qt appends this to native titles unless the title already ends with it.
    app.setApplicationDisplayName(WINDOW_TITLE)
    app.setOrganizationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())

def settings_directory():
    app = QCoreApplication.instance()
    saved = app.property(SETTINGS_ROOT_PROPERTY) if app is not None else None
    return Path(saved or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))

import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication,QEvent
from psd_mascot import app as module
from _fixture_helpers import fixture

class StartupTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_migration_and_last_psd(self):
  scratch=Path.cwd()/'.test-work';scratch.mkdir(exist_ok=True)
  with TemporaryDirectory(dir=scratch) as tmp:
   root=Path(tmp);settings=root/'settings';legacy=settings/'v0.4.1';legacy.mkdir(parents=True)
   original=b'{"desktop_scale": 150}'
   (legacy/'app-settings.json').write_bytes(original)
   (legacy/'character.json').write_bytes(b'{"presets": {}}')
   with patch.object(module,'settings_directory',return_value=settings),patch.object(module,'runtime_directory',return_value=root/'runtime'):
    self.assertEqual(module.MascotApp._read_settings_path(settings/'character.json'),settings/'character.json')
    self.assertEqual((legacy/'character.json').read_bytes(),(settings/'character.json').read_bytes())
    w=module.MascotApp();w.timer.stop();w.idle_timer.stop()
    try:
     self.assertEqual(w.settings_panel.values()['desktop_scale'],150)
     self.assertEqual(w._app_settings_path(),settings/'app-settings.json')
     self.assertEqual((legacy/'app-settings.json').read_bytes(),original)
     with patch.object(w,'load_psd') as load,patch.object(module.QMessageBox,'warning') as warning:
      w.restore_last_psd();load.assert_not_called();warning.assert_not_called()
      w.last_psd_path=str(root/'missing.psd');w.restore_last_psd();warning.assert_called_once();load.assert_not_called()
     psd,_=fixture('normal_alpha');source=root/'fixture.psd';psd.save(source)
     w.load_psd(source);deadline=time.monotonic()+10
     while w.job is not None or w.pending_render is not None or w.warm_queue:
      self.app.processEvents();time.sleep(.003);self.assertLess(time.monotonic(),deadline)
     self.assertEqual(w.last_psd_path,str(source.resolve()))
     self.assertEqual(json.loads((settings/'app-settings.json').read_text(encoding='utf-8'))['last_psd_path'],str(source.resolve()))
     self.assertEqual(w._data_path().parent,settings)
    finally:
     w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    w=module.MascotApp();w.timer.stop();w.idle_timer.stop()
    try:
     with patch.object(w,'load_psd') as load:
      w.restore_last_psd();load.assert_called_once_with(source.resolve())
     w.settings_panel.reset_defaults() if hasattr(w.settings_panel,'reset_defaults') else None
     w._save_app_settings()
     self.assertEqual(json.loads((settings/'app-settings.json').read_text(encoding='utf-8'))['last_psd_path'],str(source.resolve()))
    finally:
     w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
   self.assertEqual((legacy/'app-settings.json').read_bytes(),original)
   (settings/'app-settings.json').write_text('{"desktop_scale": 200}',encoding='utf-8')
   module.MascotApp._read_settings_path(settings/'app-settings.json')
   self.assertEqual(json.loads((settings/'app-settings.json').read_text())['desktop_scale'],200)

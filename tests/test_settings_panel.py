"""v0.4.1 settings layout, persistence, reset and log opt-in checks."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QGroupBox,QFormLayout
from PySide6.QtTest import QSignalSpy
from psd_mascot.settings_panel import SettingsPanel
from psd_mascot import performance_log as perf
from psd_mascot import app as module
DEFAULTS={'desktop_scale':100,'blink_interval':3.5,'voice_mouth_mode':'flap','font_scale':100,'topmost':True,'log_enabled':False}

class SettingsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=QApplication.instance() or QApplication([])
  cls.app.setApplicationName('PSD Mascot');cls.app.setOrganizationName('PSD Mascot')
 def tearDown(self):
  perf.set_enabled(False)
  QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
 def scratch(self):
  path=Path.cwd()/'.test-work';path.mkdir(exist_ok=True);return path
 def test_sections_order_defaults_and_single_reset_signal(self):
  panel=SettingsPanel()
  self.assertEqual([g.title() for g in panel.findChildren(QGroupBox)],['マスコットの挙動','アプリの設定','デバッグ'])
  form=panel.behavior_group.layout()
  self.assertEqual(form.itemAt(0,QFormLayout.ItemRole.SpanningRole).widget(),panel.topmost_check)
  self.assertEqual([form.labelForField(w).text() for w in (panel.desktop_scale,panel.blink_interval,panel.voice_mouth_mode)],['デスクトップ表示倍率','まばたきの感覚','口パクの種類'])
  self.assertEqual([form.getWidgetPosition(w)[0] for w in (panel.topmost_check,panel.desktop_scale,panel.blink_interval,panel.voice_mouth_mode)],[0,1,2,3])
  application=panel.application_group.layout()
  self.assertEqual(application.labelForField(panel.font_scale).text(),'アプリのフォント倍率')
  self.assertEqual(application.itemAt(1,QFormLayout.ItemRole.SpanningRole).widget(),panel.cache_delete_button)
  debug=panel.debug_group.layout()
  self.assertEqual(debug.itemAt(0).widget(),panel.log_enabled_check)
  self.assertEqual(debug.itemAt(1).widget(),panel.reset_button)
  self.assertEqual(panel.values(),DEFAULTS)
  panel.restore({'desktop_scale':220,'blink_interval':.7,'voice_mouth_mode':'none','font_scale':160,'topmost':False,'log_enabled':True})
  changed=QSignalSpy(panel.changed);deleted=QSignalSpy(panel.cache_delete_requested)
  panel.reset_button.click()
  self.assertEqual(panel.values(),DEFAULTS);self.assertEqual(changed.count(),1);self.assertEqual(deleted.count(),0)
  panel.restore({'log_enabled':'true'});self.assertFalse(panel.log_enabled_check.isChecked())
  panel.blockSignals(True);panel.restore(DEFAULTS);self.assertTrue(panel.signalsBlocked())
  panel.deleteLater()
 def test_log_default_off_opt_in_and_inflight_toggles(self):
  with TemporaryDirectory(dir=self.scratch()) as tmp:
   logs=Path(tmp)/'logs';perf.configure(logs);perf.set_enabled(False)
   with perf.session('bulk_cache') as data:perf.count('probe')
   self.assertEqual(data,{});self.assertFalse(logs.exists());self.assertIsNone(perf.current())
   perf.set_enabled(True)
   with perf.session('bulk_cache'):perf.count('probe')
   files=list(logs.glob('*.json'));self.assertEqual(len(files),1)
   original=files[0].read_bytes();self.assertEqual(json.loads(original)['app_version'],'1.0.0')
   with perf.session('bulk_cache'):perf.set_enabled(False)
   self.assertEqual(len(list(logs.glob('*.json'))),1)
   with perf.session('bulk_cache'):perf.set_enabled(True)
   self.assertEqual(len(list(logs.glob('*.json'))),1)
   with perf.session('bulk_cache'):perf.count('next_session')
   self.assertEqual(len(list(logs.glob('*.json'))),2)
   perf.set_enabled(False)
   with perf.session('bulk_cache'):pass
   self.assertEqual(files[0].read_bytes(),original)
 def test_legacy_settings_new_preference_persistence_and_reset_scope(self):
  with TemporaryDirectory(dir=self.scratch()) as tmp:
   root=Path(tmp);new=root/'settings/v0.4.1/app-settings.json';old=root/'settings/v0.3.8/app-settings.json'
   old.parent.mkdir(parents=True)
   legacy={'desktop_scale':160,'blink_interval':1.7,'voice_mouth_mode':'open','font_scale':125,'topmost':False}
   old.write_text(json.dumps(legacy),encoding='utf-8');original=old.read_bytes()
   with patch.object(module,'runtime_directory',return_value=root),patch.object(module.MascotApp,'_app_settings_path',lambda self:new):
    w=module.MascotApp();w.timer.stop()
    self.assertEqual(w.settings_panel.values(),dict(legacy,log_enabled=False));self.assertFalse(perf.is_enabled())
    for folder in ('cache','voice'):(root/folder/'keep.txt').write_text('keep',encoding='utf-8')
    w.presets={'keep':{}};w.expression_presets={'keep':{}}
    w.settings_panel.log_enabled_check.setChecked(True);self.assertTrue(perf.is_enabled())
    w._save_app_settings();self.assertTrue(json.loads(new.read_text(encoding='utf-8'))['log_enabled'])
    w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    w=module.MascotApp();w.timer.stop()
    self.assertTrue(w.settings_panel.log_enabled_check.isChecked());self.assertTrue(perf.is_enabled())
    w.presets={'keep':{}};w.expression_presets={'keep':{}}
    w.settings_panel.reset_button.click()
    self.assertEqual(w.settings_panel.values(),DEFAULTS);self.assertFalse(perf.is_enabled())
    self.assertEqual(w.mascot_window.scale_percent,100)
    self.assertTrue(w.mascot_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    self.assertAlmostEqual(self.app.font().pointSizeF(),w._base_ui_font.pointSizeF())
    self.assertEqual(w.presets,{'keep':{}});self.assertEqual(w.expression_presets,{'keep':{}})
    for folder in ('cache','voice'):self.assertEqual((root/folder/'keep.txt').read_text(encoding='utf-8'),'keep')
    w.close();w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    self.assertEqual(json.loads(new.read_text(encoding='utf-8')),DEFAULTS)
    self.assertEqual(old.read_bytes(),original)

if __name__=='__main__':unittest.main()

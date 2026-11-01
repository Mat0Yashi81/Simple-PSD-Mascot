import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from psd_mascot import app as module
from _fixture_helpers import fixture

class OutfitMenuTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=QApplication.instance() or QApplication([])
  cls.app.setApplicationName('PSD Mascot');cls.app.setOrganizationName('PSD Mascot')
 def setUp(self):
  scratch=Path.cwd()/'.test-work';scratch.mkdir(exist_ok=True)
  self.tmp=TemporaryDirectory(dir=scratch);self.root=Path(self.tmp.name)
  self.runtime=patch.object(module,'runtime_directory',return_value=self.root);self.runtime.start()
  self.settings=patch.object(module.MascotApp,'_app_settings_path',lambda _:self.root/'app-settings.json');self.settings.start()
  self.path=self.root/'character.json';self.windows=[]
  psd,_=fixture('normal_alpha');self.source=self.root/'fixture.psd';psd.save(self.source)
  self.w=self.window()
  self.normal={'roles':{'brow':None,'eye_open':'1','eye_closed':'2','mouth_closed':'3','mouth_open':'4','accessory':None},'lipsync':False}
  self.w._restore_motion(self.normal);self.w._render();self.drain()
  self.w.preset_name.setText('制服');self.w.save_preset()
  self.w.base_visibility['0']=False;self.w.preset_name.setText('私服');self.w.save_preset()
 def tearDown(self):
  for w in self.windows:
   w.bulk_active=False;w.cache_manager_active=False;w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
  self.runtime.stop();self.settings.stop();self.tmp.cleanup()
 def window(self):
  w=module.MascotApp();self.windows.append(w);w.timer.stop();w.idle_timer.stop()
  w._data_path=lambda:self.path if w.psd_path else None
  w.load_psd(self.source);self.drain(w);return w
 def drain(self,w=None):
  w=w or self.w;end=time.monotonic()+5
  while w.job is not None or w.pending_render is not None or w.warm_queue:
   self.app.processEvents();time.sleep(.003);self.assertLess(time.monotonic(),end)
 def select(self,name,w=None):
  w=w or self.w;w.preset_list.setCurrentItem(w.preset_list.findItems(name,Qt.MatchFlag.MatchExactly)[0])
 def flag(self,name,enabled=True):self.select(name);self.w.outfit_menu_check.setChecked(enabled)
 def names(self,w=None):return [a.data() for a in (w or self.w).mascot_window.outfit_menu.actions()]
 def test_filter_selection_save_and_right_click_application(self):
  w=self.w
  self.assertEqual([a.text() for a in w.mascot_window.actions()],['ボイス','着替え','閉じる'])
  self.assertFalse(w.outfit_menu_check.isChecked());self.assertFalse(w.mascot_window.outfit_menu.isEnabled())
  self.flag('制服');self.assertEqual(self.names(),['制服'])
  self.select('私服');self.assertFalse(w.outfit_menu_check.isChecked());self.assertEqual(w.outfit_menu_names,{'制服'})
  snapshot=w._motion_snapshot();w.mascot_window.outfit_menu.actions()[0].trigger();self.drain()
  self.assertTrue(w.base_visibility['0']);self.assertEqual(w._motion_snapshot(),snapshot)
  self.assertEqual(w.preset_list.currentItem().text(),'制服');self.assertTrue(w.outfit_menu_check.isChecked())
  state=tuple(sorted(w._effective_visibility().items()))
  for key,value in state:w.layers[key].visible=value
  ref=w.psd.composite(force=True).convert('RGBA');self.assertEqual(ref.tobytes(),w.frame_cache[state].tobytes())
  saved=json.loads(self.path.read_text(encoding='utf-8'))
  self.assertEqual(saved['outfit_menu'],['制服']);self.assertEqual(saved['schema_version'],7)
  self.flag('制服',False);self.assertFalse(w.mascot_window.outfit_menu.isEnabled())
  w.preset_list.setCurrentItem(None);self.assertFalse(w.outfit_menu_check.isEnabled())
 def test_reorder_overwrite_delete_and_no_reenabled_new_item(self):
  w=self.w;self.flag('制服');self.flag('私服');w._move_outfit(-1)
  self.assertEqual(self.names(),['私服','制服']);self.assertTrue(w.outfit_menu_check.isChecked())
  # Existing flag persists when overwriting; callbacks fetch the latest state.
  w.base_visibility['0']=True;w.preset_name.setText('私服');w.save_preset()
  self.assertTrue(w.outfit_menu_check.isChecked());w.base_visibility['0']=False
  w.mascot_window.outfit_menu.actions()[0].trigger();self.drain();self.assertTrue(w.base_visibility['0'])
  self.select('私服');w.delete_selected_preset();self.assertEqual(self.names(),['制服'])
  w.preset_name.setText('私服');w.save_preset();self.assertFalse(w.outfit_menu_check.isChecked())
  self.assertEqual(self.names(),['制服'])
 def test_reopen_legacy_and_blocked_operations(self):
  w=self.w;self.flag('制服');self.flag('私服');w._save_data();w.close()
  other=self.window();self.assertEqual(self.names(other),['制服','私服'])
  self.select('私服',other);self.assertTrue(other.outfit_menu_check.isChecked())
  before=dict(other.base_visibility);other.bulk_active=True
  other.mascot_window.outfit_menu.actions()[0].trigger();self.assertEqual(other.base_visibility,before);other.bulk_active=False
  other.close();saved=json.loads(self.path.read_text(encoding='utf-8'));saved.pop('outfit_menu');saved['schema_version']=6
  self.path.write_text(json.dumps(saved),encoding='utf-8');legacy=self.window()
  self.assertEqual(self.names(legacy),[]);self.assertEqual(set(legacy.presets),{'制服','私服'})
 def test_menu_outfit_interrupts_idle_and_preserves_voice_menu(self):
  w=self.w;self.flag('私服')
  w.mascot_window.set_voice_presets([{'id':'v','name':'ボイス','voice':True}])
  w.save_expression('通常')
  different={'roles':dict(self.normal['roles'],eye_open='2',eye_closed='1'),'lipsync':False}
  w._restore_motion(different);w.save_expression('笑顔');w.apply_expression('通常');self.drain()
  w._add_idle();identifier=w.idle_settings['actions'][0]['id'];w._edit_idle(identifier,{'expression':'笑顔','duration':10})
  w._trigger_idle_action(identifier);self.drain();self.assertEqual(w._idle_active_id,identifier)
  w.mascot_window.outfit_menu.actions()[0].trigger();self.drain()
  self.assertIsNone(w._idle_active_id);self.assertEqual(w._motion_snapshot(),self.normal);self.assertFalse(w.base_visibility['0'])
  self.assertEqual([a.data() for a in w.mascot_window.voice_menu.actions()],['v'])

if __name__=='__main__':unittest.main()

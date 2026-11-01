"""Idle scheduling, GUI/persistence, interaction priority and real audio tests."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,random,time,wave,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QLineEdit
from PySide6.QtCore import QCoreApplication,QEvent,Qt
from PySide6.QtGui import QKeyEvent
from psd_mascot.idle import IdleScheduler,sanitize_idle,IdlePanel
from psd_mascot import app as module
from _fixture_helpers import fixture

class IdleTests(unittest.TestCase):
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
  psd,_=fixture('normal_alpha');self.source=self.root/'mascot.psd';psd.save(self.source)
  self.normal={'roles':{'brow':None,'eye_open':'1','eye_closed':'2','mouth_closed':'3','mouth_open':'4','accessory':None},'lipsync':False}
  self.smile={'roles':{'brow':None,'eye_open':'2','eye_closed':'1','mouth_closed':'4','mouth_open':'3','accessory':None},'lipsync':False}
  self.w=self.window()
  self.w._restore_motion(self.normal);self.w.save_expression('通常')
  self.w._restore_motion(self.smile);self.w.save_expression('笑顔')
  self.w.apply_expression('通常');self.drain()
 def tearDown(self):
  for w in self.windows:
   w.bulk_active=False;w.cache_manager_active=False;w.close();w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
  self.runtime.stop();self.settings.stop();self.tmp.cleanup()
 def window(self):
  w=module.MascotApp();self.windows.append(w);w.timer.stop();w.idle_timer.stop()
  w.voice_controller.audio.setVolume(0);w._data_path=lambda:self.path if w.psd_path else None
  w.load_psd(self.source);self.drain(w);return w
 def pump(self,seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:self.app.processEvents();time.sleep(.003)
 def wait(self,condition,timeout=5):
  end=time.monotonic()+timeout
  while not condition():
   self.app.processEvents();time.sleep(.003);self.assertLess(time.monotonic(),end,'timed out')
 def drain(self,w=None):
  w=w or self.w;self.wait(lambda:w.job is None and w.pending_render is None and not w.warm_queue)
 def action(self,**updates):
  self.w._add_idle();item=self.w.idle_settings['actions'][-1]
  self.w._edit_idle(item['id'],dict(expression='笑顔',duration=.2,**updates))
  return item['id']
 def voice(self):
  file=self.root/'sample.wav'
  with wave.open(str(file),'wb') as f:
   f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0\0'*6400)
  filename,_=self.w.voice_controller.library.import_file(file)
  self.w.voice_controller._commit([{'id':'v','name':'ボイス','file':filename,'voice':False}])
 def key(self,widget):
  self.app.sendEvent(widget,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_A,Qt.KeyboardModifier.NoModifier,'a'))
 def test_scheduler_range_pause_and_sanitization(self):
  now=[10.];clock=lambda:now[0];scheduler=IdleScheduler(clock,random.Random(40))
  for _ in range(100):
   scheduler.arm(2,5);self.assertGreaterEqual(scheduler.deadline,12);self.assertLessEqual(scheduler.deadline,15)
  scheduler.arm(1,1);now[0]=12
  self.assertFalse(scheduler.poll(1,1,ready=False));self.assertEqual(scheduler.deadline,11)
  self.assertTrue(scheduler.poll(1,1));self.assertIsNone(scheduler.deadline)
  scheduler.poll(1,1,paused=True);now[0]=100;self.assertFalse(scheduler.poll(1,1));self.assertEqual(scheduler.deadline,101)
  clean=sanitize_idle({'min_seconds':9,'max_seconds':2,'actions':[None,{'id':'x','duration':float('nan')},{'id':'x','duration':99999}]})
  self.assertEqual((clean['min_seconds'],clean['max_seconds']),(2,9));self.assertEqual(len(clean['actions']),2)
  self.assertNotEqual(clean['actions'][0]['id'],clean['actions'][1]['id']);self.assertEqual(clean['actions'][1]['duration'],600)
 def test_tab_ui_global_range_crud_and_persistence(self):
  w=self.w;p=w.idle_panel
  self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())],['レイヤー','服装','表情','動き','リアクション','放置','セリフ','設定'])
  first=self.action();second=self.action();self.voice()
  p.min_seconds.setValue(10);p.max_seconds.setValue(5)
  self.assertEqual((w.idle_settings['min_seconds'],w.idle_settings['max_seconds']),(5,5))
  p.min_seconds.setValue(1);p.max_seconds.setValue(2)
  p.name_edit.setText('待機ボイス');p.name_edit.editingFinished.emit()
  p.voice_combo.setCurrentIndex(p.voice_combo.findData('v'));p.duration.setValue(.4)
  w._move_idle(second,-1);self.assertEqual(w.idle_settings['actions'][0]['id'],second)
  self.assertEqual(p.selected_id(),second);self.assertNotIn('rect',w.idle_settings['actions'][0])
  w._add_reaction();w.tabs.setCurrentWidget(w.reaction_panel);self.assertTrue(any(b.isVisible() for b in w.preview.boxes.values()))
  w.tabs.setCurrentWidget(p);self.assertTrue(all(not b.isVisible() for b in w.preview.boxes.values()))
  w._save_data();saved=json.loads(self.path.read_text(encoding='utf-8'))
  self.assertEqual(saved['schema_version'],7);self.assertEqual(saved['idle'],w.idle_settings)
  w.close();other=self.window()
  self.assertEqual(other.idle_settings,saved['idle']);self.assertEqual(other.idle_panel.action_list.count(),2)
  other._delete_idle(first);self.assertEqual(len(other.idle_settings['actions']),1)
 def test_application_activity_global_wait_and_pause(self):
  w=self.w;identifier=self.action();now=[0.]
  w.idle_scheduler=IdleScheduler(lambda:now[0],random.Random(40))
  w._edit_idle_options({'min_seconds':1,'max_seconds':1});w.mascot_window.show()
  w._advance_idle();self.assertEqual(w.idle_scheduler.deadline,1)
  now[0]=.9;self.key(w.idle_panel.name_edit);self.assertAlmostEqual(w.idle_scheduler.deadline,1.9)
  stranger=QLineEdit();self.key(stranger);self.assertAlmostEqual(w.idle_scheduler.deadline,1.9);stranger.deleteLater()
  now[0]=1.1;w._advance_idle();self.assertIsNone(w._idle_active_id)
  now[0]=2.;w._advance_idle();self.drain();self.assertEqual(w._idle_active_id,identifier)
  self.assertEqual(w._motion_snapshot(),self.smile)
  self.key(w.idle_panel.name_edit);self.drain();self.assertIsNone(w._idle_active_id);self.assertEqual(w._motion_snapshot(),self.normal)
  w.bulk_active=True;now[0]=20;w._advance_idle();self.assertIsNone(w.idle_scheduler.deadline)
  w.bulk_active=False;w._advance_idle();self.assertEqual(w.idle_scheduler.deadline,21)
  w.mascot_window.hide();now[0]=30;w._advance_idle();self.assertIsNone(w.idle_scheduler.deadline)
  w.mascot_window.show();w._advance_idle();self.assertEqual(w.idle_scheduler.deadline,31)
 def test_audio_deferred_restore_interruption_and_voice_only(self):
  w=self.w;self.voice();identifier=self.action(voice='v')
  w._edit_idle(identifier,{'duration':2})
  original=w._compose_frame
  w._compose_frame=lambda *args,**kwargs:(time.sleep(.08) or original(*args,**kwargs))
  # Interrupt a slow, already-dispatched idle frame before it becomes visible.
  w._trigger_idle_action(identifier);self.wait(lambda:w.job is not None)
  self.key(w.idle_panel.name_edit);self.drain()
  self.assertIsNone(w.voice_controller._playing_id);self.assertIsNone(w._idle_active_id)
  self.assertEqual(w._motion_snapshot(),self.normal)
  w._trigger_idle_action(identifier)
  self.assertEqual(w._reaction_pending_voice,'v');self.assertIsNone(w.voice_controller._playing_id)
  self.drain();w._compose_frame=original
  self.wait(lambda:w._voice_playing);self.assertEqual(w._idle_voice_id,'v')
  w._save_data();self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['motion'],self.normal)
  w._reaction_expires_at=time.monotonic()-1;w._advance_reaction();self.drain()
  self.assertEqual(w._motion_snapshot(),self.normal);self.assertTrue(w._voice_playing)
  w._advance_idle();self.assertIsNone(w.idle_scheduler.deadline)
  self.key(w.idle_panel.name_edit);self.wait(lambda:not w._voice_playing);self.assertIsNone(w._idle_voice_id)
  w._edit_idle(identifier,{'expression':'','duration':2})
  w._trigger_idle_action(identifier);self.wait(lambda:w._voice_playing)
  self.assertIsNotNone(w._idle_hold_until);self.assertIsNone(w._reaction_return_motion)
  w._add_reaction();reaction=w.reactions[-1]
  w._edit_reaction(reaction['id'],{'expression':'笑顔','voice':'','duration':2})
  w._tap_reaction(.5,.5);self.drain()
  self.assertIsNone(w._idle_active_id);self.assertFalse(w._voice_playing);self.assertEqual(w._action_source,'reaction')
  w._advance_idle();self.assertIsNone(w.idle_scheduler.deadline)
  w._cancel_reaction(restore=True);self.drain();self.assertEqual(w._motion_snapshot(),self.normal)
 def test_real_timer_repeat_disable_and_invalid_presets(self):
  w=self.w;identifier=self.action();w._edit_idle(identifier,{'duration':.1})
  w._edit_idle_options({'min_seconds':.1,'max_seconds':.1});w.mascot_window.show()
  calls=[];original=w._begin_temporary_action
  def track(action,source):
   if source=='idle':calls.append(time.monotonic())
   return original(action,source)
  w._begin_temporary_action=track;w.idle_timer.start(20)
  self.wait(lambda:len(calls)>=2,4)
  w._edit_idle_options({'enabled':False});self.assertIsNone(w._idle_active_id)
  before=len(calls);self.pump(.3);self.assertEqual(len(calls),before)
  w.idle_timer.stop();self.drain()
  w._edit_idle(identifier,{'expression':'missing','voice':'missing'})
  w._trigger_idle_action(identifier);self.assertIsNone(w._idle_active_id)
  w._edit_idle(identifier,{'expression':'笑顔','voice':'','enabled':False})
  w._edit_idle_options({'enabled':True});w._advance_idle();self.assertIsNone(w.idle_scheduler.deadline)
  w._trigger_idle_action(identifier);self.drain();self.assertEqual(w._idle_active_id,identifier)
  w._delete_idle(identifier);self.drain();self.assertEqual(w._motion_snapshot(),self.normal)

if __name__=='__main__':unittest.main()

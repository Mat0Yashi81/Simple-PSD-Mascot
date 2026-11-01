import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import hashlib,json,sys,time
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from PySide6.QtCore import Qt,QTimer,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtGui import QFont,QFontDatabase
import psd_mascot.app as module
from psd_mascot.disk_cache import CacheRegistry,DocumentCache
import psd_mascot.disk_cache as disk_module
app=QApplication([]);app.setApplicationName('PSD Mascot');app.setOrganizationName('PSD Mascot')
font_id=QFontDatabase.addApplicationFont('C:/Windows/Fonts/meiryo.ttc')
assert font_id>=0
app.setFont(QFont('Meiryo UI',9))
import tempfile
scratch=Path.cwd()/'.test-work';scratch.mkdir(exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='psd-mascot-v038-test-',dir=scratch))
module.runtime_directory=lambda:root
module.MascotApp._app_settings_path=lambda self:root/'app-settings.json'
fixture=root/'mascot.psd';settings=root/'character.json'
errors=[]
def report_error(*error):errors.append(error);sys.__excepthook__(*error)
sys.excepthook=report_error
psd=PSDImage.new('RGBA',(128,128))
for i,name in enumerate(('clothes A','eye A','closed A','mouth A','open A','eye B','closed B','mouth B','open B','acc A','acc B','brow A','brow B','clothes B')):
    layer=PixelLayer.frompil(Image.new('RGBA',(12,12),((i*17)%256,80,100,255)),psd,name=name,top=i*5,left=i*5)
    layer.visible=i in (0,1,3,11)
psd.save(fixture)
normal={'roles':{'brow':'11','eye_open':'1','eye_closed':'2','mouth_closed':'3','mouth_open':'4','accessory':'9'},'lipsync':False}
smile={'roles':{'brow':'12','eye_open':'5','eye_closed':'6','mouth_closed':'7','mouth_open':'8','accessory':'10'},'lipsync':True}

def pump(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:app.processEvents();time.sleep(.003)

def wait_until(condition,timeout=25):
    end=time.monotonic()+timeout
    while not condition():
        app.processEvents();time.sleep(.003)
        assert time.monotonic()<end,'operation timed out'

def drain(w):
    wait_until(lambda:w.job is None and w.pending_render is None and not w.warm_queue)

def make_window():
    w=module.MascotApp();w.timer.stop();w.move(100,90)
    w._data_path=lambda:settings if w.psd_path else None
    w.voice_controller.audio.setVolume(0)
    return w

confirmations=[]
def answer_next(text):
    def choose():
        box=app.activeModalWidget()
        if not isinstance(box,QMessageBox):
            QTimer.singleShot(5,choose);return
        confirmations.append((box.windowTitle(),box.text(),[b.text() for b in box.buttons()]))
        button=next(b for b in box.buttons() if b.text()==text)
        button.click()
    QTimer.singleShot(0,choose)

def generate(w,button,expect_success=True):
    before=(dict(w.base_visibility),w._motion_snapshot())
    answer_next('はい');button.click()
    assert w.bulk_active and w.bulk_dialog is not None
    dialog=w.bulk_dialog
    assert not dialog.ok_button.isEnabled()
    assert dialog.windowModality()==Qt.WindowModality.WindowModal
    # Esc and attempts to close must not hide an in-progress operation.
    dialog.reject();assert w.bulk_dialog is dialog
    wait_until(lambda:dialog.completed)
    assert dialog.ok_button.isEnabled() and dialog.ok_button.text()=='ＯＫ'
    if expect_success:
        assert dialog.message.text()=='ロードが完了しました',dialog.details.text()
        assert dialog.progress.value()==dialog.progress.maximum()
    else:
        assert '失敗' in dialog.message.text()
    # The window is centered on the main window and waits for explicit OK.
    pump(.01)
    a,b=dialog.frameGeometry().center(),w.frameGeometry().center()
    assert abs(a.x()-b.x())<=3 and abs(a.y()-b.y())<=3,(a,b)
    assert w.bulk_active and dialog.isVisible()
    summary=dialog.summary
    dialog.ok_button.click();assert not w.bulk_active
    drain(w)
    assert (w.base_visibility,w._motion_snapshot())==before
    return summary

w=make_window();assert (root/'cache').is_dir()
w.load_psd(fixture);drain(w)
assert w.document_cache is not None
w._restore_motion(normal);w.save_expression('通常')
w._restore_motion(smile);w.save_expression('笑顔')
w.apply_expression('通常');drain(w)
w.preset_name.setText('服A');w.save_preset()
w.base_visibility['0']=False;w.base_visibility['13']=True
w.preset_name.setText('服B');w.save_preset()
w.base_visibility['0']=True;w.base_visibility['13']=False
w._apply_visibility();drain(w)
buttons=(w.all_cache_button,w.outfit_cache_button,w.expression_panel.cache_button)
assert [b.text() for b in buttons]==['すべての事前キャッシュを生成','服装の事前キャッシュを生成','表情の事前キャッシュを生成']
# Each new button offers Japanese Yes/No and No leaves all frames untouched.
def mtimes(cache):return {p.name:p.stat().st_mtime_ns for p in cache.frames_directory.glob('*.png')}
before=mtimes(w.document_cache)
for button in buttons:
    answer_next('いいえ');button.click()
    assert not w.bulk_active and w.bulk_dialog is None
assert mtimes(w.document_cache)==before
assert all('はい' in x[2] and 'いいえ' in x[2] and '長時間' in x[1] for x in confirmations)
# Exercise all three scopes; delay the renderer to check event-loop progress.
original=w._compose_frame
w._compose_frame=lambda state,*args,**kwargs:(time.sleep(.02) or original(state,*args,**kwargs))
beats=[];heartbeat=QTimer();heartbeat.timeout.connect(lambda:beats.append(1));heartbeat.start(10)
clothes=generate(w,w.outfit_cache_button)
assert clothes['total']==8 and clothes['generated']>0,clothes
assert len(beats)>5
heartbeat.stop();w._compose_frame=original
expressions=generate(w,w.expression_panel.cache_button)
assert expressions['total']==8,expressions
all_states=generate(w,w.all_cache_button)
assert all_states['total']==16 and all_states['generated']>0,all_states
before=mtimes(w.document_cache)
again=generate(w,w.all_cache_button)
assert again=={'total':16,'generated':0,'skipped':16},again
assert mtimes(w.document_cache)==before
# Cache identity survives restart and avoids any PSD composition on a cold load.
identity=(w.document_cache.document_id,w.document_cache.generation_id)
w.close()
w2=make_window()
with patch.object(PSDImage,'composite',side_effect=AssertionError('disk cache was not reused')):
    w2.load_psd(fixture);drain(w2)
    assert w2._pixmap is not None,w2.statusBar().currentMessage()
assert (w2.document_cache.document_id,w2.document_cache.generation_id)==identity
old_cache=w2.document_cache
# Rendering revisions get a separate namespace even for the same PSD bytes.
old_revision=disk_module.RENDER_REVISION;disk_module.RENDER_REVISION+=1
changed_renderer=DocumentCache(root/'cache',fixture,old_cache.source_digest,old_cache.canvas_size)
disk_module.RENDER_REVISION=old_revision
assert changed_renderer.generation_id!=old_cache.generation_id
w2.close()
# A PSD edit gets another generation under the same PSD entry.
edited=PSDImage.open(fixture);edited[0].opacity=170;edited.save(fixture)
w3=make_window();w3.load_psd(fixture);drain(w3)
assert w3.document_cache.document_id==identity[0]
assert w3.document_cache.generation_id!=identity[1]
assert old_cache.frames_directory.is_dir()
other=root/'other.psd';other.write_bytes(fixture.read_bytes())
_,other_cache=w3.cache_registry.load_document(other)
state=tuple(sorted(w3._effective_visibility().items()))
marker=Image.new('RGBA',(128,128),(12,34,56,255));other_cache.write(state,marker)
other_frames=mtimes(other_cache)
# Foreign folders, including traversal paths, cannot be deleted by this manager.
foreign=root/'cache'/('a'*24);foreign.mkdir();(foreign/'keep.txt').write_text('keep')
(foreign/'metadata.json').write_text('{"kind":"foreign"}')
for invalid in ('../outside/'+('b'*24),'a'*24):
    try:w3.cache_registry.delete_documents([invalid])
    except (ValueError,OSError):pass
    else:raise AssertionError('unsafe cache deletion accepted')
assert (foreign/'keep.txt').read_text()=='keep'
listed=w3.cache_registry.list_documents()
assert len(listed)==2 and {r['document_id'] for r in listed}=={identity[0],other_cache.document_id}
source_hash=hashlib.sha256(fixture.read_bytes()).hexdigest()
voice_manifest=root/'voice/presets.json'
voice_before=voice_manifest.read_bytes() if voice_manifest.exists() else None
# Open settings manager, choose only the current PSD, delete and refresh.
w3.settings_panel.cache_delete_button.click()
wait_until(lambda:w3.cache_manager is not None and w3.cache_manager.job is None)
manager=w3.cache_manager
assert manager.entries.count()==2
for i in range(manager.entries.count()):
    item=manager.entries.item(i)
    if item.data(Qt.ItemDataRole.UserRole)==identity[0]:item.setCheckState(Qt.CheckState.Checked)
answer_next('はい');manager.delete_button.click()
wait_until(lambda:manager.job is None and manager.entries.count()==1)
assert not w3.document_cache.directory.exists()
assert not w3.frame_cache and w3.cache_bytes==0
assert other_cache.directory.exists() and mtimes(other_cache)==other_frames
assert hashlib.sha256(fixture.read_bytes()).hexdigest()==source_hash
assert (voice_manifest.read_bytes() if voice_manifest.exists() else None)==voice_before
manager.close_button.click();assert not w3.cache_manager_active
w3._apply_visibility();drain(w3)
assert w3.document_cache.contains_valid(state)
# Failed disk writes surface in the separate dialog and can be retried.
write=w3.document_cache.write
w3.document_cache.write=lambda *_args:(_ for _ in ()).throw(OSError('test disk full'))
generate(w3,w3.all_cache_button,expect_success=False)
w3.document_cache.write=write
success=generate(w3,w3.all_cache_button)
assert success['total']==16
# Corrupt cache images are repaired, including from a still-valid memory frame.
file=w3.document_cache.frame_path(state);file.write_bytes(b'broken PNG')
assert not w3.document_cache.contains_valid(state)
with patch.object(PSDImage,'composite',side_effect=AssertionError('expected memory cache repair')):
    repaired=generate(w3,w3.all_cache_button)
assert repaired=={'total':16,'generated':1,'skipped':15},repaired
assert w3.document_cache.contains_valid(state)
w3.close()
for window in (w,w2,w3):window.deleteLater()
QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
assert not errors,errors
print('PASS: three scopes and Japanese Yes/No; centered modal progress + explicit OK; skip + unchanged PNGs; cold disk reuse; content/renderer invalidation; PSD grouping/deletion/safety; RAM clear; write failure/retry; corrupt repair; UI heartbeat; unchanged presets/PSD/voice')
print('fixtures:',root)

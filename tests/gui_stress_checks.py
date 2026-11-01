# Execute the existing GUI cache suite, then stress a new isolated window.
from pathlib import Path
path=Path(__file__).with_name('gui_cache_checks.py')
exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'))
w4=make_window();w4.load_psd(fixture);drain(w4)
w4.timer.stop()
w4.presets={'A':dict(w4.base_visibility),'B':dict(w4.base_visibility)}
w4.presets['B']['0']=False;w4.presets['B']['13']=True
w4.expression_presets={'normal':normal,'smile':smile};w4._restore_motion(normal);w4._track_motion_layers();w4._render();drain(w4)
w4.cache_registry.delete_documents([w4.document_cache.document_id])
w4.frame_cache.clear();w4.cache_bytes=0
if w4.region_renderer is not None:w4.region_renderer.clear()
original=w4._compose_frame
w4._compose_frame=lambda state,*args,**kwargs:(time.sleep(.015) or original(state,*args,**kwargs))
# Rapid edits while previous requests are still running: latest state must win.
for i in range(24):
    w4.base_visibility.update(w4.presets['A' if i%2 else 'B'])
    w4._restore_motion(normal if i%3 else smile)
    w4.blink_active=bool(i%2);w4.mouth_open=bool(i%3);w4.lipsync_check.setChecked(True)
    w4._render();pump(.006)
w4._restore_motion(smile);w4.base_visibility.update(w4.presets['B']);w4.blink_active=True;w4.mouth_open=True;w4._render();drain(w4)
state=tuple(sorted(w4._effective_visibility().items()))
for key,visible in state:w4.layers[key].visible=visible
expected=w4.psd.composite(force=True).convert('RGBA');expected.thumbnail((1400,1400))
actual=w4.frame_cache[state]
assert actual.size==expected.size and actual.tobytes()==expected.tobytes()
# A bulk job owns an immutable spec even if queued signals alter live controls.
# Modal UI blocks normal clicks; these direct calls simulate pending queued events.
# Remove only this test window's isolated cache and reset worker-owned memory while idle.
w4.cache_registry.delete_documents([w4.document_cache.document_id]);w4.frame_cache.clear();w4.cache_bytes=0
if w4.region_renderer is not None:w4.region_renderer.clear()
changes=[]
def queued_changes():
    changes.append(True)
    w4.base_visibility.update(w4.presets['A']);w4._restore_motion(normal)
    w4._render()
QTimer.singleShot(20,queued_changes)
answer_next('はい');w4.all_cache_button.click()
dialog=w4.bulk_dialog;wait_until(lambda:dialog.completed)
assert dialog.message.text()=='ロードが完了しました',dialog.details.text()
result=dialog.summary;dialog.ok_button.click();drain(w4)
assert changes and result['total']>0
w4._compose_frame=original;drain(w4)
state=tuple(sorted(w4._effective_visibility().items()))
for key,visible in state:w4.layers[key].visible=visible
expected=w4.psd.composite(force=True).convert('RGBA');expected.thumbnail((1400,1400))
assert w4.frame_cache[state].tobytes()==expected.tobytes()
# Observe real QTimer-driven eyes and mouth, rather than only invoking _tick.
w4._compose_frame=original
w4._restore_motion(normal);w4.lipsync_check.setChecked(True)
w4.settings_panel.blink_interval.setValue(.1)
w4.blink_active=False;w4.blink_deadline=time.monotonic()+.1
w4.mouth_open=False;w4.mouth_deadline=time.monotonic()+.05
observed=[]
def observe():observed.append((w4.blink_active,w4.mouth_open))
w4.timer.timeout.connect(observe);w4.timer.start(20);pump(.8);w4.timer.stop();drain(w4)
assert {state[0] for state in observed}=={False,True},observed
assert {state[1] for state in observed}=={False,True},observed
w4.close();w4.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
assert not errors,errors
print('PASS: 24 rapid clothing/role/blink/mouth updates; stale results ignored; modal bulk with queued state changes; final full-reference equality; real blink/mouth timers')

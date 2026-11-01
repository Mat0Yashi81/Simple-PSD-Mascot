"""Opt-in packaged executable diagnostic. Uses only a new, isolated test directory."""
import json,sys,time,traceback
from pathlib import Path

def main(args):
    hold = len(args)==3 and args[2]=='--hold'
    if len(args)!=2 and not hold:
        return 2
    fixture_dir,output=map(lambda x:Path(x).resolve(),args[:2])
    if output.exists():return 2
    output.mkdir(parents=True)
    report={'checks':[],'errors':[],'frozen':bool(getattr(sys,'frozen',False))}
    sys.excepthook=lambda *exc:report['errors'].append(''.join(traceback.format_exception(*exc)))
    window=None
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt,QCoreApplication,QEvent
        from . import app as module
        from .branding import APP_NAME,WINDOW_TITLE,configure_application,set_windows_app_id
        set_windows_app_id()
        app=QApplication([])
        configure_application(app)
        # Do not read/write the user's application data, voice library, or cache.
        module.runtime_directory=lambda:output
        module.MascotApp._app_settings_path=lambda self:output/'settings/app-settings.json'
        module.MascotApp._data_path=lambda self:output/'settings/fixture.json' if self.psd_path else None
        module.MascotApp._read_settings_path=staticmethod(lambda path:path)
        window=module.MascotApp();window.show();window.timer.stop();window.idle_timer.stop()
        assert window.windowTitle()==WINDOW_TITLE
        assert app.applicationName()==APP_NAME and app.applicationDisplayName()==WINDOW_TITLE
        for icon in [app.windowIcon(),window.windowIcon(),window.mascot_window.windowIcon(),window.tray_icon.icon()]:
            assert not icon.pixmap(32,32).isNull()
        report['branding']={'name':APP_NAME,'title':window.windowTitle(),'icons_loaded':True,'tray_visible':window.tray_icon.isVisible(),'tray_geometry':window.tray_icon.geometry().getRect()}
        def wait(predicate,timeout=12):
            deadline=time.monotonic()+timeout
            while not predicate():
                app.processEvents();time.sleep(.005)
                if time.monotonic()>deadline:raise AssertionError('Timed out')
        def drain():wait(lambda:window.job is None and window.pending_render is None and not window.warm_queue)
        window.load_psd(fixture_dir/'fixture.psd');drain()
        assert window.psd is not None
        report['checks'].append('PSD load and preview')
        motion={'roles':{'brow':None,'eye_open':'1','eye_closed':'2','mouth_closed':'3','mouth_open':'4','accessory':None},'lipsync':False}
        window._restore_motion(motion);window._render();drain()
        window.preset_name.setText('Test outfit');window.save_preset();window.outfit_menu_check.setChecked(True)
        window.base_visibility['0']=False;window.mascot_window.outfit_menu.actions()[0].trigger();drain()
        assert window.base_visibility['0']
        window.save_expression('Test expression');window.apply_expression('Test expression');drain()
        window.mascot_window.show();app.processEvents()
        assert window.mascot_window.isVisible()
        report['checks'].append('Desktop window, outfit menu and expression')
        state=tuple(sorted(window._effective_visibility().items()))
        for key,value in state:window.layers[key].visible=value
        ref=window.psd.composite(force=True).convert('RGBA')
        assert ref.tobytes()==window.frame_cache[state].tobytes()
        report['checks'].append('Full compositor RGBA equality')
        vc=window.voice_controller;vc.audio.setVolume(0)
        report['audio']=[]
        for suffix in ['wav','mp3','ogg']:
            vc.import_audio(fixture_dir/('sample.'+suffix));wait(lambda:vc.import_job is None)
            preset=vc.presets[-1];vc.play(preset['id'])
            wait(lambda:vc.is_playing)
            wait(lambda:not vc.is_playing)
            report['audio'].append(suffix)
        report['checks'].append('WAV/MP3/OGG playback state and EOF')
        window._save_data();assert (output/'settings/fixture.json').is_file()
        report['checks'].append('Isolated settings persistence')
        report['ok']=not report['errors']
        if hold:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(600000,window.close)
            app.exec()
    except BaseException:
        report['errors'].append(traceback.format_exc());report['ok']=False
    finally:
        if window is not None:
            try:
                if not window._closing:window.close()
                window.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            except BaseException:report['errors'].append(traceback.format_exc());report['ok']=False
        (output/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report.get('ok') else 1

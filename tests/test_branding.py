"""Branding assets, window/tray identity and legacy settings compatibility."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QStandardPaths,QCoreApplication,QEvent
from psd_mascot import branding,app as module

class BrandingTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_multi_resolution_icon(self):
  with Image.open(branding.icon_path()) as icon:
   self.assertEqual(icon.ico.sizes(),{(n,n) for n in [16,32,48,64,128,256]})
  for n in [16,32,48,64,128,256]:self.assertFalse(branding.app_icon().pixmap(n,n).isNull())
 def test_names_tray_and_legacy_settings_location(self):
  app=self.app;snapshot=(app.applicationName(),app.applicationDisplayName(),app.organizationName(),app.applicationVersion(),app.property(branding.SETTINGS_ROOT_PROPERTY),app.windowIcon())
  app.setApplicationName('PSD Mascot');app.setOrganizationName('PSD Mascot')
  legacy=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
  scratch=Path.cwd()/'.test-work';scratch.mkdir(exist_ok=True)
  try:
   branding.configure_application(app)
   self.assertEqual(app.applicationName(),'Simple PSD Mascot');self.assertEqual(str(branding.settings_directory()),str(Path(legacy)))
   with TemporaryDirectory(dir=scratch) as tmp:
    root=Path(tmp)
    with patch.object(module,'runtime_directory',return_value=root),patch.object(module.MascotApp,'_app_settings_path',lambda _:root/'settings/app-settings.json'),patch.object(module.MascotApp,'_data_path',lambda _:None):
     window=module.MascotApp()
     try:
      self.assertEqual(window.windowTitle(),'Simple PSD Mascot v1.0.0')
      self.assertEqual(window.tray_icon.toolTip(),'Simple PSD Mascot')
      self.assertEqual([a.text() for a in window.tray_menu.actions()],['開く','終了'])
      for icon in [window.windowIcon(),window.tray_icon.icon(),window.mascot_window.windowIcon()]:self.assertFalse(icon.pixmap(32,32).isNull())
     finally:
      window.close();self.assertFalse(window.tray_icon.isVisible());window.deleteLater()
      QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
  finally:
   app.setApplicationName(snapshot[0]);app.setApplicationDisplayName(snapshot[1]);app.setOrganizationName(snapshot[2]);app.setApplicationVersion(snapshot[3]);app.setProperty(branding.SETTINGS_ROOT_PROPERTY,snapshot[4]);app.setWindowIcon(snapshot[5])

if __name__=='__main__':unittest.main()

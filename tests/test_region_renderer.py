import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,hashlib,importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from psd_mascot.region_renderer import RegionRenderer
from psd_mascot import performance_log as perf
from psd_mascot.app import MascotApp
from psd_mascot.disk_cache import CacheRegistry,DocumentCache
from psd_mascot.cache_plan import generate_plan
from _fixture_helpers import fixture,walk_layers,apply_state

def exact(a,b):
 assert a.mode==b.mode and a.size==b.size and a.tobytes()==b.tobytes(),'RGBA mismatch'

def reference(psd,layers,state):
 apply_state(layers,state);return psd.composite(force=True).convert('RGBA')

import unittest

class RendererTests(unittest.TestCase):
    def tearDown(self):
        perf.set_enabled(False)
    def test_rgba_fallback_state_and_cache_compatibility(self):
        scratch=Path.cwd()/".test-work"
        scratch.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=scratch) as temporary:
         base=Path(temporary);perf.configure(base/'logs');perf.set_enabled(True)
         # Reproduce all independent-study structures with the production renderer.
         for kind in ('normal_alpha','opacity','mask','clipping','multiply','effect','group'):
          psd,states=fixture(kind);layers=walk_layers(psd);engine=RegionRenderer(psd,layers)
          for state in states+list(reversed(states)):
           expected=reference(psd,layers,state);actual,info=engine.render(state,{'1','2','3','4'});exact(expected,actual)
           a,b=expected.copy(),actual.copy();a.thumbnail((48,48),Image.Resampling.LANCZOS);b.thumbnail((48,48),Image.Resampling.LANCZOS);exact(a,b)
           assert tuple(sorted((k,l.visible) for k,l in layers.items()))==state
           if kind in ('mask','clipping','multiply','effect','group'):assert info['renderer']=='fallback_unsupported'
          engine.clear()
         # Random semitransparent pixels, offsets (including outside canvas), opacity,
         # static clothes changes, control-schema changes, same-state reuse and eviction.
         rng=np.random.default_rng(380)
         for case in range(32):
          psd,states=fixture('opacity' if case%2 else 'normal_alpha')
          l=PixelLayer.frompil(Image.fromarray(rng.integers(0,256,(14,19,4),dtype=np.uint8)),psd,name='extra cloth',left=-5 if case%3==0 else 15,top=30)
          layers=walk_layers(psd);key=next(reversed(layers))
          states=[tuple(sorted(dict(s,**{key:value}).items())) for value in (False,True) for s in states]
          engine=RegionRenderer(psd,layers,seed_budget=64*64*4*2)
          for index in rng.permutation(len(states)).tolist()+[0,7,2,5]:
           state=states[index];expected=reference(psd,layers,state)
           controlled={'1','2','3','4'} if index%3 else {'1','2','3','4',key}
           actual,_=engine.render(state,controlled);exact(expected,actual)
           assert engine.seed_bytes<=engine.seed_budget
          # Caller operations must not mutate retained full-resolution seeds.
          actual.thumbnail((16,16));actual,_=engine.render(states[5],{'1','2','3','4'});exact(reference(psd,layers,states[5]),actual)
          engine.clear();assert not engine.seeds and engine.seed_bytes==0
         # Exception after temporary visibility damage must restore requested state,
         # discard seeds, retry full, and permanently disable fast path for this PSD.
         psd,states=fixture('normal_alpha');layers=walk_layers(psd);engine=RegionRenderer(psd,layers)
         engine.render(states[0],{'1','2','3','4'});target=states[3]
         expected=reference(psd,layers,target);original=psd.composite;calls=[]
         def broken(*args,**kwargs):
          calls.append(kwargs.get('viewport'))
          if kwargs.get('viewport') is not None:
           for layer in layers.values():layer.visible=False
           raise RuntimeError('injected region failure')
          assert tuple(sorted((k,l.visible) for k,l in layers.items()))==target
          return original(*args,**kwargs)
         with perf.session('failure_test') as session:
          with patch.object(psd,'composite',side_effect=broken):actual,info=engine.render(target,{'1','2','3','4'})
          exact(expected,actual);assert info['renderer']=='fallback_exception' and len(calls)==2
          assert engine.disabled_reason and not engine.seeds
          next_state=states[1];expected=reference(psd,layers,next_state)
          actual,info=engine.render(next_state,{'1','2','3','4'});exact(expected,actual);assert info['renderer']=='fallback_disabled'
         assert session['counters']['renderer_fallback']==2
         assert session['stages']['region_composite']['failed_count']==1
         # Failing unsupported full compositor is not retried as a fast-path exception.
         psd,states=fixture('mask');layers=walk_layers(psd);engine=RegionRenderer(psd,layers)
         with patch.object(psd,'composite',side_effect=ValueError('full failure')) as mocked:
          try:engine.render(states[2],{'1','2','3','4'})
          except ValueError:pass
          else:raise AssertionError('full error swallowed')
          assert mocked.call_count==1
         assert tuple(sorted((k,l.visible) for k,l in layers.items()))==states[2]
         # Reuse caches written by the unchanged v0.3.6 DocumentCache implementation.
         psd,states=fixture('normal_alpha');source=base/'fixture.psd';psd.save(source)
         psd,new_cache=CacheRegistry(base/'cache').load_document(source);layers=walk_layers(psd)
         spec=importlib.util.spec_from_file_location('psd_mascot._legacy_disk',Path(__file__).with_name('_legacy_disk_cache.py'))
         legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
         old_cache=legacy.DocumentCache(new_cache.root,source,new_cache.source_digest,psd.size)
         assert (old_cache.document_id,old_cache.generation_id)==(new_cache.document_id,new_cache.generation_id)
         expected=[]
         for state in states:
          image=reference(psd,layers,state);old_cache.write(state,image);expected.append(image)
         before={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in new_cache.frames_directory.glob('*.png')}
         w=SimpleNamespace(psd=psd,psd_path=source,document_cache=new_cache,layers=layers,frame_cache=OrderedDict(),cache_bytes=0,region_renderer=None,expression_layers={'1','2','3','4'})
         for name in ('_compose_frame','_compose_frame_measured','_remember_frame','_persist_frame'):setattr(w,name,getattr(MascotApp,name).__get__(w))
         with patch.object(PSDImage,'composite',side_effect=AssertionError('must reuse existing PNG')):
          for state,image in zip(states,expected):exact(w._compose_frame(state)[0],image)
         assert w.region_renderer is None
         after={p.name:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in new_cache.frames_directory.glob('*.png')}
         assert before==after
         # Library mismatches must fall back rather than broadening the compatibility gate.
         with patch('psd_mascot.region_renderer.psd_tools.__version__','untested'):
          engine=RegionRenderer(psd,layers);assert engine.reasons
          actual,info=engine.render(states[0],{'1','2','3','4'});exact(actual,expected[0]);assert info['renderer']=='fallback_unsupported'

if __name__=='__main__':unittest.main()

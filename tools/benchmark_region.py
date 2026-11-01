import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import sys,json,time,hashlib
from pathlib import Path
from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from psd_mascot import app as module,performance_log as perf
from psd_mascot.region_renderer import RegionRenderer
from psd_mascot.disk_cache import CacheRegistry,state_digest
from psd_mascot.cache_plan import generate_plan,iter_plan_states

from PIL import Image
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()

def build_spec(payload,psd):
 layers={}
 def walk(group,prefix=()):
  for i,l in enumerate(group):
   parts=prefix+(i,);layers['/'.join(map(str,parts))]=l
   if l.is_group():walk(l,parts)
 walk(psd)
 base={k:l.visible for k,l in layers.items()}
 base.update({k:bool(v) for k,v in payload.get('visibility',{}).items() if k in layers})
 outfits=[base]
 for saved in payload.get('presets',{}).values():
  state=dict(base);state.update({k:bool(v) for k,v in saved.items() if k in layers});outfits.append(state)
 motions=[payload.get('motion',{'roles':payload.get('roles',{})})]+list(payload.get('expression_presets',{}).values())
 controlled=set(payload.get('expression_layers',[]))
 for m in motions:controlled.update(k for k in m.get('roles',{}).values() if k)
 spec={'outfits':outfits,'motions':motions,'controlled':controlled}
 seen=set();states=[]
 for state in iter_plan_states(spec):
  key=state_digest(state)
  if key not in seen:seen.add(key);states.append(state)
 return spec,layers,states

import argparse
parser=argparse.ArgumentParser(description="v0.4.1 backend benchmark: separate empty caches, native/final RGBA verification")
parser.add_argument('--psd',type=Path,required=True)
parser.add_argument('--settings',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True,help='new directory only')
args=parser.parse_args()
perf.set_enabled(True)  # This explicit diagnostic tool always requests logs.
root=args.output;root.mkdir(parents=True,exist_ok=False)
source=args.psd;settings=args.settings
payload=json.loads(settings.read_text(encoding='utf-8'))
protected={str(p):{'sha256':digest(p),'mtime_ns':p.stat().st_mtime_ns} for p in (source,settings)}
(root/'protected-before.json').write_text(json.dumps(protected),encoding='utf-8')
reports={}
for name,enabled in (('legacy',False),('auto',True)):
    mode=root/name;mode.mkdir();perf.configure(mode/'logs')
    t=time.perf_counter();psd,cache=CacheRegistry(mode/'cache').load_document(source);load=time.perf_counter()-t
    spec,layers,states=build_spec(payload,psd)
    native=[];verification_seconds=[0.]
    class TracingRenderer(RegionRenderer):
        def __init__(self,doc,layer_map):super().__init__(doc,layer_map,enabled=enabled)
        def render(self,state,controlled):
            image,info=super().render(state,controlled)
            t=time.perf_counter();native.append({'state_digest':state_digest(state),'sha256':hashlib.sha256(image.tobytes()).hexdigest(),'size':image.size})
            verification_seconds[0]+=time.perf_counter()-t
            return image,info
    w=SimpleNamespace(psd=psd,psd_path=source,document_cache=cache,layers=layers,frame_cache=OrderedDict(),cache_bytes=0,region_renderer=None,expression_layers=set(spec['controlled']))
    for method in ('_compose_frame','_compose_frame_measured','_remember_frame','_persist_frame'):setattr(w,method,getattr(module.MascotApp,method).__get__(w))
    def report_progress(data):
        if data['phase']=='generate':print(name,data['done'],'/',data['total'],flush=True)
    with patch.object(module,'RegionRenderer',TracingRenderer):
        result=generate_plan(spec,cache,lambda state:w._compose_frame(state,True,controlled=spec['controlled']),report_progress)
    log=json.loads(next((mode/'logs').glob('*.json')).read_text(encoding='utf-8'))
    final=[]
    for state in states:
        with Image.open(cache.frame_path(state)) as image:final.append({'state_digest':state_digest(state),'rgba_sha256':hashlib.sha256(image.tobytes()).hexdigest(),'png_sha256':digest(cache.frame_path(state))})
    reports[name]={'result':result,'load_seconds':load,'native':native,'final':final,
                   'verification_seconds':verification_seconds[0],
                   'total_seconds_including_verification':log['stages']['total']['total_seconds'],
                   'pipeline_seconds_excluding_test_hashing':log['stages']['total']['total_seconds']-verification_seconds[0],
                   'log':log}
    (root/(name+'.json')).write_text(json.dumps(reports[name],ensure_ascii=False,indent=2),encoding='utf-8')
    w.region_renderer.clear()
assert reports['legacy']['native']==reports['auto']['native'],'native RGBA mismatch'
assert reports['legacy']['final']==reports['auto']['final'],'final RGBA or PNG bytes mismatch'
# Both cold modes must generate all states. No inherited user cache was used.
assert reports['legacy']['result']==reports['auto']['result']
# A repeat of the production bulk generator must skip all generated PNGs.
before={p.name:(digest(p),p.stat().st_mtime_ns) for p in cache.frames_directory.glob('*.png')}
perf.configure(root/'reuse-logs')
with patch.object(psd,'composite',side_effect=AssertionError('must reuse PNG')):
    reuse=generate_plan(spec,cache,lambda state:w._compose_frame(state,True,controlled=spec['controlled']),lambda _:None)
assert reuse['generated']==0 and reuse['skipped']==len(states)
after={p.name:(digest(p),p.stat().st_mtime_ns) for p in cache.frames_directory.glob('*.png')};assert before==after
for name,info in protected.items():
    p=Path(name);assert digest(p)==info['sha256'] and p.stat().st_mtime_ns==info['mtime_ns'],name
summary={'state_count':len(states),'canvas_size':psd.size,'legacy_seconds':reports['legacy']['pipeline_seconds_excluding_test_hashing'],
         'auto_seconds':reports['auto']['pipeline_seconds_excluding_test_hashing'],'native_rgba_exact':True,'final_rgba_exact':True,'final_png_bytes_exact':True,
         'auto_counters':reports['auto']['log']['counters'],'reuse_result':reuse,'protected_files_unchanged':len(protected)}
summary['speedup']=summary['legacy_seconds']/summary['auto_seconds']
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: production pipeline comparison, native/final RGBA + PNG bytes exact, warm reuse skips all, protected input/source/cache/settings unchanged',flush=True)
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

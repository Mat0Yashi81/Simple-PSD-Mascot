"""Small constructed compatibility PSDs; separate from the real character benchmark."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer,Group
from psd_tools.constants import BlendMode,Tag
from psd_tools.psd.descriptor import Descriptor,DescriptorBlock2,Bool as Boolean,UnitFloat,Enumerated,Double
from psd_tools.psd.tagged_blocks import TaggedBlock
from psd_tools.terminology import Key,Klass,Unit,Enum
from psd_mascot.region_renderer import walk_layers
from psd_mascot.cache_plan import effective_visibility


def apply_state(layers,state):
    for key,visible in state:layers[key].visible=visible

def fixture(kind):
    psd=PSDImage.new('RGBA',(64,64))
    rng=np.random.default_rng(371)
    pixels=rng.integers(0,256,(64,64,4),dtype=np.uint8)
    base=PixelLayer.frompil(Image.fromarray(pixels),psd,name='body')
    for i,(color,top,left) in enumerate((((180,20,30,128),20,20),((20,180,30,200),20,20),((20,30,180,255),35,25),((180,30,180,90),35,25))):
        PixelLayer.frompil(Image.new('RGBA',(12,8),color),psd,name=f'part {i}',top=top,left=left)
    hair=PixelLayer.frompil(Image.new('RGBA',(20,4),(30,20,10,170)),psd,name='overlying hair',top=22,left=17)
    if kind=='opacity':base.opacity=137;hair.opacity=201
    if kind=='mask':
        mask=Image.new('L',(12,8),0);mask.paste(255,(0,0,6,8));psd[1].create_mask(mask)
    if kind=='clipping':psd[2].clipping=True
    if kind=='multiply':psd[1].blend_mode=BlendMode.MULTIPLY
    if kind=='group':
        group=Group.new(psd,name='group');PixelLayer.frompil(Image.new('RGBA',(8,8),(0,255,0,255)),group,name='child')
    if kind=='effect':
        effect=Descriptor(classID=Klass.SolidFill)
        effect[b'present']=Boolean(True);effect[Key.Enabled]=Boolean(True)
        effect[Key.Mode]=Enumerated(b'BlnM',b'norm')
        effect[Key.Opacity]=UnitFloat(100.,Unit.Percent)
        color=Descriptor(classID=Klass.RGBColor)
        color[Key.Red]=Double(0.);color[Key.Green]=Double(255.);color[Key.Blue]=Double(255.)
        effect[Key.Color]=color
        block=DescriptorBlock2();block[b'masterFXSwitch']=Boolean(True);block[Key.Scale]=UnitFloat(100.,Unit.Percent);block[b'SoFi']=effect
        psd[1].tagged_blocks[Tag.OBJECT_BASED_EFFECTS_LAYER_INFO]=TaggedBlock(key=Tag.OBJECT_BASED_EFFECTS_LAYER_INFO,data=block)
        psd.mark_updated()
    layers=walk_layers(psd);base_vis={k:True for k in layers}
    roles={'eye_open':'1','eye_closed':'2','mouth_closed':'3','mouth_open':'4'}
    states=[tuple(sorted(effective_visibility(base_vis,roles,{'1','2','3','4'},blink,mouth,True).items())) for blink in (False,True) for mouth in (False,True)]
    return psd,states

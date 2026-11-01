"""Conservative region renderer: flat normal RGB8 PSDs tested in v0.3.7 only.

All access is confined to the application's single rendering worker. Seeds are
unscaled RGBA images, never persisted; final PNGs still use the original pipeline.
"""
from collections import OrderedDict
import PIL
import numpy
import psd_tools
from psd_tools.constants import BlendMode, ColorMode, Tag, Resource
from . import performance_log as perf

def walk_layers(psd):
    result={}
    def walk(parent,prefix=()):
        for i,layer in enumerate(parent):
            parts=prefix+(i,);key='/'.join(map(str,parts));result[key]=layer
            if layer.is_group():walk(layer,parts)
    walk(psd)
    return result

def unsupported_reasons(psd):
    """Conservative gate: no promise for untested PSD features, even hidden ones."""
    reasons=[]
    if psd.color_mode != ColorMode.RGB:reasons.append('document: non-RGB')
    if psd.depth != 8:reasons.append('document: non-8-bit')
    if Resource.ICC_PROFILE in psd.image_resources:reasons.append('document: ICC profile not validated')
    for key,layer in walk_layers(psd).items():
        tests={
            'not a flat pixel layer':layer.kind!='pixel' or layer.is_group(),
            'non-normal blend':layer.blend_mode!=BlendMode.NORMAL,
            'mask':layer.has_mask(), 'vector mask':layer.has_vector_mask(),
            'clipping':bool(layer.clipping) or layer.has_clip_layers(),
            'layer effects':layer.has_effects() or any(tag in layer.tagged_blocks for tag in (Tag.OBJECT_BASED_EFFECTS_LAYER_INFO, Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V0, Tag.OBJECT_BASED_EFFECTS_LAYER_INFO_V1)), 'stroke':layer.has_stroke(),
            'fill opacity':layer.fill_opacity!=255,
            'advanced blending':any(tag in layer.tagged_blocks for tag in (Tag.CHANNEL_BLENDING_RESTRICTIONS_SETTING, Tag.KNOCKOUT_SETTING)),
        }
        ranges=layer._record.blending_ranges
        pairs=list(ranges.composite_ranges or [])+[pair for channel in (ranges.channel_ranges or []) for pair in channel]
        tests['blend-if ranges']=any(tuple(pair)!=(0,65535) for pair in pairs)
        for reason,bad in tests.items():
            if bad:reasons.append(f'{key}: {reason}')
    return reasons

def union_boxes(boxes,size):
    boxes=[b for b in boxes if b[0]<b[2] and b[1]<b[3]]
    if not boxes:return None
    box=(max(0,min(b[0] for b in boxes)),max(0,min(b[1] for b in boxes)),
         min(size[0],max(b[2] for b in boxes)),min(size[1],max(b[3] for b in boxes)))
    return box if box[0]<box[2] and box[1]<box[3] else None


class RegionRenderer:
    SEED_BUDGET = 128 * 1024 * 1024
    MAX_SEEDS = 8

    def __init__(self, psd, layers, *, enabled=True, seed_budget=None):
        self.psd = psd
        self.layers = layers
        self.seed_budget = self.SEED_BUDGET if seed_budget is None else max(0, seed_budget)
        self.seeds = OrderedDict()
        self.seed_bytes = 0
        self.disabled_reason = ""
        try:
            self.reasons = unsupported_reasons(psd)
            versions = (psd_tools.__version__, PIL.__version__, numpy.__version__)
            if versions != ("1.26.0", "13.0.0", "2.5.4"):
                self.reasons.append(f"untested library versions: {versions}")
        except Exception as exc:
            self.reasons = [f"eligibility check failed: {type(exc).__name__}: {exc}"]
        if not enabled:
            self.reasons.append("full renderer selected explicitly")
        perf.event("renderer_support", eligible=not self.reasons,
                   reasons=self.reasons[:20], reason_count=len(self.reasons),
                   seed_budget_bytes=self.seed_budget)

    def clear(self):
        """Call only after the rendering worker is idle, or from that worker."""
        for _, image in self.seeds.values():
            image.close()
        self.seeds.clear()
        self.seed_bytes = 0

    def _apply(self, state):
        for key, visible in state:
            self.layers[key].visible = visible

    def _full(self):
        with perf.measure("psd_composite"):
            image = self.psd.composite(force=True)
        if image is None:
            raise ValueError("合成画像を作成できませんでした")
        with perf.measure("rgba_convert"):
            return image.convert("RGBA")

    def _fallback(self, state, reason):
        self._apply(state)
        perf.count("renderer_fallback")
        perf.count(f"renderer_{reason}")
        with perf.measure("fallback_render"):
            return self._full(), {"renderer": reason,
                                  "renderer_reason": self.disabled_reason or "; ".join(self.reasons[:3])}

    def _remember(self, key, state, image):
        cost = image.width * image.height * 4
        if cost > self.seed_budget:
            perf.count("renderer_seed_not_retained")
            return False
        while self.seeds and (self.seed_bytes + cost > self.seed_budget or
                              len(self.seeds) >= self.MAX_SEEDS):
            _, (_, old) = self.seeds.popitem(last=False)
            self.seed_bytes -= old.width * old.height * 4
            old.close()
            perf.count("renderer_seed_evicted")
        self.seeds[key] = (state, image)
        self.seed_bytes += cost
        return True

    def render(self, state, controlled):
        """Render exactly the requested immutable visibility snapshot.

        Identity includes the controlled-key schema AND every non-controlled
        layer's actual visibility. Preset names are intentionally irrelevant.
        A document instance owns its own seeds, so PSD reloads cannot reuse them.
        """
        if len(state) != len(self.layers) or {k for k, _ in state} != set(self.layers):
            raise ValueError("描画状態とPSDのレイヤー構造が一致しません")
        controlled = tuple(sorted(set(controlled) & self.layers.keys()))
        self._apply(state)
        try:
            if self.reasons:
                return self._fallback(state, "fallback_unsupported")
            if self.disabled_reason:
                return self._fallback(state, "fallback_disabled")
            key = (controlled, tuple((k, v) for k, v in state if k not in controlled))
            seed = self.seeds.get(key)
            if seed is None:
                image = self._full()
                perf.count("renderer_seed_full")
                if self._remember(key, state, image):
                    # The caller thumbnails its result in place. Never expose
                    # the full-size seed itself to that operation.
                    return image.copy(), {"renderer": "seed_full"}
                return image, {"renderer": "seed_full_not_retained"}
            self.seeds.move_to_end(key)
            seed_state, seed_image = seed
            previous = dict(seed_state)
            changed = [k for k, v in state if previous[k] != v]
            box = union_boxes([self.layers[k].bbox for k in changed], self.psd.size)
            result = None
            try:
                with perf.measure("fast_render"):
                    result = seed_image.copy()
                    if box is not None:
                        with perf.measure("region_composite"):
                            patch = self.psd.composite(force=True, viewport=box)
                        if patch is None or patch.size != (box[2]-box[0], box[3]-box[1]):
                            raise ValueError("差分合成画像の寸法が一致しません")
                        with perf.measure("rgba_convert"):
                            patch = patch.convert("RGBA")
                        # Replace all RGBA channels; overlaying would leave the
                        # old mouth/eyes visible under transparent pixels.
                        result.paste(patch, box[:2])
                perf.count("renderer_fast")
                perf.count("renderer_fast_region" if box is not None else "renderer_fast_seed_copy")
                return result, {"renderer": "fast_region" if box is not None else "fast_seed_copy",
                                "region_box": box}
            except Exception:
                if result is not None:
                    result.close()
                raise
        except Exception as exc:
            if self.reasons or self.disabled_reason:
                raise
            # A failed patch (or seed preparation) must never reach the RAM or
            # PNG cache. Reapply ALL target flags and retry from scratch.
            self.clear()
            self.disabled_reason = f"{type(exc).__name__}: {exc}"
            perf.event("renderer_fast_disabled", reason=self.disabled_reason)
            image, info = self._fallback(state, "fallback_exception")
            info["renderer_error"] = self.disabled_reason
            return image, info
        finally:
            # Also restore after a library error in the full retry. The worker
            # leaves the document at the requested state, as the legacy path did.
            self._apply(state)

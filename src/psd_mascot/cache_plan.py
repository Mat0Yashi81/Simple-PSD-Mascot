"""服装・表情の組み合わせをGUIの状態を変更せず列挙する。"""

from .disk_cache import state_digest
from . import performance_log as perf


def effective_visibility(base, roles, controlled, blink=False, mouth=False, lipsync=False):
    visible = dict(base)
    for key in controlled:
        if key in visible:
            visible[key] = False
    def assign(role, value):
        key = roles.get(role)
        if key in visible:
            visible[key] = bool(value)
    assign("eye_open", not blink)
    assign("eye_closed", blink)
    assign("brow", True)
    assign("accessory", True)
    speaking = bool(lipsync and mouth and roles.get("mouth_open"))
    assign("mouth_open", speaking)
    assign("mouth_closed", not speaking)
    return visible


def animation_states(base, motion, controlled):
    roles = motion.get("roles", {})
    for blink in (False, True) if roles.get("eye_closed") else (False,):
        for mouth in (False, True) if roles.get("mouth_open") else (False,):
            visible = effective_visibility(base, roles, controlled, blink, mouth, lipsync=True)
            yield tuple(sorted(visible.items()))


def iter_plan_states(spec):
    for outfit in spec["outfits"]:
        for motion in spec["motions"]:
            yield from animation_states(outfit, motion, spec["controlled"])


def plan_estimate(spec):
    variants = sum((2 if m.get("roles", {}).get("eye_closed") else 1) *
                   (2 if m.get("roles", {}).get("mouth_open") else 1) for m in spec["motions"])
    return len(spec["outfits"]) * variants


def generate_plan(spec, cache, compose, report):
    with perf.session("bulk_cache", cache.source, planned_candidates=plan_estimate(spec),
                      canvas_size=list(cache.canvas_size)) as timing:
        result = _generate_plan_measured(spec, cache, compose, report)
        timing["result"] = result
        return result


def _generate_plan_measured(spec, cache, compose, report):
    # Store only hashes, not every full visibility map. Large combinations
    # therefore don't retain thousands of duplicated per-layer dictionaries.
    seen, missing = set(), set()
    raw_total = plan_estimate(spec)
    for index, state in enumerate(iter_plan_states(spec), 1):
        key = state_digest(state)
        if key not in seen:
            seen.add(key)
            if not cache.contains_valid(state):
                missing.add(key)
            else:
                perf.count("bulk_existing_valid_skipped")
        if index == 1 or index % 16 == 0 or index == raw_total:
            report({"phase": "scan", "done": index, "total": raw_total,
                    "cached": len(seen)-len(missing), "missing": len(missing)})
    unique_total, generation_total = len(seen), len(missing)
    created = processed = 0
    report({"phase": "generate", "done": 0, "total": generation_total,
            "cached": unique_total-generation_total})
    for state in iter_plan_states(spec):
        key = state_digest(state)
        if key not in missing:
            continue
        # A second application instance may have generated it in the meantime.
        if not cache.contains_valid(state):
            compose(state)
            created += 1
        else:
            perf.count("bulk_available_after_scan_skipped")
        missing.remove(key)
        processed += 1
        report({"phase": "generate", "done": processed, "total": generation_total,
                "cached": unique_total-generation_total})
    return {"total": unique_total, "generated": created, "skipped": unique_total-created}

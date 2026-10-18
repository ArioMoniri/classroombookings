#!/usr/bin/env python3
"""Quality gate for the launch media: smoothness (judder) and fidelity.

    python3 -I scripts/record/launch/quality.py VIDEO [--ref LOSSLESS.mkv] [--ffmpeg-vmaf PATH] [--json OUT.json]

Smoothness, from ffmpeg's mpdecimate (default thresholds: a frame is "unique" when it differs visibly from the last
unique one) and freezedetect (n=0.001, d=0.05: three or more identical frames):

- unique: unique frames / all frames.
- motion segments: maximal runs of frames in which no two unique frames are more than 2 frames apart (no still
  stretch of 50 ms or more). Judder (a 30 fps source in a 60 fps file) shows as about 50 % unique inside them; a real
  60 fps picture is 100 %. Gate: >= 95 %.
- freezes >= 50 ms (freezedetect), split three ways: slow motion (the frames inside still change, below
  freezedetect's noise floor: an ease-out tail, a slow Lottie part), holds (identical frames on purpose: a read pause,
  a still screen) and judder-like ones (identical frames, shorter than 150 ms, with motion on both sides: at least
  half the frames in the 150 ms before and after change). Gate: no judder-like freeze.

Exact repeats (--exact, for a lossless master): mpdecimate with hi=lo=1, frac=0 (any change at all is a change);
an isolated repeat is a frame identical to the one before while the frames on both sides change. Most of those are
the last step of an ease-out (a crossfade or a sub-pixel settle rounds to the same 8-bit pixels once, then the layer
snaps to rest and stays still). A mid-motion repeat is one inside continuing motion (two changing frames before it
and two after it, "##.##", visible on both sides): the judder signature, which a deterministic capture must not have. Gate: none (with
--plan, repeats inside a Lottie scene are counted apart: the animations have hold keyframes that step on purpose).
mpdecimate's default thresholds also drop frames that do change, a little (the tail of an ease-out, a fading tap
dot); the exact flags separate those from real repeats.

Fidelity (with --ref, the lossless master the file was encoded from, scaled to the same size): PSNR (Y) and, when an
ffmpeg with libvmaf is given (--ffmpeg-vmaf, e.g. a static build; the system ffmpeg may lack it), VMAF v0.6.1 mean
and 1st percentile. Gate: VMAF mean >= 95.

Sync flashes: the recorder paints a full-screen magenta frame (#ff00ff, lib/recorder.mjs SYNC_COLOR) around every
off-camera cut; render.mjs cuts them out. A frame whose picture is 5 % or more that colour (on a 64x36 thumbnail) is
one that leaked into the video (the 2026-10-18 render had two). Gate: none. Licence: same as the repository.
"""
import argparse
import json
import re
import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate",
               "-show_entries", "format=duration,size,bit_rate", "-of", "json", path]).stdout
    j = json.loads(out)
    st, fm = j["streams"][0], j["format"]
    num, den = st["avg_frame_rate"].split("/")
    return {"width": st["width"], "height": st["height"], "fps": float(num) / float(den), "duration": float(fm["duration"]),
            "bytes": int(fm["size"]), "mbit_s": round(int(fm.get("bit_rate", 0)) / 1e6, 2)}


def keep_flags(path, fps, vf="mpdecimate"):
    # mpdecimate at debug level logs "keep" or "drop" per frame
    err = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "debug", "-i", path, "-an", "-vf", vf, "-f", "null", "-"]).stderr
    flags = []
    for line in err.splitlines():
        m = re.search(r"mpdecimate.*\b(keep|drop)\b pts:(\d+)", line)
        if m:
            flags.append(m.group(1) == "keep")
    return flags


def freezes(path):
    err = run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-an", "-vf", "freezedetect=n=0.001:d=0.05", "-f", "null", "-"]).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    durs = [float(x) for x in re.findall(r"freeze_duration: ([\d.]+)", err)]
    return list(zip(starts, durs))


def smoothness(path, fps, exact_src=None, src_fps=None):
    """exact_src: a lossless file with the same frames (the file itself, or the master it was encoded from); a lossy
    file has encoder noise in every frame, so "any change at all" is only meaningful on lossless frames. Without it,
    visible changes (mpdecimate's defaults) stand in."""
    k = keep_flags(path, fps)
    exact_vf = "mpdecimate=hi=1:lo=1:frac=0"
    if exact_src and src_fps and abs(src_fps - fps) > 0.01:  # a 30 fps file from the 60 fps master: decimate the same way
        exact_vf = f"setpts=N/{src_fps}/TB,fps={fps},{exact_vf}"
    x = keep_flags(exact_src, fps, exact_vf) if exact_src else k
    n = len(k)
    uniq = [i for i, x in enumerate(k) if x]
    segs, cur = [], None
    for i in uniq:
        if cur and i - cur[1] <= 2:
            cur[1] = i
        else:
            if cur:
                segs.append(tuple(cur))
            cur = [i, i]
    if cur:
        segs.append(tuple(cur))
    segs = [s for s in segs if s[1] - s[0] >= 5]  # motion that lasts at least ~100 ms
    in_seg = sum(s[1] - s[0] + 1 for s in segs)
    uniq_seg = sum(sum(k[s[0]:s[1] + 1]) for s in segs)
    win = max(1, round(0.15 * fps))
    holds, judder, slow = [], [], []
    for start, dur in freezes(path):
        a = int(round(start * fps))
        b = int(round((start + dur) * fps))
        before = x[max(0, a - win):a]
        after = x[b:b + win]
        moving = lambda w: len(w) > 0 and sum(w) / len(w) >= 0.5
        item = {"at": round(start, 3), "ms": round(dur * 1000)}
        if any(x[a + 1:b]):
            slow.append(item)
        else:
            (judder if dur < 0.15 and moving(before) and moving(after) else holds).append(item)
    return {
        "frames": n, "unique": len(uniq), "unique_pct": round(100 * len(uniq) / max(1, n), 1),
        "motion_segments": len(segs), "motion_frames": in_seg, "motion_unique_pct": round(100 * uniq_seg / max(1, in_seg), 1),
        "freezes": len(holds) + len(judder) + len(slow), "slow_motion": len(slow), "holds": len(holds), "judder_freezes": len(judder),
        "judder_list": judder[:20],
        "exact_from": exact_src,  # None: the "exact" numbers below are visible changes only (a lossy file, no master)
        "exact_unique_pct": round(100 * sum(x) / max(1, len(x)), 1),
        "isolated_repeats": sum(1 for i in range(1, len(x) - 1) if not x[i] and x[i - 1] and x[i + 1]),
        # an exact repeat inside continuing motion that is visible on both sides (mpdecimate's default thresholds)
        "midmotion_list": [round(i / fps, 3) for i in range(2, min(len(x), len(k)) - 2)
                           if not x[i] and x[i - 2] and x[i - 1] and x[i + 1] and x[i + 2] and k[i - 1] and k[i + 1]],
    }


def sync_flashes(path, fps):
    w, h = 64, 36
    raw = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", path, "-an", "-vf", f"scale={w}:{h}:flags=area,format=rgb24",
                          "-f", "rawvideo", "-"], capture_output=True, check=False).stdout
    n, hits = w * h * 3, []
    for i in range(len(raw) // n):
        f = raw[i * n:(i + 1) * n]
        mag = sum(1 for j in range(0, n, 3) if f[j] > 200 and f[j + 1] < 90 and f[j + 2] > 200)
        if mag >= 0.05 * w * h:
            hits.append(round(i / fps, 3))
    return hits


def fidelity(path, ref, vmaf_ffmpeg, info):
    w, h = info["width"], info["height"]
    out = {}
    # pair frames by index, not by timestamp: the masters are Matroska (millisecond timestamps: 16, 33, 50 ms ...) and
    # pairing by rounded time compares every third frame with its neighbour
    fr = info["fps"]
    lav = (f"[0:v]format=yuv420p,setpts=N/{fr}/TB[d];"
           f"[1:v]scale={w}:{h}:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p,setpts=N/{fr}/TB[r]")
    err = run(["ffmpeg", "-nostdin", "-hide_banner", "-i", path, "-i", ref, "-lavfi", f"{lav};[d][r]psnr", "-f", "null", "-"]).stderr
    m = re.search(r"PSNR y:([\d.inf]+) u:([\d.inf]+) v:([\d.inf]+) average:([\d.inf]+)", err)
    if m:
        out["psnr_y"], out["psnr_avg"] = m.group(1), m.group(4)
    if vmaf_ffmpeg:
        logf = "/dev/shm/vmaf.json" if sys.platform.startswith("linux") else "vmaf.json"
        err = run([vmaf_ffmpeg, "-nostdin", "-hide_banner", "-i", path, "-i", ref, "-lavfi",
                   f"{lav};[d][r]libvmaf=log_fmt=json:log_path={logf}:n_threads=2:n_subsample=1", "-f", "null", "-"]).stderr
        try:
            j = json.load(open(logf))
            vals = sorted(f["metrics"]["vmaf"] for f in j["frames"])
            out["vmaf_mean"] = round(sum(vals) / len(vals), 2)
            out["vmaf_p1"] = round(vals[max(0, len(vals) // 100 - 1)], 2)
            out["vmaf_min"] = round(vals[0], 2)
        except Exception as e:  # noqa: BLE001
            out["vmaf_error"] = f"{e}: {err[-300:]}"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--ref")
    ap.add_argument("--ffmpeg-vmaf")
    ap.add_argument("--json")
    ap.add_argument("--exact", action="store_true", help="gate on mid-motion repeats (a lossless master)")
    ap.add_argument("--plan", help="render.mjs plan: repeats inside a Lottie scene (intro, chapter, outro) are the animation's own hold keyframes")
    a = ap.parse_args()
    info = probe(a.video)
    ref = probe(a.ref) if a.ref else None
    same_frames = ref and abs(ref["duration"] - info["duration"]) < 0.1 and round(ref["fps"]) % round(info["fps"]) == 0
    r = {"file": a.video, **info, **smoothness(a.video, info["fps"], a.video if a.exact else a.ref if same_frames else None, ref["fps"] if ref else None)}
    r["sync_flash_frames"] = sync_flashes(a.video, info["fps"])[:20]
    if a.plan:
        lottie = [(sc["start"] / 1000, sc["end"] / 1000) for sc in json.load(open(a.plan))["scenes"] if sc["kind"] in ("intro", "chapter", "outro")]
        takes = [(sc["start"] / 1000, sc["end"] / 1000) for sc in json.load(open(a.plan))["scenes"] if sc["kind"] == "take"]
        # only inside a Lottie scene and not overlapping a take scene (a crossfade into a take counts as the take)
        authored = [t for t in r["midmotion_list"] if any(s0 <= t <= s1 for s0, s1 in lottie) and not any(s0 <= t <= s1 for s0, s1 in takes)]
        r["midmotion_lottie"] = len(authored)
        r["midmotion_list"] = [t for t in r["midmotion_list"] if t not in authored]
    r["midmotion_repeats"] = len(r["midmotion_list"])
    r["midmotion_list"] = r["midmotion_list"][:20]
    if a.ref and ref and abs(ref["fps"] - info["fps"]) < 0.01:
        r.update(fidelity(a.video, a.ref, a.ffmpeg_vmaf, info))
    r["gate"] = {
        "motion_unique_ge_95": r["motion_unique_pct"] >= 95,
        "no_judder_freeze": r["judder_freezes"] == 0,
        "no_sync_flash": not r["sync_flash_frames"],
        **({"no_midmotion_repeat": r["midmotion_repeats"] == 0} if a.exact else {}),
        **({"vmaf_ge_95": r["vmaf_mean"] >= 95} if "vmaf_mean" in r else {}),
    }
    if a.json:
        with open(a.json, "w") as f:
            json.dump(r, f, indent=2)
    print(json.dumps({k: v for k, v in r.items() if k not in ("judder_list", "midmotion_list")}))
    return 0 if all(r["gate"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())

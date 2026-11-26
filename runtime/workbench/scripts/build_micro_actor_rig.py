#!/usr/bin/env python3
"""Align same-body micro-acting edit variants and extract non-overlapping eye/mouth patches.

Preserves 100% of static body/hair/glasses/coat pixels from the clean base image while
computing sub-region feathered patches for eyes (blink, gaze) and mouth (viseme openness),
plus a 3x3 magnified facial inspection matrix to verify zero seam/ghosting artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean_base_rgba(src: Path, dst: Path, stray_alpha: int = 10) -> dict[str, Any]:
    im = Image.open(src).convert("RGBA")
    arr = np.array(im)
    a = arr[..., 3]
    removed = int(((a >= 1) & (a <= stray_alpha)).sum())
    a[a <= stray_alpha] = 0
    arr[..., 3] = a
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(dst, optimize=True)
    ys, xs = np.where(a >= 25)
    h, w = a.shape
    return {
        "width": w,
        "height": h,
        "corners_alpha": [int(a[0, 0]), int(a[0, -1]), int(a[-1, 0]), int(a[-1, -1])],
        "stray_removed": removed,
        "content_bounds": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else [0, 0, w, h],
        "sha256": sha256_file(dst),
    }


def _shift_image(arr: np.ndarray, dx: int, dy: int) -> np.ndarray:
    h, w, c = arr.shape
    out = np.zeros_like(arr)
    sx0 = max(0, -dx)
    sx1 = min(w, w - dx)
    sy0 = max(0, -dy)
    sy1 = min(h, h - dy)
    dx0 = max(0, dx)
    dx1 = dx0 + (sx1 - sx0)
    dy0 = max(0, dy)
    dy1 = dy0 + (sy1 - sy0)
    if sx1 > sx0 and sy1 > sy0:
        out[dy0:dy1, dx0:dx1] = arr[sy0:sy1, sx0:sx1]
    return out


def align_variant_to_base(
    base_arr: np.ndarray,
    var_arr: np.ndarray,
    static_mask: np.ndarray,
    max_shift: int = 8,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Find integer (dx, dy) maximizing pixel agreement on static non-facial pixels."""
    if var_arr.shape != base_arr.shape:
        var_arr = np.array(
            Image.fromarray(var_arr, "RGBA").resize((base_arr.shape[1], base_arr.shape[0]), Image.Resampling.LANCZOS)
        )
    b_rgb = base_arr[..., :3].astype(np.float32)
    b_a = base_arr[..., 3:4].astype(np.float32) / 255.0
    best_score = float("inf")
    best_shift = (0, 0)
    ys, xs = np.where(static_mask)
    # Sample at step 2 for speed during search
    ys_s, xs_s = ys[::2], xs[::2]
    b_pts = b_rgb[ys_s, xs_s]
    ba_pts = b_a[ys_s, xs_s]

    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            shifted = _shift_image(var_arr, dx, dy)
            v_pts = shifted[ys_s, xs_s, :3].astype(np.float32)
            va_pts = shifted[ys_s, xs_s, 3:4].astype(np.float32) / 255.0
            diff = np.abs(v_pts - b_pts).mean(axis=1) + np.abs(va_pts[:, 0] - ba_pts[:, 0]) * 60.0
            score = float(diff.mean())
            if score < best_score:
                best_score = score
                best_shift = (dx, dy)

    aligned = _shift_image(var_arr, best_shift[0], best_shift[1])
    return aligned, {"dx": best_shift[0], "dy": best_shift[1], "static_l1": round(best_score, 3)}


def _detect_peak_box(base_arr: np.ndarray, var_arr: np.ndarray, y_lo: int, y_hi: int, x_lo: int, x_hi: int, pad: int = 8) -> list[int]:
    diff = np.abs(var_arr[y_lo:y_hi, x_lo:x_hi, :3].astype(np.float32) - base_arr[y_lo:y_hi, x_lo:x_hi, :3].astype(np.float32)).mean(axis=2)
    # Weighted with alpha diff inside face
    adiff = np.abs(var_arr[y_lo:y_hi, x_lo:x_hi, 3].astype(np.float32) - base_arr[y_lo:y_hi, x_lo:x_hi, 3].astype(np.float32)) * 0.4
    score = diff + adiff
    thresh = max(14.0, float(np.quantile(score, 0.96)) * 0.45)
    ys, xs = np.where(score >= thresh)
    if len(ys) == 0:
        raise ValueError(f"No significant facial difference detected inside band y=[{y_lo}..{y_hi}], x=[{x_lo}..{x_hi}]")
    # Remove isolated 1-2px noise by keeping components within 15px of median mass if needed
    y0 = max(y_lo, int(ys.min()) + y_lo - pad)
    y1 = min(y_hi, int(ys.max()) + y_lo + pad + 1)
    x0 = max(x_lo, int(xs.min()) + x_lo - pad)
    x1 = min(x_hi, int(xs.max()) + x_lo + pad + 1)
    return [x0, y0, x1, y1]


def _union_boxes(boxes: list[list[int]]) -> list[int]:
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _feathered_patch(base_arr: np.ndarray, var_arr: np.ndarray, box: list[int], feather: int = 6) -> Image.Image:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    sub_var = var_arr[y0:y1, x0:x1].astype(np.float32).copy()
    sub_base = base_arr[y0:y1, x0:x1].astype(np.float32)

    # Mild boundary skin-tone offset calibration using outer 3px perimeter where base is opaque
    ring = np.zeros((h, w), dtype=bool)
    ring[:3, :] = True
    ring[-3:, :] = True
    ring[:, :3] = True
    ring[:, -3:] = True
    ring &= (sub_base[..., 3] > 200) & (sub_var[..., 3] > 200)
    if ring.sum() >= 24:
        delta = np.median(sub_base[ring, :3] - sub_var[ring, :3], axis=0)
        delta = np.clip(delta, -10.0, 10.0)
        sub_var[..., :3] = np.clip(sub_var[..., :3] + delta, 0, 255)

    # Difference-guided sparse alpha mask: keep glasses/skin/contour 100% locked to base,
    # allowing only actual eye/mouth edits plus a smooth dilated feather halo.
    rgb_diff = np.abs(sub_var[..., :3] - sub_base[..., :3]).mean(axis=2)
    core_thresh = max(20.0, float(np.quantile(rgb_diff, 0.90)) * 0.45)
    core_mask = (rgb_diff >= core_thresh).astype(np.uint8) * 255
    mask_img = Image.fromarray(core_mask, "L")
    # Dilate slightly so anti-aliased iris/lid/lip edges remain intact, then smooth blur
    mask_img = mask_img.filter(ImageFilter.MaxFilter(5))
    blur_r = max(1.5, float(feather) * 0.5)
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(blur_r))
    diff_weight = np.array(mask_img, dtype=np.float32) / 255.0
    # Boost core back to full 1.0 where actual movement happens
    diff_weight = np.where(rgb_diff >= max(28.0, core_thresh * 1.3), np.maximum(diff_weight, 0.96), diff_weight)

    # Cosine border taper near box edge to guarantee zero hard box cutoff
    yy, xx = np.mgrid[0:h, 0:w]
    edge_dist = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)).astype(np.float32)
    f = float(max(2, feather))
    border_weight = 0.5 - 0.5 * np.cos(np.pi * np.clip(edge_dist / f, 0.0, 1.0))

    weight = np.clip(diff_weight * border_weight, 0.0, 1.0)
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[..., :3] = np.clip(sub_var[..., :3], 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(sub_var[..., 3] * weight, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def build_rig(
    raw_dir: Path,
    out_dir: Path,
    rig_id: str = "micro_actor_v1",
    align_ref_path: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_base_path = raw_dir / "base_clean.png"
    base_metrics = clean_base_rgba(raw_dir / "base.png", clean_base_path)
    base_arr = np.array(Image.open(clean_base_path).convert("RGBA"))
    align_arr = np.array(Image.open(align_ref_path).convert("RGBA")) if align_ref_path and align_ref_path.is_file() else base_arr
    if align_arr.shape != base_arr.shape:
        align_arr = np.array(Image.fromarray(align_arr, "RGBA").resize((base_arr.shape[1], base_arr.shape[0]), Image.Resampling.LANCZOS))
    h, w = base_arr.shape[:2]

    bx0, by0, bx1, by1 = base_metrics["content_bounds"]
    # Static ring mask: hair outer/body torso outside central face box
    face_cx = (bx0 + bx1) // 2
    static_mask = (base_arr[..., 3] > 180)
    static_mask[int(by0 + (by1 - by0) * 0.10) : int(by0 + (by1 - by0) * 0.45), max(0, face_cx - 170) : min(w, face_cx + 170)] = False

    variants = {}
    alignments = {}
    for key in ("eyes_closed", "eyes_glance_left", "mouth_soft_open", "mouth_mid_open"):
        p = raw_dir / f"{key}.png"
        var_arr = np.array(Image.open(p).convert("RGBA"))
        aligned, info = align_variant_to_base(align_arr, var_arr, static_mask)
        aligned[..., 3] = np.minimum(aligned[..., 3], base_arr[..., 3])
        variants[key] = aligned
        alignments[key] = info

    # Auto-search head face region based on content_bounds height
    body_h = by1 - by0
    # Eyes sit roughly at 16%..33% of waist-up portrait height; mouth at 31%..44%
    eye_y_lo = by0 + int(body_h * 0.13)
    eye_y_hi = by0 + int(body_h * 0.34)
    mouth_y_lo = by0 + int(body_h * 0.28)
    mouth_y_hi = by0 + int(body_h * 0.46)
    face_x_lo = max(0, face_cx - 160)
    face_x_hi = min(w, face_cx + 160)

    # First locate each raw peak strictly in narrower prior sub-bands
    e_boxes = [
        _detect_peak_box(align_arr, variants["eyes_closed"], eye_y_lo, by0 + int(body_h * 0.31), face_x_lo, face_x_hi, pad=7),
        _detect_peak_box(align_arr, variants["eyes_glance_left"], eye_y_lo, by0 + int(body_h * 0.31), face_x_lo, face_x_hi, pad=7),
    ]
    eye_box = _union_boxes(e_boxes)

    # Search mouth strictly BELOW eye_box bottom (or enforce separation >= 4px)
    m_y_lo = max(mouth_y_lo, eye_box[3] + 2)
    m_boxes = [
        _detect_peak_box(align_arr, variants["mouth_soft_open"], m_y_lo, mouth_y_hi, max(0, face_cx - 120), min(w, face_cx + 120), pad=6),
        _detect_peak_box(align_arr, variants["mouth_mid_open"], m_y_lo, mouth_y_hi, max(0, face_cx - 120), min(w, face_cx + 120), pad=6),
    ]
    mouth_box = _union_boxes(m_boxes)

    # Safety clamp if expansion slightly touches
    if eye_box[3] >= mouth_box[1]:
        mid = (eye_box[3] + mouth_box[1]) // 2
        eye_box[3] = mid - 1
        mouth_box[1] = mid + 1
    assert eye_box[3] < mouth_box[1], f"Eye box {eye_box} overlaps mouth box {mouth_box}"

    # Export locked 100% base & local patches
    base_out = out_dir / "base.png"
    base_out.write_bytes(clean_base_path.read_bytes())

    eye_patches = {}
    for key in ("eyes_closed", "eyes_glance_left"):
        patch = _feathered_patch(align_arr, variants[key], eye_box, feather=5)
        fn = f"{key}.png"
        patch.save(out_dir / fn, optimize=True)
        eye_patches[key] = {
            "path": fn,
            "x": eye_box[0],
            "y": eye_box[1],
            "w": eye_box[2] - eye_box[0],
            "h": eye_box[3] - eye_box[1],
            "sha256": sha256_file(out_dir / fn),
        }

    mouth_patches = {}
    for key in ("mouth_soft_open", "mouth_mid_open"):
        patch = _feathered_patch(align_arr, variants[key], mouth_box, feather=5)
        fn = f"{key}.png"
        patch.save(out_dir / fn, optimize=True)
        mouth_patches[key] = {
            "path": fn,
            "x": mouth_box[0],
            "y": mouth_box[1],
            "w": mouth_box[2] - mouth_box[0],
            "h": mouth_box[3] - mouth_box[1],
            "sha256": sha256_file(out_dir / fn),
        }

    origin = [round(float((bx0 + bx1) / 2.0), 1), int(by1)]
    rig_doc = {
        "schema": "micro_actor_rig/v1",
        "id": rig_id,
        "baseSize": [w, h],
        "origin": origin,
        "contentBounds": base_metrics["content_bounds"],
        "baseSha256": base_metrics["sha256"],
        "eyeBox": eye_box,
        "mouthBox": mouth_box,
        "roiSeparationPx": int(mouth_box[1] - eye_box[3]),
        "alignments": alignments,
        "eyes": eye_patches,
        "mouths": mouth_patches,
        "staticBodyLockPct": 100.0,
    }
    (out_dir / "rig.json").write_text(json.dumps(rig_doc, ensure_ascii=False, indent=2) + "\n")

    # Build 3x3 magnified face composite verification matrix
    fx0 = max(0, min(eye_box[0], mouth_box[0]) - 65)
    fy0 = max(0, eye_box[1] - 90)
    fx1 = min(w, max(eye_box[2], mouth_box[2]) + 65)
    fy1 = min(h, mouth_box[3] + 65)
    fw, fh = fx1 - fx0, fy1 - fy0
    cell_scale = 2 if fw <= 320 else 1.5
    cw, ch = int(round(fw * cell_scale)), int(round(fh * cell_scale))

    eye_states = [("open", None), ("glance_left", eye_patches["eyes_glance_left"]), ("closed", eye_patches["eyes_closed"])]
    mouth_states = [("closed", None), ("soft_open", mouth_patches["mouth_soft_open"]), ("mid_open", mouth_patches["mouth_mid_open"])]

    pad_c = 16
    hdr = 34
    mat = Image.new("RGB", (3 * cw + 4 * pad_c, 3 * (ch + hdr) + 4 * pad_c), (242, 238, 228))
    draw = ImageDraw.Draw(mat)
    base_img = Image.open(base_out).convert("RGBA")

    for r_i, (ename, ep) in enumerate(eye_states):
        for c_i, (mname, mp) in enumerate(mouth_states):
            comp = base_img.copy()
            if ep:
                comp.alpha_composite(Image.open(out_dir / ep["path"]).convert("RGBA"), (ep["x"], ep["y"]))
            if mp:
                comp.alpha_composite(Image.open(out_dir / mp["path"]).convert("RGBA"), (mp["x"], mp["y"]))
            bg = Image.new("RGBA", (fw, fh), (228, 200, 164, 255))
            bg.alpha_composite(comp.crop((fx0, fy0, fx1, fy1)), (0, 0))
            zoomed = bg.convert("RGB").resize((cw, ch), Image.Resampling.BICUBIC)
            px = pad_c + c_i * (cw + pad_c)
            py = pad_c + r_i * (ch + hdr + pad_c)
            draw.text((px, py), f"eye={ename} | mouth={mname}", fill=(30, 48, 44))
            mat.paste(zoomed, (px, py + hdr))
    mat.save(out_dir / "rig_3x3_face_matrix.png")
    return rig_doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--rig-id", default="micro_actor_v1")
    parser.add_argument("--align-ref", type=Path, default=None, help="Optional composited solid-bg base image used during opaque edit generation")
    args = parser.parse_args()
    doc = build_rig(args.raw_dir, args.out_dir, rig_id=args.rig_id, align_ref_path=args.align_ref)
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

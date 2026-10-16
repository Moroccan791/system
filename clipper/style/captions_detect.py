"""Read the caption look out of a reference clip - without OCR and without
downloading anything.

Pipeline, per sampled frame:

    local-contrast mask (tophat / blackhat)
      -> letter components
        -> lines (merge letters horizontally)
          -> caption bands (merge lines vertically)
            -> measurements: fill colour, outline colour + width, cap height,
               position, word count, casing, line count

Then across time, per cue:

    karaoke   : does a second text colour appear and disappear word by word?
    animation : do the glyphs grow / fade in over the first frames?
    grouping  : do the measurements repeat frame after frame (stable geometry)?

Everything that cannot be measured honestly is reported as None with a low
confidence instead of a made-up number, and evidence PNGs are written so the
result can be checked by eye.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import subprocess

import cv2
import numpy as np

from .frames import SampledFrame
from ..captions.render import subtitles_filter

# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------


@dataclass
class Band:
    """One caption line detected in one frame (pixel coords, sampled frame)."""

    x: int
    y: int
    w: int
    h: int
    fill_bgr: tuple[int, int, int]
    outline_bgr: tuple[int, int, int] | None = None
    outline_width: float | None = None
    glyph_height: float = 0.0
    n_glyphs: int = 0
    n_words: int = 0
    fill_ratio: float = 0.0
    polarity: str = "light_on_dark"
    text_mask: np.ndarray | None = field(default=None, repr=False)
    # top colour clusters among the glyph pixels: [(bgr, share)], biggest first.
    # Kept because a frame median blends a white base colour with a yellow
    # highlight into a meaningless average.
    palette: list[tuple[tuple[int, int, int], float]] = field(default_factory=list)

    @property
    def cx_ratio(self) -> float:
        return (self.x + self.w / 2)

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


# ---------------------------------------------------------------------------
# single frame
# ---------------------------------------------------------------------------


def _text_mask(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (light_text_mask, dark_text_mask) of locally-contrasting pixels."""
    k = max(3, (min(gray.shape) // 120) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    light = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    dark = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, kernel)
    return light, dark


def _binarize(mask: np.ndarray) -> np.ndarray:
    hi = float(np.percentile(mask, 99.5))
    if hi < 12:
        return np.zeros_like(mask, dtype=np.uint8)
    thr = max(18.0, hi * 0.42)
    return (mask >= thr).astype(np.uint8)


def _letter_components(mask: np.ndarray, min_h: int, max_h: int,
                       return_labels: bool = False):
    """Connected components that could plausibly be single letters.

    Each entry is (x, y, w, h, pixel_area) - area matters because letters carry
    most of the ink while anti-aliasing fragments carry very little, which is
    how the real letter height is found on a busy background.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out: list[tuple[int, int, int, int, int]] = []
    keep: list[int] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (min_h <= h <= max_h):
            continue
        if w > h * 3:            # too wide to be one glyph
            continue
        if area < max(6, h * 0.6):
            continue
        # glyphs are strokes: they never fill their bounding box. Solid blocks
        # (grid cells, blobs, UI panels) are the classic false positive on
        # textured backgrounds, and they carry enough ink to poison the
        # dominant-letter clustering.
        box_fill = float(area) / float(max(1, w * h))
        if box_fill > 0.88 or box_fill < 0.10:
            continue
        if not (0.12 <= (w / max(1, h)) <= 2.0):
            continue
        out.append((int(x), int(y), int(w), int(h), int(area)))
        keep.append(i)
    return (out, labels, keep) if return_labels else out


def _bbox(boxes: list[tuple[int, int, int, int, ...]]) -> tuple[int, int, int, int, int]:
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return int(x0), int(y0), int(x1 - x0), int(y1 - y0), len(boxes)


def _median_letter_width(comps: list[tuple[int, int, int, int, ...]]) -> float:
    widths = [c[2] for c in comps if c[2] > 0]
    return float(np.median(widths)) if widths else 12.0


def _group_lines(boxes: list[tuple[int, int, int, int, ...]], max_gap: int | None = None,
                 min_glyphs: int = 3) -> list[tuple[int, int, int, int, int]]:
    """Merge letter boxes into text lines. Returns (x, y, w, h, n_glyphs).

    The gap threshold defaults to ~2.5 letter widths: wide enough to bridge word
    spaces (so a whole caption line stays one unit) while word counting is left
    to the column-gap analysis, which measures it properly.
    """
    if not boxes:
        return []
    if max_gap is None:
        max_gap = max(8, int(2.5 * _median_letter_width(boxes)))
    rows: list[list[tuple[int, int, int, int, ...]]] = []
    for box in sorted(boxes, key=lambda b: (b[1], b[0])):
        placed = False
        for row in rows:
            r_y = min(b[1] for b in row)
            r_h = max(b[1] + b[3] for b in row) - r_y
            b_cy = box[1] + box[3] / 2
            if r_y + 0.15 * r_h <= b_cy <= r_y + 0.85 * r_h:
                row.append(box)
                placed = True
                break
        if not placed:
            rows.append([box])

    lines: list[tuple[int, int, int, int, int]] = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        cluster: list[tuple[int, int, int, int, ...]] = [row[0]]
        for box in row[1:]:
            gap = box[0] - (cluster[-1][0] + cluster[-1][2])
            if gap <= max_gap:
                cluster.append(box)
                continue
            if len(cluster) >= min_glyphs:
                lines.append(_bbox(cluster))
            cluster = [box]
        if len(cluster) >= min_glyphs:
            lines.append(_bbox(cluster))
    return lines


def _stroke_ratio(mask: np.ndarray, box: tuple[int, int, int, int]) -> float:
    """Stroke width / glyph height. Letters sit around 0.1-0.4; the thin dark
    ring drawn around letters (an outline, not text) sits far below."""
    x, y, w, h = box
    local = mask[y:y + h, x:x + w]
    if local.size == 0:
        return 0.0
    dist = cv2.distanceTransform((local > 0).astype(np.uint8), cv2.DIST_L2, 3)
    if dist.max() <= 0:
        return 0.0
    return float(2.0 * dist.max() / max(1, h))


def _dominant_cluster(boxes: list[tuple[int, int, int, int, int]],
                      tol: float = 0.30) -> tuple[float, float, list[int]]:
    """Height of the dominant letter population, ink-weighted.

    Returns (height, ink_ratio, selected_component_indices). Weighting by pixel
    area rather than component count is the whole trick: fragments are numerous
    but nearly inkless, real letters are few but hold the ink.
    """
    if not boxes:
        return 0.0, 0.0, []
    heights = np.array([b[3] for b in boxes], dtype=float)
    areas = np.array([b[4] for b in boxes], dtype=float)
    total_ink = float(areas.sum()) or 1.0
    # weight each distinct height by the ink at that height
    by_height: dict[int, float] = {}
    for h, a in zip(heights, areas):
        by_height[int(h)] = by_height.get(int(h), 0.0) + float(a)
    if not by_height:
        return 0.0, 0.0, []
    peak = max(by_height, key=lambda k: by_height[k])
    # refine with a weighted mean of the neighbourhood, then keep inliers
    for _ in range(2):
        sel = np.abs(heights - peak) <= tol * peak
        if sel.sum() == 0:
            break
        peak = float(np.average(heights[sel], weights=areas[sel]))
    sel = np.abs(heights - peak) <= tol * peak
    selected = [i for i in range(len(boxes)) if sel[i]]
    ink_ratio = float(areas[sel].sum() / total_ink) if sel.any() else 0.0
    return peak, ink_ratio, selected


def _clean_mask(mask: np.ndarray, labels: np.ndarray, keep: list[int],
                boxes: list[tuple[int, int, int, int, int]],
                *, min_ink: float = 0.45, min_letters: int = 3):
    """Rebuild the mask from only the dominant letter population.

    Returns (clean_mask, letter_height, kept_boxes). Everything measured after
    this point (box, colours, word count, column profile) sees the caption and
    not the scene behind it.
    """
    height, ink_ratio, selected = _dominant_cluster(boxes)
    if height <= 0 or len(selected) < min_letters or ink_ratio < min_ink:
        return mask, height, boxes
    ids = [keep[i] for i in selected]
    clean = np.isin(labels, ids).astype(np.uint8)
    kept = [boxes[i] for i in selected]
    return clean, height, kept


def _measure(frame_bgr: np.ndarray, box: tuple[int, int, int, int, int],
             mask: np.ndarray, labels: np.ndarray, keep: list[int],
             boxes: list[tuple[int, int, int, int, int]]) -> Band | None:
    x, y, w, h, n_glyphs = box
    # 1. keep only letters of one size -> this is what makes a bushy background
    #    (grids, textures, UI) stop looking like text
    clean_full, letter_h, kept = _clean_mask(mask, labels, keep, boxes)
    if letter_h <= 0:
        return None
    clean = clean_full[y:y + h, x:x + w]
    if clean.size == 0 or int(clean.sum()) < 20:
        return None
    sel = clean > 0
    ys, xs = np.nonzero(sel)
    if len(ys) == 0:
        return None
    # 2. re-derive the box from the cleaned glyphs only
    x, y = x + int(xs.min()), y + int(ys.min())
    w, h = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    local = clean_full[y:y + h, x:x + w]
    sel = local > 0
    fill_ratio = float(sel.mean())
    if not (0.03 <= fill_ratio <= 0.75):
        return None

    # 3. colours from the glyph pixels
    pixels = frame_bgr[y:y + h, x:x + w][sel]
    palette = _palette(pixels)
    fill = np.array(palette[0][0], dtype=float) if palette else np.median(pixels, axis=0)

    ring_k = max(2, int(round(h * 0.10)))
    grown = cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * ring_k + 1,) * 2))
    ring = (grown > 0) & ~sel
    outline_bgr = None
    outline_w = None
    if ring.sum() > 20:
        ring_px = frame_bgr[y:y + h, x:x + w][ring]
        cand = np.median(ring_px, axis=0).astype(int)
        if float(np.abs(cand.astype(float) - fill).sum()) > 90:
            outline_bgr = tuple(int(v) for v in cand)
            profile = []
            for t in range(1, ring_k + 1):
                grown_t = cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * t + 1,) * 2))
                ring_t = (grown_t > 0) & (local == 0)
                if ring_t.sum() == 0:
                    break
                px = frame_bgr[y:y + h, x:x + w][ring_t]
                diff = np.abs(px.astype(float) - np.array(outline_bgr, dtype=float)).mean(axis=1)
                profile.append(float(np.mean(diff < 75)))
            if profile:
                outline_w = float(np.sum(profile)) + 0.5

    # glyph height = dominant letter height (ink-weighted), never the raw box
    glyph_h = float(letter_h) if letter_h > 0 else float(h)

    # words: bridge letters into words, then count the word blobs. A horizontal
    # dilation of ~half a letter closes intra-word letter gaps but not spaces.
    letters = [b for b in kept]
    letter_w = float(np.median([b[2] for b in letters])) if letters else glyph_h * 0.6
    bridge = max(1, int(round(letter_w * 0.25)))
    joined = cv2.dilate(local, cv2.getStructuringElement(cv2.MORPH_RECT, (bridge * 2 + 1, 1)))
    n_comp, _, stats_c, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    min_word_px = max(4, int(glyph_h * 0.35))
    n_words = sum(1 for i in range(1, n_comp)
                  if stats_c[i, cv2.CC_STAT_AREA] >= min_word_px) or 1

    return Band(x=x, y=y, w=w, h=h, fill_bgr=(int(fill[0]), int(fill[1]), int(fill[2])),
                outline_bgr=outline_bgr, outline_width=outline_w, glyph_height=glyph_h,
                n_glyphs=n_glyphs, n_words=int(n_words), fill_ratio=fill_ratio,
                polarity="light_on_dark" if float(np.mean(fill)) > 110 else "dark_on_light",
                text_mask=local.copy(), palette=palette)


def _palette(pixels: np.ndarray, bins: int = 16, top: int = 3,
             min_share: float = 0.08) -> list[tuple[tuple[int, int, int], float]]:
    """Quantise glyph colours into clusters, biggest first.

    Returns [(mean_bgr_of_cluster, share)] which is what lets a white base
    colour and a yellow highlight be told apart inside a single frame.
    """
    if pixels is None or len(pixels) == 0:
        return []
    px = np.asarray(pixels, dtype=np.int32)
    q = (px // bins) * bins
    keys = q[:, 0] * 65536 + q[:, 1] * 256 + q[:, 2]
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    total = float(counts.sum())
    order = np.argsort(-counts)[:top]
    out: list[tuple[tuple[int, int, int], float]] = []
    for i in order:
        share = float(counts[i] / total)
        if share < min_share:
            continue
        mean = px[inv == i].mean(axis=0)
        out.append((tuple(int(v) for v in mean), round(share, 3)))
    return out


def _surround_luminance(frame_bgr: np.ndarray, box: tuple[int, int, int, int], pad: float) -> float:
    """Median luminance just outside the band - the "background" the text sits on."""
    H, W = frame_bgr.shape[:2]
    x, y, w, h = box
    px = int(max(4, pad))
    out_y0, out_y1 = max(0, y - px), min(H, y + h + px)
    out_x0, out_x1 = max(0, x - px), min(W, x + w + px)
    outer = frame_bgr[out_y0:out_y1, out_x0:out_x1]
    if outer.size == 0:
        return 0.0
    mask = np.ones(outer.shape[:2], dtype=bool)
    inner_y0, inner_x0 = y - out_y0, x - out_x0
    mask[inner_y0:inner_y0 + h, inner_x0:inner_x0 + w] = False
    if not mask.any():
        return 0.0
    return float(np.median(cv2.cvtColor(outer, cv2.COLOR_BGR2GRAY)[mask]))


def _polarity_ok(fill_lum: float, surround_lum: float, polarity: str) -> bool:
    """Captions are bright-on-dark or dark-on-light *relative to their setting*.

    This is what stops the detector latching onto a black outline drawn around
    white glyphs: that ring is dark, but its surroundings are dark too.
    """
    if polarity == "light_on_dark":
        return fill_lum >= 145.0 and surround_lum <= 150.0 and (fill_lum - surround_lum) >= 45.0
    return fill_lum <= 110.0 and surround_lum >= 135.0 and (surround_lum - fill_lum) >= 45.0


def _text_score(band: Band, heights: list[int], stroke: float) -> float:
    """How much does this look like a line of caption text?"""
    score = 0.0
    score += min(1.0, band.n_glyphs / 6.0)                        # enough letters
    if heights and len(heights) >= 3:
        cv_h = float(np.std(heights) / (np.mean(heights) + 1e-6))
        score += 1.0 / (1.0 + 3.0 * cv_h)                          # even heights
    score += 1.0 if 0.06 <= stroke <= 0.5 else 0.15                # letters have body
    score += 1.0 if 1.8 <= (band.w / max(1, band.h)) <= 30 else 0.2
    score += 1.0 if 0.05 <= band.fill_ratio <= 0.6 else 0.2
    score += min(1.0, band.w / 180.0)          # prefer the whole line over a piece
    return score / 6.0


def _candidate_masks(gray: np.ndarray, region: tuple[int, int]) -> list[tuple[str, np.ndarray]]:
    """Several ways of saying "this pixel is text", because no single one works
    on every background.

    local contrast (top-hat at two thresholds) handles captions on busy or
    low-contrast backgrounds; an absolute brightness cut handles the case where
    local contrast vanishes (light text over a light patch) - the failure mode
    that split a real caption into two fragments during development.
    """
    y0, y1 = region
    tophat, blackhat = _text_mask(gray)
    top_region = tophat[y0:y1]
    p99 = float(np.percentile(top_region, 99.5)) if top_region.size else 0.0
    masks: list[tuple[str, np.ndarray]] = []
    if p99 >= 10:
        for scale, floor in ((0.42, 18.0), (0.22, 10.0)):
            binary = np.zeros_like(tophat)
            binary[y0:y1] = (top_region >= max(floor, p99 * scale)).astype(np.uint8)
            masks.append((f"tophat_{scale:.2f}", binary))
    bright = np.zeros_like(gray)
    bright[y0:y1] = ((gray[y0:y1] >= 185) & (tophat[y0:y1] >= 8)).astype(np.uint8)
    if bright.sum() > 50:
        # drop structures thinner than ~2 px: grid lines and UI hairlines
        bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN,
                                  cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)))
        masks.append(("bright", bright))
    dark = np.zeros_like(gray)
    dark[y0:y1] = (gray[y0:y1] <= 55).astype(np.uint8)
    if dark.sum() > 50 and blackhat[y0:y1].max() >= 40:
        masks.append(("dark", dark))
    return masks


def _iou(a: Band, b: Band) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    return inter / float(a.w * a.h + b.w * b.h - inter)


def _same_line(a: Band, b: Band, tol: float = 0.5) -> bool:
    return abs(a.y + a.h / 2 - (b.y + b.h / 2)) <= tol * max(a.h, b.h)


def _refine_group_heights(group: list[tuple[float, Band]]) -> None:
    """Re-measure a line's glyph height on the union of every mask that found it.

    Different thresholds capture different parts of the same letterforms: a high
    top-hat threshold keeps the bright cores but breaks letters into pieces,
    a low one or a plain brightness cut fills them in. Measuring each mask alone
    therefore under-reads the cap height (a fragment cluster wins the ink vote);
    their union is a complete letterform, so the measurement is taken there.
    """
    if len(group) < 2:
        return
    x0 = min(b.x for _, b in group)
    y0 = min(b.y for _, b in group)
    x1 = max(b.x + b.w for _, b in group)
    y1 = max(b.y + b.h for _, b in group)
    union = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    for _, band in group:
        if band.text_mask is None:
            continue
        mh, mw = band.text_mask.shape
        oy, ox = band.y - y0, band.x - x0
        target = union[oy:oy + mh, ox:ox + mw]
        union[oy:oy + mh, ox:ox + mw] = np.maximum(target, band.text_mask[:mh, :mw])
    if int(union.sum()) == 0:
        return
    min_h = max(4, int(union.shape[0] * 0.4))
    boxes = _letter_components(union, 4, max(8, union.shape[0] + 4))
    height, ink, _ = _dominant_cluster(boxes)
    if height > 0 and ink >= 0.35:
        for _, band in group:
            band.glyph_height = float(max(band.glyph_height, height))


def _coverage(inner: Band, outer: Band) -> float:
    """Fraction of `inner`'s width that lies inside `outer`."""
    x0 = max(inner.x, outer.x)
    x1 = min(inner.x + inner.w, outer.x + outer.w)
    if x1 <= x0:
        return 0.0
    return (x1 - x0) / float(max(1, inner.w))


def _redundant(candidate: Band, kept: Band) -> bool:
    """True when `candidate` is just a piece of `kept` (same line, inside it).

    IoU is the wrong test here: a 65 px fragment inside a 273 px caption has a
    tiny IoU yet is obviously the same text, found again by another mask.

    The direction matters and must not be symmetric: a fragment inside a caption
    covers 100% of *itself* with the caption, so a symmetric test would let the
    fragment throw the full line away.
    """
    if not _same_line(candidate, kept):
        return _iou(candidate, kept) > 0.25
    if candidate.w <= kept.w:
        return _coverage(candidate, kept) >= 0.6 or _iou(candidate, kept) > 0.25
    return _iou(candidate, kept) > 0.25


def _merge_line_fragments(bands: list[tuple[float, Band]], max_gap_ratio: float = 2.5,
                          tol_y: float = 0.3, frame_width: int = 1080) -> list[tuple[float, Band]]:
    """Re-join a caption line that a background patch split into fragments.

    Fragments sit on the same baseline, are similar in height and are separated
    by at most a couple of cap heights (a background patch swallowing a word can
    leave that much space). Two genuinely separate text blocks essentially never
    share a baseline that closely, so this is safe, and it is what keeps a
    caption from being reported as two short bands - which would wreck the
    centre-x, width and word-count measurements.
    """
    out = list(bands)
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i][1], out[j][1]
                gap = max(a.x, b.x) - min(a.x + a.w, b.x + b.w)
                same_line = abs(a.y - b.y) <= tol_y * max(a.h, b.h)
                same_height = abs(a.glyph_height - b.glyph_height) <= 0.25 * max(
                    a.glyph_height, b.glyph_height, 1.0)
                wide = (min(a.x, b.x) + gap + max(a.w, b.w)) <= 0.94 * frame_width
                if same_line and same_height and wide and 0 <= gap <= max_gap_ratio * max(a.h, b.h):
                    left, right = (a, b) if a.x <= b.x else (b, a)
                    x0 = left.x
                    x1 = max(left.x + left.w, right.x + right.w)
                    y0 = min(a.y, b.y)
                    y1 = max(a.y + a.h, b.y + b.h)
                    combined = Band(x=x0, y=y0, w=x1 - x0, h=y1 - y0,
                                    fill_bgr=left.fill_bgr, outline_bgr=left.outline_bgr,
                                    outline_width=left.outline_width,
                                    glyph_height=max(a.glyph_height, b.glyph_height),
                                    n_glyphs=a.n_glyphs + b.n_glyphs,
                                    n_words=a.n_words + b.n_words,
                                    fill_ratio=(a.fill_ratio + b.fill_ratio) / 2,
                                    polarity=left.polarity,
                                    text_mask=_merge_masks(a, b, x0, y0),
                                    palette=left.palette)
                    score = max(out[i][0], out[j][0])
                    out = [o for k, o in enumerate(out) if k not in (i, j)] + [(score, combined)]
                    merged = True
                    break
            if merged:
                break
    return out


def _merge_masks(a: Band, b: Band, x0: int, y0: int) -> np.ndarray:
    """Combine two fragment masks on the union bounding box."""
    w = max(a.x + a.w, b.x + b.w) - x0
    h = max(a.y + a.h, b.y + b.h) - y0
    out = np.zeros((h, w), dtype=np.uint8)
    for band in (a, b):
        if band.text_mask is None:
            continue
        hh, ww = band.text_mask.shape
        oy, ox = band.y - y0, band.x - x0
        out[oy:oy + hh, ox:ox + ww] = np.maximum(out[oy:oy + hh, ox:ox + ww],
                                                 band.text_mask[:hh, :ww])
    return out


def detect_bands(frame_bgr: np.ndarray, *, region: tuple[float, float] = (0.08, 1.0),
                 max_bands: int = 2, include_scores: bool = False):
    """Caption-like bands in one frame, best first.

    `region` limits the search to a vertical slice (captions live in the middle
    and lower part of the frame; the top 8% is usually UI/chrome).
    """
    H, W = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    y_top, y_bottom = int(H * region[0]), int(H * region[1])
    min_h = max(4, int(H * 0.012))
    max_h = max(8, int(H * 0.11))

    scored: list[tuple[float, Band]] = []
    for source, binary in _candidate_masks(gray, (y_top, y_bottom)):
        if int(binary.sum()) == 0:
            continue
        boxes, labels, keep = _letter_components(binary, min_h, max_h, return_labels=True)
        if len(boxes) < 3:
            continue
        for line in _group_lines(boxes, min_glyphs=3):
            x, y, w, h, n = line
            if w < W * 0.06 or w > W * 0.99 or x < W * 0.01 or (x + w) > W * 0.995:
                continue
            if h > H * 0.16:
                continue
            band = _measure(frame_bgr, line, binary, labels, keep, boxes)
            if band is None:
                continue
            band.polarity = "light_on_dark" if source != "dark" else "dark_on_light"
            fill_lum = float(np.mean(band.fill_bgr))
            surround = _surround_luminance(frame_bgr, (band.x, band.y, band.w, band.h),
                                           pad=band.h * 0.6)
            if not _polarity_ok(fill_lum, surround, band.polarity):
                continue
            stroke = _stroke_ratio(binary, (band.x, band.y, band.w, band.h))
            if stroke < 0.05:          # a hairline ring, not a letterform
                continue
            score = _text_score(band, [], stroke)
            scored.append((score, band))

    # re-join fragments of the same line, then keep the best non-overlapping ones
    scored = _merge_line_fragments(scored)

    # every mask that found the same line sees a different part of it: measure
    # the line once, on the union of those masks
    groups: list[list[tuple[float, Band]]] = []
    for item in sorted(scored, key=lambda sb: (-sb[1].w, sb[1].x)):
        for group in groups:
            if any(_same_line(item[1], other) and _iou(item[1], other) >= 0.0 and
                   not (item[1].x + item[1].w < other.x or other.x + other.w < item[1].x)
                   for _, other in group):
                group.append(item)
                break
        else:
            groups.append([item])
    for group in groups:
        _refine_group_heights(group)
    scored.sort(key=lambda sb: (-sb[0], -sb[1].n_glyphs))
    kept: list[tuple[float, Band]] = []
    for score, band in scored:
        # a wider band that contains an already-kept one is the better read of
        # the same text (different masks fragment the line differently, and the
        # fragment scores no worse) - so drop what it contains and keep it
        # the newcomer supersedes kept bands only when it is the wider read of
        # the same line and actually covers them
        contained = [k for k, (_, other) in enumerate(kept)
                     if _same_line(other, band) and band.w >= other.w
                     and _coverage(other, band) >= 0.6]
        for k in sorted(contained, reverse=True):
            kept.pop(k)
        if any(_redundant(band, other) for _, other in kept):
            continue
        kept.append((score, band))
        if len(kept) >= max_bands:
            break
    kept.sort(key=lambda sb: -(sb[1].w * sb[0]))
    return kept if include_scores else [b for _, b in kept]


# ---------------------------------------------------------------------------
# across time
# ---------------------------------------------------------------------------


# Calibration of OUR rendering stack, measured (not assumed): `python -m clipper style`
# must answer "what font size would reproduce this cap height with our renderer?".
# Value obtained by rendering HANDSOME with Montserrat Bold at sizes 100/120/200 and
# measuring the glyph box height through this module's own detector; see
# tests/test_style_captions.py::test_font_size_calibration, which re-measures it and
# fails if a font or ffmpeg change moves it.
CAP_HEIGHT_EM = 0.478          # fallback; the real value is calibrated at run time
DEFAULT_CAP_HEIGHT_EM = 0.478
# Per-font spread: DejaVu Sans measures ~0.68, Montserrat ~0.48. Since the font
# cannot be identified from pixels, size estimates carry that error (~±20% for
# geometric sans faces, more for very wide fonts). Reported honestly in the profile.


def _iqr(values: list[float]) -> float:
    return float(np.percentile(values, 75) - np.percentile(values, 25)) if values else 0.0


def _same_band(a: Band, b: Band, tol_x: float, tol_y: float) -> bool:
    return (abs(a.cx_ratio - b.cx_ratio) <= tol_x
            and abs(a.cy - b.cy) <= tol_y
            and 0.6 <= (b.w / max(1, a.w)) <= 1.7)


def _cluster_colors(bands: list[Band], min_share: float = 0.12) -> list[tuple[tuple[int, int, int], float]]:
    """Quantised glyph colours weighted by pixel count -> [(bgr, share)]."""
    buckets: dict[tuple[int, int, int], float] = {}
    exact: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    total = 0.0
    for b in bands:
        palette = b.palette or [(b.fill_bgr, 1.0)]
        weight = float(b.text_mask.sum()) if b.text_mask is not None else 1.0
        for color, share in palette:
            key = tuple(int(c / 24.0) * 24 for c in color)
            buckets[key] = buckets.get(key, 0.0) + weight * share
            exact.setdefault(key, []).append(tuple(int(v) for v in color))
            total += weight * share
    if not total:
        return []
    ranked = sorted(buckets.items(), key=lambda kv: -kv[1])
    out = []
    for key, weight in ranked:
        share = weight / total
        if share < min_share:
            continue
        color = tuple(int(v) for v in np.median(np.array(exact.get(key, [key]), dtype=float), axis=0))
        out.append((color, round(share, 3)))
    return out


def _hex(bgr: tuple[int, int, int]) -> str:
    b, g, r = (int(np.clip(v, 0, 255)) for v in bgr[:3])
    return f"#{r:02X}{g:02X}{b:02X}"


def _dominant_color(bands: list[Band]) -> tuple[int, int, int] | None:
    """Most common glyph colour across these bands, weighted by pixel count."""
    if not bands:
        return None
    buckets: dict[tuple[int, int, int], float] = {}
    exact: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
    for b in bands:
        palette = b.palette or [(b.fill_bgr, 1.0)]
        weight = float(b.text_mask.sum()) if b.text_mask is not None else 1.0
        for color, share in palette:
            key = tuple(int(c / 20.0) * 20 for c in color)
            buckets[key] = buckets.get(key, 0.0) + weight * share
            exact.setdefault(key, []).append(tuple(int(v) for v in color))
    if not buckets:
        return None
    best = max(buckets, key=lambda k: buckets[k])
    # the bucket is only a grouping key: report the median of the real colours
    # that landed in it, so quantisation does not leak into the profile
    return tuple(int(v) for v in np.median(np.array(exact[best], dtype=float), axis=0))


def _color_dist(a, b) -> float:
    return float(np.abs(np.array(a, dtype=float) - np.array(b, dtype=float)).sum())


def _base_and_highlight(cues: list[list[tuple[float, Band]]], fallback: tuple[int, int, int],
                        min_dist: float = 90.0) -> tuple[tuple[int, int, int], tuple[int, int, int] | None]:
    """Base = colour as a cue appears, highlight = colour once words are spoken."""
    starts, ends = [], []
    for cue in cues:
        s = _dominant_color([b for _, b in cue[:2]])
        e = _dominant_color([b for _, b in cue[-2:]])
        if s is not None:
            starts.append(s)
        if e is not None:
            ends.append(e)
    if not starts or not ends:
        return fallback, None
    base = tuple(int(v) for v in np.median(np.array(starts, dtype=float), axis=0))
    end_c = tuple(int(v) for v in np.median(np.array(ends, dtype=float), axis=0))
    if _color_dist(base, end_c) >= min_dist:
        return base, end_c
    return fallback, None


def _upper_likelihood(bands: list[Band]) -> float:
    """How much the glyphs look like capital letters.

    Capitals are top-heavy and have no ascender/descender rows: ink sits in the
    top and bottom bands of the glyph box and the middle rows are lighter.
    Lowercase puts its ink in the x-height band (the middle).

    Rows carrying almost no ink are dropped first: on busy footage they are
    background speckle, and they flatten the very contrast this measures.
    """
    scores: list[float] = []
    for band in bands:
        mask = band.text_mask
        if mask is None or mask.size == 0:
            continue
        rows = mask.sum(axis=1).astype(float)
        if rows.sum() <= 0:
            continue
        keep = rows >= 0.06 * rows.max()
        idx = np.where(keep)[0]
        if len(idx) < 6:
            continue
        rows = rows[idx.min():idx.max() + 1]
        n = len(rows)
        total = float(rows.sum())
        k = max(1, int(n * 0.20))
        edge = (float(rows[:k].sum()) + float(rows[-k:].sum())) / total
        mid = float(rows[int(n * 0.35):int(n * 0.65)].sum()) / total
        edge_score = float(np.clip((edge - 0.30) / 0.15, 0.0, 1.0))
        mid_score = 1.0 - float(np.clip((mid - 0.30) / 0.15, 0.0, 1.0))
        scores.append(0.75 * edge_score + 0.25 * mid_score)
    return float(np.mean(scores)) if scores else 0.0


def _accumulate_masks(cue: list[tuple[float, Band]], tol: float = 2.0) -> np.ndarray | None:
    """Average the glyph masks of a cue into one image.

    The caption is identical in every frame of a cue while background clutter
    moves and changes, so accumulating emphasises text and averages clutter out.
    This is what makes word counts survive on busy footage. Bands are aligned by
    their bottom edge and horizontal centre.
    """
    usable = [(t, b) for t, b in cue if b.text_mask is not None and b.text_mask.size > 0]
    if len(usable) < 2:
        return usable[0][1].text_mask.copy() if usable else None
    ref = max(usable, key=lambda tb: tb[1].w)[1]
    h = int(max(b.h for _, b in usable)) + 4
    w = int(max(b.w for _, b in usable)) + 4
    acc = np.zeros((h, w), dtype=np.float32)
    n = 0
    for _, band in usable:
        m = band.text_mask
        if m is None:
            continue
        mh, mw = m.shape
        ox = int(np.clip((ref.x + ref.w / 2) - (band.x + band.w / 2) + 2, 0, max(0, w - mw)))
        oy = int(np.clip(band.y - (ref.y - 2), 0, max(0, h - mh)))
        acc[oy:oy + mh, ox:ox + mw] += (m > 0).astype(np.float32)
        n += 1
    if n == 0:
        return None
    return (acc / n >= 0.5).astype(np.uint8)


def _cue_upper_likelihood(cues: list[list[tuple[float, Band]]]) -> float:
    """Casing vote across cues, measured on accumulated (clutter-free) masks."""
    votes: list[float] = []
    for cue in cues:
        mask = _accumulate_masks(cue)
        if mask is None or int(mask.sum()) < 30:
            continue
        rows = mask.sum(axis=1).astype(float)
        total = float(rows.sum())
        n = len(rows)
        k = max(1, int(n * 0.20))
        edge = (float(rows[:k].sum()) + float(rows[-k:].sum())) / total
        mid = float(rows[int(n * 0.35):int(n * 0.65)].sum()) / total
        edge_score = float(np.clip((edge - 0.30) / 0.15, 0.0, 1.0))
        mid_score = 1.0 - float(np.clip((mid - 0.30) / 0.15, 0.0, 1.0))
        votes.append(0.75 * edge_score + 0.25 * mid_score)
    return float(np.mean(votes)) if votes else 0.0


def _column_profile(mask: np.ndarray | None, bins: int = 48) -> np.ndarray | None:
    """Normalised ink-per-column signature of a caption line.

    Within one cue the glyphs never move, so this signature is stable; the next
    cue (different words) changes it. That is how consecutive captions at the
    same screen position are told apart without OCR.
    """
    if mask is None or mask.size == 0:
        return None
    cols = mask.sum(axis=0).astype(np.float32)
    if float(cols.sum()) <= 0:
        return None
    idx = np.linspace(0, len(cols), bins + 1).astype(int)
    binned = np.array([cols[idx[i]:max(idx[i] + 1, idx[i + 1])].mean() for i in range(bins)],
                      dtype=np.float32)
    norm = float(np.linalg.norm(binned))
    return binned / norm if norm > 0 else None


def _split_track(track: list[tuple[float, Band]], *, gap: float = 0.35,
                 profile_min: float = 0.86,
                 width_tol: float = 0.14) -> list[list[tuple[float, Band]]]:
    """Split a position-tracked run into cues at every text change.

    Deliberately does NOT split on colour: with karaoke the dominant colour
    flips mid-cue as words get spoken, so a colour jump is a karaoke signal, not
    a cue boundary. Text identity is stable within a cue, so the column profile
    (and the line width) are the reliable separators.
    """
    if not track:
        return []
    out: list[list[tuple[float, Band]]] = [[track[0]]]
    for t, band in track[1:]:
        prev_t, prev = out[-1][-1]
        split = (t - prev_t) > gap
        if not split:
            pa, pb = _column_profile(prev.text_mask), _column_profile(band.text_mask)
            if pa is not None and pb is not None and float(np.dot(pa, pb)) < profile_min:
                split = True
        if not split:
            ratio = band.w / max(1, prev.w)
            if ratio > 1.0 + width_tol or ratio < 1.0 - width_tol:
                split = True
        (out.append([(t, band)]) if split else out[-1].append((t, band)))
    return out


def analyze_captions(frames: list[SampledFrame], *, min_cue_frames: int = 2,
                     canonical_height: int = 1920,
                     cap_height_em: float | None = None) -> dict:
    """Full caption section of the style profile, plus raw measurements."""
    detections: list[tuple[float, Band]] = []
    for frame in frames:
        for band in detect_bands(frame.bgr, max_bands=2):
            detections.append((frame.t, band))

    if not detections:
        return {"present": False, "confidence": 0.0, "evidence": {"cue_count": 0, "frames": []},
                "raw": {}}

    # band geometry is in *sampled* pixels; positions are normalised by the
    # sampled frame, and pixel sizes are converted to the canonical canvas.
    H, W = frames[0].gray.shape[:2]
    tol_x = W * 0.06
    tol_y = H * 0.045

    # ---- detections -> position tracks -> cues -----------------------------
    detections.sort(key=lambda d: d[0])
    # match each detection to the best *open* track, not just the newest one:
    # a frame can contain more than one band (multi-line captions, or a line
    # split by a background patch) and matching only the newest flipped between
    # positions every frame, so no track ever accumulated.
    tracks: list[list[tuple[float, Band]]] = []
    for t, band in detections:
        candidate: list[tuple[float, Band]] | None = None
        for track in tracks:
            last_t, last_band = track[-1]
            if (t - last_t) <= 0.35 and _same_band(last_band, band, tol_x, tol_y):
                if candidate is None or last_t > candidate[-1][0]:
                    candidate = track
        if candidate is not None:
            candidate.append((t, band))
        else:
            tracks.append([(t, band)])
    cues: list[list[tuple[float, Band]]] = []
    for track in tracks:
        cues.extend(_split_track(track))
    cues = [c for c in cues if len(c) >= min_cue_frames]

    if not cues:
        return {"present": False, "confidence": 0.1,
                "evidence": {"cue_count": 0, "frames": [], "note": "detections were not stable"},
                "raw": {"detections": len(detections)}}

    stable = [b for c in cues for _, b in c]
    cue_count = len(cues)

    # measurements that the background can distort are taken from the per-cue
    # accumulated mask instead of single frames
    acc_heights: list[float] = []
    acc_words: list[int] = []
    for cue in cues:
        mask = _accumulate_masks(cue)
        if mask is None or int(mask.sum()) < 30:
            continue
        min_h = max(4, int(H * 0.012))
        boxes = _letter_components(mask, min_h, max_h=max(8, int(H * 0.11)))
        height, ink, _sel = _dominant_cluster(boxes)
        if height > 0 and ink >= 0.35:
            acc_heights.append(height)
            bridge = max(1, int(round(_median_letter_width(boxes) * 0.25)))
            joined = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (bridge * 2 + 1, 1)))
            n_comp, _, st, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
            words = sum(1 for i in range(1, n_comp) if st[i, cv2.CC_STAT_AREA] >= height * 0.5)
            if words:
                acc_words.append(int(words))

    # ---- geometry ----------------------------------------------------------
    cy_vals = [np.mean([b.cy for _, b in c]) / H for c in cues]
    cx_vals = [np.mean([b.cx_ratio for _, b in c]) / W for c in cues]
    cy = float(np.median(cy_vals))
    cx = float(np.median(cx_vals))
    # cap-height proxy: the ink-weighted dominant letter height. The raw box
    # height is unreliable on busy backgrounds (grid lines and texture join the
    # band and inflate it), and a plain median of letter heights is unreliable
    # on noisy footage (fragments drag it down). Ink weighting is robust to both.
    # height comes from the per-frame bands: accumulating a cue's masks is what
    # makes word counts reliable, but the sub-pixel alignment needed to stack
    # masks fragments the top/bottom rows and skews a height measured from it.
    box_h = float(np.median([b.glyph_height for b in stable]))
    outline_w = float(np.median([b.outline_width for b in stable if b.outline_width])) \
        if any(b.outline_width for b in stable) else None

    scale_to_canonical = canonical_height / float(H)
    cap_h_canonical = box_h * scale_to_canonical
    font_size_ass = int(round(cap_h_canonical / (cap_height_em or DEFAULT_CAP_HEIGHT_EM)))
    font_size_ass = int(np.clip(font_size_ass, 24, 260))
    # honest error bar: the font face cannot be identified from pixels, and faces
    # differ in cap-height-per-em by roughly this much (Montserrat 0.48 vs
    # DejaVu Sans 0.68 were both measured on this renderer)
    em = cap_height_em or DEFAULT_CAP_HEIGHT_EM
    font_size_uncertainty = max(0.0, 1.0 - em / 0.68)

    # ---- colours -----------------------------------------------------------
    # Karaoke semantics decide this, not raw pixel share: at the start of a cue
    # every word is unspoken (base colour), by the end they are all spoken
    # (highlight colour). Counting pixels would call the highlight the base,
    # because spoken words accumulate.
    colors = _cluster_colors(stable)
    overall = colors[0][0] if colors else (255, 255, 255)
    base, highlight = _base_and_highlight(cues, overall)
    karaoke_enabled = highlight is not None
    # flash test: with karaoke, the accent colour appears in some frames of a cue
    # and not in others. Without karaoke every frame looks the same.
    flash_score = 0.0
    if highlight is not None:
        per_cue_changes = 0
        for cue in cues:
            seen = []
            for _, b in cue:
                d_base = np.abs(np.array(b.fill_bgr, float) - np.array(base, float)).sum()
                d_hl = np.abs(np.array(b.fill_bgr, float) - np.array(highlight, float)).sum()
                seen.append("base" if d_base <= d_hl else "hl")
            if len(set(seen)) > 1:
                per_cue_changes += 1
        flash_score = per_cue_changes / max(1, cue_count)
        if flash_score < 0.2:
            karaoke_enabled = False

    # ---- animation ---------------------------------------------------------
    animation = "none"
    anim_votes = {"pop": 0, "fade": 0, "none": 0}
    for cue in cues:
        if len(cue) < 3:
            continue
        first, _, steady = cue[0][1], cue[1][1], cue[len(cue) // 2][1]
        grow = (first.w * first.h) and (steady.w * steady.h) / max(1.0, first.w * first.h)
        if grow > 1.12:
            anim_votes["pop"] += 1
        else:
            first_bright = float(np.mean(first.fill_bgr))
            steady_bright = float(np.mean(steady.fill_bgr))
            if steady_bright - first_bright > 40 and first.fill_ratio < steady.fill_ratio * 0.8:
                anim_votes["fade"] += 1
            else:
                anim_votes["none"] += 1
    if anim_votes["pop"] >= max(2, 0.4 * cue_count):
        animation = "pop"
    elif anim_votes["fade"] >= max(2, 0.4 * cue_count):
        animation = "fade"

    # ---- text metrics ------------------------------------------------------
    if acc_words:
        counts = np.bincount(np.clip(np.asarray(acc_words), 0, 12))
        words_per_cue = int(np.argmax(counts))
    else:
        words_per_cue = int(np.median([max(b.n_words for _, b in c) for c in cues]))
    widths = [b.w for b in stable]
    median_widget_w = float(np.median(widths))
    # 0.55 em per character is a fair average for bold sans
    chars_per_line = int(round(median_widget_w / max(1.0, (font_size_ass / scale_to_canonical) * 0.48)))
    max_lines = 1
    if len(cues) >= 4:
        # a second line would show up as two bands stacked in the same cue frames
        stacked = 0
        for t in {round(t, 2) for t, _ in detections}:
            bands_t = [b for tt, b in detections if round(tt, 2) == t]
            ys = sorted(b.cy for b in bands_t)
            if len(ys) > 1 and (ys[-1] - ys[0]) < H * 0.13:
                stacked += 1
        if stacked >= max(2, 0.25 * len({round(t, 2) for t, _ in detections})):
            max_lines = 2

    # per-band casing vote wins: the accumulated mask is great for word counts
    # but alignment smear softens the row-ink profile that casing depends on.
    upper_lik = max(_upper_likelihood(stable), 0.85 * _cue_upper_likelihood(cues))
    casing = "upper" if upper_lik >= 0.62 else None
    if casing is None:
        # lowercase glyphs measure x-height rather than cap height, which reads
        # roughly a fifth small: keep the estimate but declare it less certain
        font_size_uncertainty += 0.2
    font_size_uncertainty = round(min(0.6, font_size_uncertainty), 2)

    # a text-only check on the *first* frame of the first cue: is the fill
    # darker than its outline? that flips primary/outline colours
    flip = float(np.mean(base)) < 110 and any(
        b.outline_bgr and float(np.mean(b.outline_bgr)) > 130 for b in stable)
    if flip:
        base, highlight = (highlight or (255, 255, 255)), base

    confidence = float(np.clip(
        0.35
        + 0.25 * min(1.0, cue_count / 6.0)
        + 0.20 * min(1.0, len(stable) / 40.0)
        + 0.20 * (1.0 if casing else 0.4),
        0.0, 0.95,
    ))

    return {
        "present": True,
        "font_family": None,           # cannot be identified from pixels (documented)
        "cap_height_ratio": round(cap_h_canonical / canonical_height, 4),
        "font_size_ass": font_size_ass,
        "font_size_uncertainty": font_size_uncertainty,
        "primary_color": _hex(base),
        "outline_color": _hex(stable[0].outline_bgr or (0, 0, 0)),
        "outline_width": int(round((outline_w or 3.0) * scale_to_canonical)),
        "casing": casing,
        "position": {
            "anchor": ("bottom_center" if cx < 0.45 else "bottom_center" if cx <= 0.55
                       else "bottom_center"),
            "cx": round(cx, 4),
            "cy": round(cy, 4),
        },
        "karaoke": {"enabled": bool(karaoke_enabled),
                    "highlight_color": _hex(highlight) if highlight else None,
                    "flash_score": round(flash_score, 3)},
        "animation": {"in": animation},
        "max_lines": max_lines,
        "max_words_per_cue": int(np.clip(words_per_cue, 1, 8)),
        "max_chars_per_line": int(np.clip(chars_per_line, 8, 60)),
        "confidence": round(confidence, 3),
        "evidence": {
            "cue_count": cue_count,
            "detection_frames": len(stable),
            "upper_likelihood": round(upper_lik, 3),
            "box_height_iqr": round(_iqr([b.h for b in stable]), 2),
            "sampled_frame": [int(W), int(H)],
            "frames": [],
        },
        "raw": {
            "cy_median": round(cy, 4), "cx_median": round(cx, 4),
            "cap_height_px_sampled": round(box_h, 2),
            "glyph_height_median_px": round(float(np.median([b.glyph_height for b in stable])), 2),
            "outline_width_px": round(outline_w, 2) if outline_w else None,
            "colors": [{"hex": _hex(c), "share": round(sh, 3)} for c, sh in colors[:4]],
            "anim_votes": anim_votes,
        },
    }


# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------


def draw_evidence(frame: SampledFrame, bands: list[Band]) -> np.ndarray:
    """Annotated copy of a frame: what the detector saw, with measurements."""
    canvas = frame.bgr.copy()
    H, W = canvas.shape[:2]
    for band in bands:
        cv2.rectangle(canvas, (band.x, band.y), (band.x + band.w, band.y + band.h),
                      (0, 255, 0), 2)
        label = (f"cap={band.glyph_height:.0f}px fill={band.fill_bgr[::-1]} "
                 f"words={band.n_words}")
        cv2.putText(canvas, label, (max(2, band.x), max(14, band.y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(canvas, label, (max(2, band.x), max(14, band.y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)
    cv2.line(canvas, (0, int(H * 0.5)), (W, int(H * 0.5)), (60, 60, 60), 1)
    return canvas


# ---------------------------------------------------------------------------
# self-calibration
# ---------------------------------------------------------------------------
CALIBRATION_TEXT = "HANDMADE"


def calibrate_cap_height(cache_dir, *, sampled_width: int = 480, font: str = "Montserrat",
                         font_size: int = 160, **cache_kwargs) -> float:
    """Measure how many em of *our own renderer* a caption line's glyph height is.

    The ratio between rendered cap-height and requested font size depends on the
    font face (unidentifiable from pixels), on libass, on the encoder and on the
    sampling resolution the extractor uses. Rather than hard-code a constant
    that silently drifts, render one line through the same pipeline the captions
    stage uses and measure it. Cached, because it costs about a second.
    """
    from .. import config
    from ..captions.ass import write_ass
    from ..captions.cues import group_words
    from ..asr.base import Word
    from ..ffmpeg import ffmpeg_exe
    from ..util import jsonio, log
    from .frames import sample_video

    cache_dir = Path(cache_dir) if cache_dir else None
    cache_file = cache_dir / "calibration.json" if cache_dir else None
    key = f"{font}|{font_size}|{sampled_width}"
    if cache_file and cache_file.exists():
        cached = (jsonio.load(cache_file, {}) or {}).get(key)
        if isinstance(cached, (int, float)) and 0.05 < float(cached) < 1.5:
            return float(cached)

    workdir = Path(cache_dir or config.WORK / "_calibration")
    workdir.mkdir(parents=True, exist_ok=True)
    style = config.deep_merge(config.DEFAULT_STYLE, {
        "captions": {"font_family": font, "font_size_ass": font_size, "casing": "upper",
                     "karaoke": {"enabled": False}, "animation": {"in": "none"},
                     "outline_width": 0, "max_lines": 1}})
    words = [Word(text=token, start=i * 0.45, end=i * 0.45 + 0.4, source="calibration")
             for i, token in enumerate(CALIBRATION_TEXT.split())]
    cues = group_words(words, max_words=len(words), max_chars=40, max_lines=1, gap_break=9)
    ass_path = workdir / "calibration.ass"
    write_ass(ass_path, cues, style, width=1080, height=1920, autofit=False)
    clip = workdir / "calibration.mp4"
    proc = subprocess.run([
        ffmpeg_exe(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x101010:s=1080x1920:d=1",
        "-vf", subtitles_filter(ass_path),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-t", "1", str(clip)], capture_output=True, text=True)
    if proc.returncode != 0:
        log.warn("calibration render failed, using the built-in constant",
                 err=proc.stderr.strip()[-160:])
        return DEFAULT_CAP_HEIGHT_EM

    frames = list(sample_video(str(clip), fps=2, width=sampled_width))
    if not frames:
        return DEFAULT_CAP_HEIGHT_EM
    frame = frames[0]
    bands = detect_bands(frame.bgr, region=(0.25, 0.98), max_bands=1)
    if not bands:
        log.warn("calibration line not detected, using the built-in constant")
        return DEFAULT_CAP_HEIGHT_EM
    band = bands[0]
    ratio = (band.glyph_height / frame.gray.shape[0]) * 1920.0 / float(font_size)
    value = float(np.clip(ratio, 0.05, 1.5))
    if cache_file:
        data = jsonio.load(cache_file, {}) or {}
        data[key] = round(value, 4)
        jsonio.save(cache_file, data)
    log.info("renderer calibrated", cap_height_em=round(value, 4), sampled_width=sampled_width,
             font=font)
    return value

"""Streaming, non-semantic visual candidates from every supplied RGB frame.

No frame decoder, screenshot scheduler, OCR, UI recognition, or global image
deduplication lives here. A candidate says only that pixels changed. Images are
kept at bounded resolution; output contains timestamps, never image payloads.
Callers must feed every decoded frame with its actual, strictly increasing time.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import heapq
import math
from typing import Mapping

import numpy as np


class _TimeSpreadBuffer:
    """Bounded streaming samples: thin the densest time neighborhoods first.

    The first and latest observed endpoints survive. This is pixel navigation,
    not semantic selection. Parent dictionaries share only retained payloads.
    Lazy heap entries are periodically rebuilt to keep memory O(limit).
    """

    def __init__(self, limit, on_omit):
        self.limit, self.on_omit = limit, on_omit
        self.entries, self.heap = {}, []
        self.head = self.tail = None
        self.serial = 0

    def _score(self, key):
        if key is None or key not in self.entries:
            return
        item = self.entries[key]
        item['version'] += 1
        left, right = item['left'], item['right']
        if left is not None and right is not None:
            span = self.entries[right]['row']['end'] - self.entries[left]['row']['end']
            heapq.heappush(self.heap, (span, key, item['version']))

    def add(self, row, parent):
        self.serial += 1
        key = self.serial
        parent[key] = row
        self.entries[key] = dict(row=row, parent=parent, left=self.tail, right=None, version=0)
        previous = self.tail
        if previous is None:
            self.head = key
        else:
            self.entries[previous]['right'] = key
        self.tail = key
        self._score(previous)
        if len(self.entries) > self.limit:
            while self.heap:
                _, victim, version = heapq.heappop(self.heap)
                if victim in self.entries and self.entries[victim]['version'] == version:
                    self.remove(victim)
                    break
        self._bound_heap()

    def remove(self, key):
        item = self.entries.pop(key)
        left, right = item['left'], item['right']
        item['parent'].pop(key)
        if left is None:
            self.head = right
        else:
            self.entries[left]['right'] = right
        if right is None:
            self.tail = left
        else:
            self.entries[right]['left'] = left
        self._score(left)
        self._score(right)
        self.on_omit(item['row'])
        self._bound_heap()

    def _bound_heap(self):
        if len(self.heap) > 4 * self.limit:
            self.heap.clear()
            for key in self.entries:
                self._score(key)


@dataclass(frozen=True)
class VisualChangeConfig:
    max_dimension: int = 192
    grid_rows: int = 8
    grid_cols: int = 12
    pixel_noise: float = 3.0 / 255.0
    global_threshold: float = 0.022
    local_threshold: float = 0.075
    quiet_factor: float = 0.25
    settle_seconds: float = 0.25
    motion_seconds: float = 0.65
    transient_seconds: float = 1.5
    motion_tile_fraction: float = 0.25
    local_stability_seconds: float = 0.4
    local_quiet_threshold: float = 0.004
    local_onset_threshold: float = 0.06
    max_nodes: int = 4000

    def __post_init__(self):
        for name, minimum in (("max_dimension", 16), ("grid_rows", 1),
                              ("grid_cols", 1), ("max_nodes", 2)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        for name in ("pixel_noise", "global_threshold", "local_threshold",
                     "quiet_factor", "motion_tile_fraction", "local_quiet_threshold", "local_onset_threshold"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError(f"{name} must be finite and in (0, 1]")
        for name in ("settle_seconds", "motion_seconds", "transient_seconds", "local_stability_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


class VisualChangeDetector:
    """Feed uint8 RGB arrays; finish returns JSON-compatible nodes and stats.

    Duplicate/backward/non-finite timestamps are rejected before state changes.
    This avoids manufacturing a fixed frame rate or assigning two different
    pictures the same extraction timestamp. Config accepts a dataclass or dict.
    A node limit affects the index only: subsequent supplied frames are still
    analyzed, omissions are reported, and one slot is reserved for tail context.
    """

    def __init__(self, config=None):
        if config is None:
            config = VisualChangeConfig()
        elif isinstance(config, Mapping):
            config = VisualChangeConfig(**config)
        if not isinstance(config, VisualChangeConfig):
            raise TypeError("config must be VisualChangeConfig, a mapping, or None")
        self.config = config
        self._nodes = []
        self._count = 0
        self._previous = None
        self._first_time = self._time = None
        self._shape = None
        self._active = None
        self._result = None
        self._omitted = 0
        self._omitted_span = None
        self._candidate_count = 0
        self._motion_count = 0
        self._motion_frame_count = 0
        self._local_count = 0
        self._weak_count = 0
        self._weak_omitted = 0
        self._weak_buffer = _TimeSpreadBuffer(config.max_nodes, self._omit_weak)
        self._omission_bins = {}
        self._omission_bin_seconds = 30.0
        self._last_motion_time = None
        self._pending_local = None
        self._coalesced_local = 0

    def feed(self, timestamp: float, rgb: np.ndarray) -> None:
        if self._result is not None:
            raise RuntimeError("cannot feed after finish")
        timestamp = self._valid_time(timestamp, "timestamp")
        if self._time is not None and timestamp <= self._time:
            raise ValueError("frame timestamps must be strictly increasing")
        frame = self._prepare(rgb)
        if self._shape is not None and frame.shape != self._shape:
            raise ValueError("analysis frame shape changed within the stream")
        if self._previous is None:
            self._initialize(timestamp, frame)
            return

        adjacent = self._difference(frame, self._previous)
        reference = self._difference(frame, self._reference)
        self._track_cell_stability(timestamp, frame, adjacent)
        if self._active is None and (adjacent["score"] >= 1 or reference["score"] >= 1):
            self._append_context(self._idle_start, self._time, self._idle_frame, self._time)
            self._active = {
                "before": self._time, "onset": timestamp, "peak_time": timestamp,
                "peak_score": 0.0, "last_signal": timestamp, "signals": 0,
                "frames": 0, "regions": np.zeros_like(reference["tiles"], dtype=bool),
                "metrics": self._empty_metrics(), "quiet_since": None, "quiet_image": None,
                "motion_observations": {}, "weak_observation_count": 0,
            }
        if self._active is not None:
            self._record_event(timestamp, adjacent, reference)
            self._emit_local_change(timestamp, frame, adjacent)
            # Compare to a quiet-period anchor as well as the adjacent frame:
            # slow fades must not look settled solely because each step is small.
            active = self._active
            if self._is_quiet(adjacent):
                if active["quiet_since"] is None:
                    active["quiet_since"] = timestamp
                    active["quiet_image"] = frame.copy()
                elif not self._is_quiet(self._difference(frame, active["quiet_image"])):
                    active["quiet_since"] = timestamp
                    active["quiet_image"] = frame.copy()
                elif timestamp - active["quiet_since"] >= self.config.settle_seconds:
                    self._close_event(timestamp, frame, reference)
            else:
                active["quiet_since"] = None
                active["quiet_image"] = None
        self._flush_local(timestamp)
        self._previous = frame
        self._time = timestamp
        self._count += 1

    def finish(self, end_time: float) -> dict:
        end_time = self._valid_time(end_time, "end_time")
        if self._result is not None:
            if end_time != self._result["stats"]["requested_end_time"]:
                raise ValueError("finish was already called with a different end_time")
            return deepcopy(self._result)
        if self._time is not None and end_time < self._time:
            raise ValueError("end_time precedes the final supplied frame")
        if self._previous is not None:
            if self._active is not None:
                self._close_event(self._time, self._previous)
            self._append_context(self._idle_start, end_time, self._idle_frame,
                                 self._time, tail=True)
        self._nodes.sort(key=lambda node: (node["start"], node["end"]))
        for number, node in enumerate(self._nodes, 1):
            node["id"] = f"visual-{number:05d}"
            if 'motion_observations' in node:
                node['motion_observations'] = list(node['motion_observations'].values())
                node['omitted_weak_observations'] = (node['weak_observation_count'] -
                                                     len(node['motion_observations']))
        retained_weak = sum(len(node.get("motion_observations", [])) for node in self._nodes)
        omitted_weak = self._weak_count - retained_weak
        stats = {
            "candidate_only": True,
            "frames_analyzed": self._count,
            "first_frame_time": self._first_time,
            "last_frame_time": self._time,
            "requested_end_time": end_time,
            "analysis_width": self._shape[1] if self._shape else None,
            "analysis_height": self._shape[0] if self._shape else None,
            "candidate_nodes": self._candidate_count,
            "returned_nodes": len(self._nodes),
            "node_limit": self.config.max_nodes,
            "truncated": bool(self._omitted or omitted_weak),
            "omitted_nodes": self._omitted,
            "omitted_time_range": self._omitted_span,
            "omission_bins": [self._omission_bins[k] for k in sorted(self._omission_bins)],
            "omission_bin_seconds": self._omission_bin_seconds,
            "omission_bin_basis": "omitted observation end; each row is a time envelope, not continuous loss",
            "node_index_complete": not bool(self._omitted or omitted_weak),
            "all_supplied_frames_analyzed": True,
            "motion_episodes": self._motion_count,
            "frames_aggregated_in_motion": self._motion_frame_count,
            "local_candidates_during_motion": self._local_count,
            "local_grid_observations_coalesced": self._coalesced_local,
            "weak_motion_observations": self._weak_count,
            "retained_weak_motion_observations": retained_weak,
            "omitted_weak_motion_observations": omitted_weak,
            "motion_observation_index_complete": not bool(omitted_weak),
            "weak_retention_policy": "time_spread_smallest_neighbor_span_v1",
            "local_evidence_policy": "strict_stable_regions_get_nodes; weaker_pixels_stay_in_motion_observations",
            "coalescing": "continuous_pixel_activity_into_motion_intervals",
            "coverage_basis": "supplied_frames_only; no claim about decoder omissions",
            "config": asdict(self.config),
        }
        self._result = {"nodes": self._nodes, "stats": stats}
        return deepcopy(self._result)

    @staticmethod
    def _valid_time(value, name):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite nonnegative number")
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative number")
        return value

    def _prepare(self, rgb):
        if (not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3
                or rgb.dtype != np.uint8 or min(rgb.shape[:2]) < 1):
            raise ValueError("rgb must be a nonempty uint8 array shaped [height, width, 3]")
        frame = rgb.astype(np.float32) / 255.0
        height, width = frame.shape[:2]
        scale = min(1.0, self.config.max_dimension / max(height, width))
        if scale < 1.0:
            # Area bins include every input pixel; point sampling would erase
            # small bright/dark details depending on their alignment.
            out_h, out_w = max(1, round(height * scale)), max(1, round(width * scale))
            ys = np.linspace(0, height, out_h + 1, dtype=int)
            xs = np.linspace(0, width, out_w + 1, dtype=int)
            frame = np.add.reduceat(np.add.reduceat(frame, ys[:-1], axis=0),
                                    xs[:-1], axis=1)
            frame /= (np.diff(ys)[:, None] * np.diff(xs)[None, :])[:, :, None]
        return frame

    def _initialize(self, timestamp, frame):
        self._shape = frame.shape
        height, width = frame.shape[:2]
        self._ys = np.linspace(0, height, min(height, self.config.grid_rows) + 1, dtype=int)
        self._xs = np.linspace(0, width, min(width, self.config.grid_cols) + 1, dtype=int)
        self._areas = np.diff(self._ys)[:, None] * np.diff(self._xs)[None, :]
        self._first_time = self._time = timestamp
        self._previous = frame
        self._reference = frame.copy()
        self._local_reference = frame.copy()
        self._weak_reference = frame.copy()
        self._cell_quiet_image = frame.copy()
        self._cell_since = np.full(self._areas.shape, timestamp, dtype=float)
        self._cell_before = self._cell_since.copy()
        self._strict_image = frame.copy()
        self._strict_since = self._cell_since.copy()
        self._strict_before = self._cell_since.copy()
        self._recent_jump = np.zeros_like(self._cell_since)
        self._strict_onset_jump = np.zeros_like(self._cell_since)
        self._idle_start = self._idle_frame = timestamp
        self._count = 1

    def _pixel_difference(self, current, reference):
        return np.maximum(np.abs(current - reference).mean(axis=2)
                          - self.config.pixel_noise, 0)

    def _tile_means(self, pixels):
        return np.add.reduceat(np.add.reduceat(pixels, self._ys[:-1], axis=0),
                               self._xs[:-1], axis=1) / self._areas

    def _difference(self, current, reference):
        pixels = self._pixel_difference(current, reference)
        tiles = self._tile_means(pixels)
        global_score, local_score = float(pixels.mean()), float(tiles.max())
        return {
            "global": global_score, "local": local_score, "tiles": tiles,
            "fraction": float((pixels >= self.config.local_threshold / 2).mean()),
            "score": max(global_score / self.config.global_threshold,
                         local_score / self.config.local_threshold),
        }

    def _is_quiet(self, difference):
        return difference["score"] < self.config.quiet_factor

    @staticmethod
    def _empty_metrics():
        return dict(adjacent_global=0.0, adjacent_local=0.0, reference_global=0.0,
                    reference_local=0.0, changed_fraction=0.0, peak_score=0.0,
                    moving_tile_fraction=0.0)

    def _moving_fraction(self, adjacent):
        return float((adjacent["tiles"] >=
                      self.config.local_threshold * self.config.quiet_factor).mean())

    def _record_event(self, timestamp, adjacent, reference):
        active = self._active
        active["frames"] += 1
        if not self._is_quiet(adjacent):
            active["signals"] += 1
            active["last_signal"] = timestamp
        score = reference["score"]
        if score > active["peak_score"]:
            active["peak_score"] = score
            active["peak_time"] = timestamp
        values = dict(adjacent_global=adjacent["global"], adjacent_local=adjacent["local"],
                      reference_global=reference["global"], reference_local=reference["local"],
                      changed_fraction=max(adjacent["fraction"], reference["fraction"]),
                      peak_score=max(adjacent["score"], reference["score"]),
                      moving_tile_fraction=self._moving_fraction(adjacent))
        for name, value in values.items():
            active["metrics"][name] = max(active["metrics"][name], value)
        for difference in (adjacent, reference):
            threshold = (self.config.global_threshold if difference["global"] >=
                         self.config.global_threshold else self.config.local_threshold)
            active["regions"] |= difference["tiles"] >= threshold

    def _track_cell_stability(self, timestamp, frame, adjacent):
        self._recent_jump = np.maximum(adjacent["tiles"],
                                       self._recent_jump * math.exp(-(timestamp - self._time) / 0.2))
        tiles = self._tile_means(self._pixel_difference(frame, self._cell_quiet_image))
        changed = tiles >= self.config.local_threshold * self.config.quiet_factor
        self._cell_since[changed] = timestamp
        self._cell_before[changed] = self._time
        self._copy_tiles(self._cell_quiet_image, frame, changed)
        strict_tiles = self._tile_means(self._pixel_difference(frame, self._strict_image))
        changed = strict_tiles >= self.config.local_quiet_threshold
        self._strict_since[changed] = timestamp
        self._strict_before[changed] = self._time
        self._strict_onset_jump[changed] = self._recent_jump[changed]
        self._copy_tiles(self._strict_image, frame, changed)

    def _copy_tiles(self, destination, source, mask):
        for row, col in np.argwhere(mask):
            ys, xs = slice(self._ys[row], self._ys[row + 1]), slice(self._xs[col], self._xs[col + 1])
            destination[ys, xs] = source[ys, xs]

    def _emit_local_change(self, timestamp, frame, adjacent):
        if self._active["signals"] < 3:
            return
        moving_now = self._moving_fraction(adjacent) >= self.config.motion_tile_fraction
        if moving_now:
            self._last_motion_time = timestamp
        recent_motion = (self._last_motion_time is not None and
                         timestamp - self._last_motion_time <= self.config.local_stability_seconds)
        if not recent_motion:
            return
        # Preserve the original, more permissive observations in the motion
        # index. They do not each demand a screenshot or masquerade as a UI step.
        if moving_now:
            weak = timestamp - self._cell_since >= self.config.settle_seconds
            if weak.any():
                weak_reference = self._difference(frame, self._weak_reference)
                weak &= weak_reference["tiles"] >= self.config.local_threshold
                if weak.any() and weak.mean() <= 0.65:
                    observation = self._local_node(timestamp, adjacent, weak_reference, weak,
                                                   self._cell_before, self._cell_since)
                    observation["reason"] = "weak_local_stability_during_motion"
                    observation["image_priority"] = "low"
                    self._weak_count += 1
                    self._active['weak_observation_count'] += 1
                    observation['observation_ordinal'] = self._active['weak_observation_count']
                    self._weak_buffer.add(observation, self._active['motion_observations'])
                    self._copy_tiles(self._weak_reference, frame, weak)
        duration = timestamp - self._strict_since
        mature = duration >= self.config.local_stability_seconds
        # Only new stability qualifies. A quiet patch from several seconds ago
        # must not become a new local event when the camera starts moving again.
        newly_mature = self._time - self._strict_since < self.config.local_stability_seconds
        changed = (mature & newly_mature &
                   (self._strict_onset_jump >= self.config.local_onset_threshold))
        if not changed.any():
            return
        reference = self._difference(frame, self._local_reference)
        changed &= reference["tiles"] >= self.config.local_threshold
        if not changed.any() or changed.mean() > 0.65:
            return
        node = self._local_node(timestamp, adjacent, reference, changed,
                                self._strict_before, self._strict_since)
        node["image_priority"] = "normal"
        node["evidence_strength"] = "strict_local_pixel_stability"
        node["metrics"]["local_stable_seconds"] = float(duration[changed].min())
        node["metrics"]["onset_local_jump"] = float(self._strict_onset_jump[changed].max())
        self._queue_local(node, changed)
        self._copy_tiles(self._local_reference, frame, changed)

    def _queue_local(self, node, mask):
        pending = self._pending_local
        if pending is not None:
            previous, previous_mask = pending
            overlap = int((mask & previous_mask).sum()) / max(1, min(int(mask.sum()), int(previous_mask.sum())))
            close_onset = abs(node["start"] - previous["start"]) <= 0.3
            # Neighboring grid cells of one screen transition settle on slightly
            # different frames. Merge those observations, not repeated changes
            # to the same cells, so A -> B -> A remains representable.
            if close_onset and overlap <= 0.2 and node["end"] - previous["end"] <= 0.2:
                previous["start"] = min(previous["start"], node["start"])
                previous["end"] = node["end"]
                previous["frames"][0]["time"] = previous["start"]
                if node["metrics"]["reference_local"] > previous["metrics"]["reference_local"]:
                    previous["frames"][1] = node["frames"][1]
                previous["frames"][-1] = node["frames"][-1]
                for key, value in node["metrics"].items():
                    previous["metrics"][key] = max(previous["metrics"].get(key, 0), value)
                previous_mask |= mask
                previous["changed_regions"] = self._regions(previous_mask)
                previous["coalesced_local_observations"] += 1
                self._coalesced_local += 1
                return
            self._flush_local(node["end"], force=True)
        node["coalesced_local_observations"] = 1
        self._pending_local = (node, mask.copy())

    def _flush_local(self, timestamp, force=False):
        if self._pending_local is None:
            return
        node, _ = self._pending_local
        if force or timestamp - node["end"] > 0.2:
            self._append_node(node)
            self._local_count += 1
            self._pending_local = None

    def _local_node(self, timestamp, adjacent, reference, changed, before_times, since_times):
        before = float(before_times[changed].min())
        representative = float(since_times[changed].max())
        metrics = self._empty_metrics()
        metrics.update(adjacent_global=adjacent["global"], adjacent_local=adjacent["local"],
                       reference_global=reference["global"],
                       reference_local=float(reference["tiles"][changed].max()),
                       changed_fraction=reference["fraction"], peak_score=reference["score"],
                       moving_tile_fraction=self._moving_fraction(adjacent))
        return {
            "start": before, "end": timestamp, "kind": "change",
            "frames": [{"time": before, "role": "before"},
                       {"time": representative, "role": "representative"},
                       {"time": timestamp, "role": "after"}],
            "metrics": metrics, "changed_regions": self._regions(changed),
            "reason": "locally_stable_pixels_changed_while_other_regions_keep_moving",
        }

    def _close_event(self, timestamp, frame, reference=None):
        self._flush_local(timestamp, force=True)
        active = self._active
        if reference is None:
            reference = self._difference(frame, self._reference)
        returned = reference["score"] < 0.55
        if returned and active["last_signal"] - active["before"] <= self.config.transient_seconds:
            kind, reason = "transient", "brief_pixel_change_returned_near_its_prior_reference"
        elif (active["signals"] >= 3 and active["last_signal"] - active["onset"] >=
              self.config.motion_seconds):
            kind, reason = "motion", "continuous_pixel_activity_aggregated_into_one_interval"
            self._motion_count += 1
            self._motion_frame_count += active["frames"]
        else:
            kind, reason = "change", "adjacent_or_accumulated_reference_pixel_change"
        self._append_node({
            "start": active["before"], "end": timestamp, "kind": kind,
            "frames": [{"time": active["before"], "role": "before"},
                       {"time": active["peak_time"],
                        "role": "peak" if kind == "transient" else "representative"},
                       {"time": timestamp, "role": "after"}],
            "metrics": active["metrics"], "changed_regions": self._regions(active["regions"]),
            "reason": reason,
            "motion_observations": active["motion_observations"],
            "weak_observation_count": active['weak_observation_count'],
            "image_priority": "low" if kind == "motion" else "normal",
        })
        self._active = None
        self._reference = frame.copy()
        self._local_reference = frame.copy()
        self._weak_reference = frame.copy()
        self._cell_quiet_image = frame.copy()
        self._cell_since.fill(timestamp)
        self._cell_before.fill(timestamp)
        self._strict_image = frame.copy()
        self._strict_since.fill(timestamp)
        self._strict_before.fill(timestamp)
        self._recent_jump.fill(0)
        self._strict_onset_jump.fill(0)
        self._last_motion_time = None
        self._idle_start = self._idle_frame = timestamp

    def _append_context(self, start, end, representative, last, tail=False):
        self._append_node({
            "start": start, "end": end, "kind": "context",
            "frames": [{"time": representative, "role": "representative"},
                       {"time": last, "role": "after"}],
            "metrics": self._empty_metrics(), "changed_regions": [],
            "reason": "observed_context_below_change_threshold_or_stream_boundary",
            "image_priority": "normal" if tail or start == self._first_time else "low",
        }, tail=tail)

    def _append_node(self, node, tail=False):
        self._candidate_count += 1
        limit = self.config.max_nodes if tail else self.config.max_nodes - 1
        if len(self._nodes) < limit:
            self._nodes.append(node)
        else:
            self._omitted += 1
            self._record_omitted_span(node)
            # A dropped parent cannot expose its children. Release their slots
            # and account for them once, in addition to the parent omission.
            for key in list(node.get('motion_observations', {})):
                self._weak_buffer.remove(key)

    def _omit_weak(self, node):
        self._weak_omitted += 1
        self._record_omitted_span(node, weak=True)

    def _record_omitted_span(self, node, weak=False):
        if self._omitted_span is None:
            self._omitted_span = [node["start"], node["end"]]
        else:
            self._omitted_span[0] = min(self._omitted_span[0], node["start"])
            self._omitted_span[1] = max(self._omitted_span[1], node["end"])
        key = int(node['end'] // self._omission_bin_seconds)
        row = dict(start=node['start'], end=node['end'],
                   major_nodes=int(not weak), weak_observations=int(weak))
        self._merge_omission_bin(self._omission_bins, key, row)
        while len(self._omission_bins) > 128:
            merged = {}
            for key, row in self._omission_bins.items():
                self._merge_omission_bin(merged, key // 2, row)
            self._omission_bins = merged
            self._omission_bin_seconds *= 2

    @staticmethod
    def _merge_omission_bin(bins, key, row):
        if key not in bins:
            bins[key] = dict(row)
        else:
            old = bins[key]
            old['start'] = min(old['start'], row['start'])
            old['end'] = max(old['end'], row['end'])
            for count in ('major_nodes', 'weak_observations'):
                old[count] += row[count]

    def _regions(self, mask):
        """Connected grid cells become approximate normalized bounding boxes."""
        pending = set(map(tuple, np.argwhere(mask).tolist()))
        regions = []
        while pending:
            seed = min(pending)
            pending.remove(seed)
            component, stack = [seed], [seed]
            while stack:
                row, col = stack.pop()
                for item in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                    if item in pending:
                        pending.remove(item)
                        component.append(item)
                        stack.append(item)
            rows, cols = zip(*component)
            height, width = self._shape[:2]
            x, y = int(self._xs[min(cols)]), int(self._ys[min(rows)])
            right, bottom = int(self._xs[max(cols) + 1]), int(self._ys[max(rows) + 1])
            regions.append(dict(x=x / width, y=y / height,
                                width=(right - x) / width, height=(bottom - y) / height))
        return regions

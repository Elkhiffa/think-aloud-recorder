"""Synthetic pixel sequences test mechanics, not general UI recognition accuracy."""
import json
import unittest

import numpy as np

from visual_change import VisualChangeConfig, VisualChangeDetector, _TimeSpreadBuffer


def plain(value=24, height=96, width=192):
    return np.full((height, width, 3), value, dtype=np.uint8)


def run(sequence, end=None, **config):
    detector = VisualChangeDetector(config)
    for timestamp, frame in sequence:
        detector.feed(timestamp, frame)
    result = detector.finish(end if end is not None else sequence[-1][0])
    return result


def events(result):
    return [node for node in result["nodes"] if node["kind"] != "context"]


class VisualChangeTests(unittest.TestCase):
    def assert_observed_times(self, result, sequence):
        observed = {timestamp for timestamp, _ in sequence}
        for node in result["nodes"]:
            self.assertLessEqual(node["start"], node["end"])
            for frame in node["frames"]:
                self.assertIn(frame["time"], observed)
                self.assertIn(frame["role"], ("before", "representative", "after", "peak"))

    def test_single_frame_small_popup_uses_local_signal_and_retains_peak(self):
        base = plain()
        popup = base.copy()
        popup[32:40, 70:78] = 235  # 0.35% of the frame, much less than a global cut.
        sequence = [(0.0, base), (0.991, base), (1.003, popup),
                    (1.014, base), (1.052, base), (1.4, base)]
        result = run(sequence)
        self.assertEqual(len(events(result)), 1)
        node = events(result)[0]
        self.assertEqual(node["kind"], "transient")
        self.assertIn({"time": 1.003, "role": "peak"}, node["frames"])
        self.assertLess(node["metrics"]["reference_global"], 0.022)
        self.assertGreater(node["metrics"]["reference_local"], 0.075)
        self.assertTrue(node["changed_regions"])
        self.assert_observed_times(result, sequence)

    def test_a_b_a_returns_are_not_globally_deduplicated(self):
        a, b = plain(20), plain(180)
        sequence = [(0, a), (0.1, a), (1.0, b), (1.1, b), (1.5, b),
                    (2.0, b), (3.0, a), (3.1, a), (3.5, a)]
        result = run(sequence)
        self.assertEqual([node["kind"] for node in events(result)], ["change", "change"])
        self.assertIn(3.0, [frame["time"] for node in events(result) for frame in node["frames"]])
        self.assertEqual(result["nodes"][0]["kind"], "context")
        self.assertEqual(result["nodes"][-1]["kind"], "context")
        self.assert_observed_times(result, sequence)

    def test_accumulated_fade_is_detected_when_each_adjacent_step_is_too_small(self):
        sequence = [(index / 30, plain(20 + index)) for index in range(90)]
        sequence += [(3.1, plain(109)), (3.5, plain(109))]
        result = run(sequence)
        self.assertTrue(events(result))
        self.assertLessEqual(len(events(result)), 2)
        strongest = max(events(result), key=lambda node: node["metrics"]["reference_global"])
        self.assertGreater(strongest["metrics"]["reference_global"], 0.20)
        self.assertLess(strongest["metrics"]["adjacent_global"], 0.022)
        self.assert_observed_times(result, sequence)

    def test_locally_stable_panel_is_retained_during_continuous_background_activity(self):
        sequence = []
        for index in range(60):
            frame = plain(30 if index % 2 else 90)
            if index >= 10:
                frame[24:60, 64:112] = 225
            sequence.append((index * 0.1, frame))
        result = run(sequence)
        local = [node for node in events(result) if "locally_stable" in node["reason"]]
        self.assertTrue(local)
        self.assertTrue(any(node["kind"] == "motion" for node in events(result)))
        self.assertLessEqual(len(events(result)), 3)
        self.assertTrue(any(frame["time"] == 1.0 for node in local for frame in node["frames"]))
        self.assertTrue(any(region["width"] < 1 and region["height"] < 1
                            for node in local for region in node["changed_regions"]))
        self.assert_observed_times(result, sequence)

    def test_strict_local_candidate_does_not_require_current_motion_or_weak_maturity(self):
        for stop_motion, settle_seconds in ((True, 0.25), (False, 0.8)):
            with self.subTest(stop_motion=stop_motion, settle_seconds=settle_seconds):
                sequence = []
                for index in range(20):
                    moving = not stop_motion or index < 7
                    frame = plain(30 if moving and index % 2 else 90)
                    if index >= 3:
                        frame[24:60, 64:112] = 225
                    sequence.append((index * 0.1, frame))
                result = run(sequence, settle_seconds=settle_seconds)
                local = [node for node in events(result) if "locally_stable" in node["reason"]]
                self.assertEqual(len(local), 1)
                self.assertEqual(local[0]["frames"], [
                    {"time": sequence[2][0], "role": "before"},
                    {"time": sequence[3][0], "role": "representative"},
                    {"time": sequence[7][0], "role": "after"},
                ])
                self.assertEqual(local[0]["metrics"]["moving_tile_fraction"] == 0, stop_motion)
                self.assertEqual(result["stats"]["weak_motion_observations"], 1)
                self.assert_observed_times(result, sequence)

    def test_repeated_local_changes_update_weak_and_strict_references_independently(self):
        sequence = []
        for index in range(20):
            frame = plain(30 if index % 2 else 90)
            if index >= 3:
                frame[24:60, 64:112] = 225 if index < 10 else 10
            sequence.append((index * 0.1, frame))
        result = run(sequence)
        local = [node for node in events(result) if "locally_stable" in node["reason"]]
        weak = [observation for node in events(result)
                for observation in node.get("motion_observations", [])]
        self.assertEqual(len(local), 2)
        self.assertEqual(len(weak), 2)
        self.assertEqual([node["end"] for node in local], [sequence[7][0], sequence[14][0]])
        self.assertEqual([node["end"] for node in weak], [sequence[6][0], sequence[13][0]])
        for observations in (local, weak):
            self.assertEqual([node["frames"][1]["time"] for node in observations],
                             [sequence[3][0], sequence[10][0]])
            self.assertAlmostEqual(observations[0]["metrics"]["reference_local"],
                                   (225 - 90 - 3) / 255, places=6)
            self.assertAlmostEqual(observations[1]["metrics"]["reference_local"],
                                   (225 - 10 - 3) / 255, places=6)
        self.assertEqual(result["stats"]["local_candidates_during_motion"], 2)
        self.assertEqual(result["stats"]["weak_motion_observations"], 2)
        self.assert_observed_times(result, sequence)

    def test_fresh_high_amplitude_noise_aggregates_instead_of_exploding_node_count(self):
        rng = np.random.default_rng(738)
        sequence = [(index / 29.97, rng.integers(0, 256, size=(96, 192, 3), dtype=np.uint8))
                    for index in range(180)]
        result = run(sequence)
        self.assertEqual([node["kind"] for node in events(result)], ["motion"])
        self.assertEqual(result["stats"]["frames_analyzed"], 180)
        self.assertGreater(result["stats"]["frames_aggregated_in_motion"], 170)
        self.assertFalse(result["stats"]["truncated"])

    def test_slow_dark_local_motion_is_indexed_as_weak_instead_of_primary_screenshots(self):
        sequence = []
        for index in range(70):
            frame = plain(30 if index % 2 else 90)
            frame[24:60, 64:112] = 20 + index * 2
            sequence.append((index * .1, frame))
        result = run(sequence)
        self.assertEqual(result["stats"]["local_candidates_during_motion"], 0)
        self.assertGreater(result["stats"]["weak_motion_observations"], 0)
        motion = [node for node in result["nodes"] if node["kind"] == "motion"]
        self.assertEqual(len(motion), 1)
        self.assertEqual(motion[0]["image_priority"], "low")
        self.assertTrue(motion[0]["motion_observations"])
        for observation in motion[0]["motion_observations"]:
            self.assertEqual(observation["image_priority"], "low")
            self.assert_observed_times({"nodes": [observation]}, sequence)

    def test_neighboring_cells_settling_at_different_times_form_one_local_node(self):
        sequence = []
        for index in range(25):
            frame = plain(30 if index % 2 else 90)
            if index >= 4:
                frame[24:36, 64:80] = 225
            if index >= 5:
                frame[24:36, 80:96] = 225
            sequence.append((index * .1, frame))
        result = run(sequence)
        local = [node for node in result["nodes"] if "locally_stable" in node["reason"]]
        self.assertEqual(len(local), 1)
        self.assertGreater(local[0]["coalesced_local_observations"], 1)
        self.assertGreater(result["stats"]["local_grid_observations_coalesced"], 0)
        self.assertEqual(local[0]["image_priority"], "normal")
        self.assert_observed_times(result, sequence)

    def test_short_high_contrast_popup_peak_survives_stricter_motion_local_gate(self):
        sequence = []
        for index in range(25):
            frame = plain(30 if index % 2 else 90)
            frame[24:36, 64:80] = 20
            if index == 5:
                frame[24:36, 64:80] = 250
            sequence.append((index * .1, frame))
        result = run(sequence)
        self.assertIn(.5, [frame["time"] for node in result["nodes"] for frame in node["frames"]])
        self.assert_observed_times(result, sequence)

    def test_weak_observation_budget_is_reported_and_does_not_stop_frame_analysis(self):
        sequence = []
        for index in range(100):
            frame = plain(30 if index % 2 else 90)
            frame[24:60, 64:112] = 20 + index * 2
            sequence.append((index * .1, frame))
        result = run(sequence, max_nodes=3)
        stats = result["stats"]
        self.assertLessEqual(len(result["nodes"]), 3)
        self.assertLessEqual(stats["retained_weak_motion_observations"], 3)
        self.assertGreater(stats["omitted_weak_motion_observations"], 0)
        self.assertFalse(stats["motion_observation_index_complete"])
        self.assertFalse(stats["node_index_complete"])
        self.assertTrue(stats["truncated"])
        self.assertIsNotNone(stats["omitted_time_range"])
        self.assertEqual(stats["frames_analyzed"], len(sequence))

        weak = [row for node in result['nodes'] for row in node.get('motion_observations', [])]
        unlimited = run(sequence)
        all_weak = [row for node in unlimited['nodes'] for row in node.get('motion_observations', [])]
        self.assertEqual(weak[0]['end'], all_weak[0]['end'])
        self.assertEqual(weak[-1]['end'], all_weak[-1]['end'])
        self.assertGreater(weak[-1]['observation_ordinal'], len(weak))
        bins = stats['omission_bins']
        self.assertEqual(sum(b['weak_observations'] for b in bins), stats['omitted_weak_motion_observations'])
        self.assertEqual(sum(b['major_nodes'] for b in bins), stats['omitted_nodes'])

    def test_temporal_buffer_spreads_bursts_and_keeps_sparse_later_observations(self):
        omitted, parents = [], [{}, {}]
        buffer = _TimeSpreadBuffer(40, omitted.append)
        times = [i / 100 for i in range(1000)] + [20 + i * 5 for i in range(30)]
        for i, at in enumerate(times):
            buffer.add(dict(start=at-.001, end=at, observation_ordinal=i+1), parents[i >= 1000])
            self.assertLessEqual(len(buffer.entries), 40)
            self.assertLessEqual(len(buffer.heap), 160)
        retained = [row['end'] for parent in parents for row in parent.values()]
        self.assertEqual(len(retained), 40)
        self.assertEqual(len(omitted), len(times)-40)
        self.assertIn(times[0], retained)
        self.assertIn(times[-1], retained)
        self.assertGreaterEqual(len(parents[1]), 28)
        self.assertTrue(all(any(left <= t < left+40 for t in retained) for left in (0,40,80,120)))
        for key in list(parents[0]):
            buffer.remove(key)
        self.assertFalse(parents[0])
        buffer.add(dict(start=180, end=180), parents[1])
        self.assertEqual(len(buffer.entries), len(parents[1]))

    def test_omission_accounting_stays_bounded_with_dropped_parents(self):
        detector = VisualChangeDetector(dict(max_nodes=2))
        detector.feed(0, plain())
        parent = {}
        for i in range(1000):
            detector._weak_count += 1
            detector._weak_buffer.add(dict(start=i*60, end=i*60+1), parent)
        # The initial context consumes the non-tail slot; this parent is lost.
        detector._append_context(0, 0, 0, 0)
        detector._append_node(dict(start=0, end=60000, motion_observations=parent))
        self.assertFalse(parent)
        self.assertFalse(detector._weak_buffer.entries)
        result = detector.finish(60001)
        stats = result['stats']
        self.assertEqual(stats['omitted_weak_motion_observations'], 1000)
        self.assertEqual(sum(b['weak_observations'] for b in stats['omission_bins']), 1000)
        self.assertEqual(sum(b['major_nodes'] for b in stats['omission_bins']), stats['omitted_nodes'])
        self.assertLessEqual(len(stats['omission_bins']), 128)
        self.assertEqual(stats['omitted_time_range'], [0, 60000])

    def test_small_sensor_noise_stays_below_threshold(self):
        rng = np.random.default_rng(91)
        sequence = [(index / 25, rng.integers(98, 103, size=(72, 120, 3), dtype=np.uint8))
                    for index in range(90)]
        result = run(sequence)
        self.assertEqual(events(result), [])
        self.assertEqual(len(result["nodes"]), 1)

    def test_vfr_uses_actual_times_and_quiet_duration_not_frame_count(self):
        a, b = plain(10), plain(160)
        sequence = [(7.021, a), (7.5, a), (7.503, b), (7.51, b),
                    (7.513, b), (8.101, b), (12.72, b)]
        result = run(sequence, end=13.5)
        self.assertEqual(len(events(result)), 1)
        node = events(result)[0]
        self.assertEqual(node["start"], 7.5)
        self.assertEqual(node["end"], 8.101)
        self.assertEqual(node["frames"][1]["time"], 7.503)
        self.assertEqual(result["stats"]["first_frame_time"], 7.021)
        self.assertEqual(result["nodes"][-1]["end"], 13.5)
        self.assert_observed_times(result, sequence)

    def test_delayed_next_frame_does_not_turn_short_transient_into_long_motion(self):
        a, b = plain(10), plain(100)
        sequence = [(0.0, a), (0.05, b), (0.08, a), (0.09, a), (20.0, a)]
        result = run(sequence)
        self.assertEqual(events(result)[0]["kind"], "transient")
        self.assertIn({"time": 0.05, "role": "peak"}, events(result)[0]["frames"])

    def test_same_pixels_at_different_frame_rates_retain_real_durations(self):
        for times in ([0.0, 0.1, 0.13, 0.6, 1.4], [0.0, 0.1, 0.2, 0.21, 0.6, 1.4]):
            sequence = [(time, plain(20 if time < 0.1 else 170)) for time in times]
            result = run(sequence)
            node = events(result)[0]
            self.assertEqual(node["kind"], "change")
            self.assertEqual(node["start"], 0.0)
            self.assertEqual(node["end"], 0.6)
            self.assert_observed_times(result, sequence)

    def test_empty_and_single_frame_inputs_have_honest_context(self):
        empty = VisualChangeDetector().finish(6.0)
        self.assertEqual(empty["nodes"], [])
        self.assertEqual(empty["stats"]["frames_analyzed"], 0)
        self.assertIsNone(empty["stats"]["first_frame_time"])
        single = run([(2.5, plain())], end=4.0)
        self.assertEqual(len(single["nodes"]), 1)
        self.assertEqual(single["nodes"][0]["kind"], "context")
        self.assertEqual(single["nodes"][0]["start"], 2.5)
        self.assertEqual(single["nodes"][0]["end"], 4.0)
        self.assertEqual({frame["time"] for frame in single["nodes"][0]["frames"]}, {2.5})

    def test_static_clip_context_includes_first_and_last_supplied_frames(self):
        result = run([(0.3, plain()), (1.9, plain()), (9.7, plain())], end=10)
        self.assertEqual(events(result), [])
        self.assertEqual(result["nodes"][0]["frames"],
                         [{"time": 0.3, "role": "representative"}, {"time": 9.7, "role": "after"}])

    def test_duplicate_backwards_and_nonfinite_times_rejected_without_mutation(self):
        detector = VisualChangeDetector()
        detector.feed(0.5, plain())
        for invalid in (0.5, 0.49, -1, float("nan"), float("inf"), True):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                detector.feed(invalid, plain(220))
        detector.feed(0.6, plain())
        with self.assertRaises(ValueError):
            detector.finish(0.59)
        result = detector.finish(0.6)
        self.assertEqual(result["stats"]["frames_analyzed"], 2)
        self.assertEqual(events(result), [])

    def test_finish_is_idempotent_and_defensive(self):
        detector = VisualChangeDetector()
        detector.feed(0, plain())
        result = detector.finish(1)
        result["nodes"].clear()
        self.assertEqual(len(detector.finish(1)["nodes"]), 1)
        with self.assertRaises(ValueError):
            detector.finish(2)
        with self.assertRaises(RuntimeError):
            detector.feed(2, plain())

    def test_unsettled_event_uses_final_pixels_when_finished(self):
        for returned, kind in ((True, "transient"), (False, "change")):
            with self.subTest(returned=returned):
                sequence = [(0.0, plain(20)), (0.1, plain(180)),
                            (0.2, plain(20 if returned else 180))]
                result = run(sequence, end=0.4)
                self.assertEqual(len(events(result)), 1)
                node = events(result)[0]
                self.assertEqual(node["kind"], kind)
                self.assertEqual(node["end"], 0.2)
                self.assertEqual(node["frames"][1], {
                    "time": 0.1, "role": "peak" if returned else "representative",
                })
                self.assertEqual(result["stats"]["frames_analyzed"], 3)
                self.assertEqual(result["nodes"][-1]["end"], 0.4)
                self.assert_observed_times(result, sequence)

    def test_node_cap_reports_omissions_but_continues_analyzing_and_retains_tail(self):
        sequence = [(0.0, plain(10))]
        for index in range(1, 15):
            value = 150 if index % 2 else 10
            sequence.extend([(float(index), plain(value)), (index + 0.1, plain(value)),
                             (index + 0.5, plain(value))])
        result = run(sequence, end=15, max_nodes=5)
        stats = result["stats"]
        self.assertEqual(len(result["nodes"]), 5)
        self.assertTrue(stats["truncated"])
        self.assertGreater(stats["omitted_nodes"], 0)
        self.assertIsNotNone(stats["omitted_time_range"])
        self.assertFalse(stats["node_index_complete"])
        self.assertEqual(stats["frames_analyzed"], len(sequence))
        self.assertEqual(stats["candidate_nodes"], stats["returned_nodes"] + stats["omitted_nodes"])
        self.assertEqual(result["nodes"][-1]["end"], 15)
        self.assertEqual(result["nodes"][-1]["kind"], "context")

    def test_area_downsampling_and_changed_regions_remain_bounded_and_serializable(self):
        a, b = plain(20, 360, 640), plain(20, 360, 640)
        b[100:150, 300:340] = 230
        sequence = [(0.0, a), (0.1, b), (0.4, b), (0.8, b)]
        result = run(sequence)
        self.assertEqual(result["stats"]["analysis_width"], 192)
        self.assertEqual(result["stats"]["analysis_height"], 108)
        self.assertTrue(events(result))
        for node in events(result):
            for region in node["changed_regions"]:
                self.assertGreater(region["width"], 0)
                self.assertGreater(region["height"], 0)
                self.assertGreaterEqual(region["x"], 0)
                self.assertGreaterEqual(region["y"], 0)
                self.assertLessEqual(region["x"] + region["width"], 1)
                self.assertLessEqual(region["y"] + region["height"], 1)
        json.dumps(result, allow_nan=False)

    def test_invalid_images_and_config_are_rejected(self):
        for value in ([], np.zeros((0, 3, 3), dtype=np.uint8),
                      np.zeros((10, 10), dtype=np.uint8), np.zeros((10, 10, 3))):
            with self.assertRaises(ValueError):
                VisualChangeDetector().feed(0, value)
        for config in ({"max_nodes": 1}, {"global_threshold": 0},
                       {"settle_seconds": float("nan")}, {"max_dimension": True}):
            with self.assertRaises(ValueError):
                VisualChangeDetector(config)
        with self.assertRaises(TypeError):
            VisualChangeDetector({"unknown_setting": 12})
        self.assertEqual(VisualChangeDetector(VisualChangeConfig()).config.max_dimension, 192)

    def test_no_claim_to_detect_below_resolution_or_below_threshold_details(self):
        a, b = plain(20), plain(20)
        b[50, 50] = 25
        result = run([(0, a), (0.01, b), (0.02, a), (1.0, a)])
        self.assertEqual(events(result), [])
        self.assertTrue(result["stats"]["candidate_only"])
        self.assertIn("supplied_frames_only", result["stats"]["coverage_basis"])


if __name__ == "__main__":
    unittest.main()

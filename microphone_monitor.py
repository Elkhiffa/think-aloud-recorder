"""Read-only OBS level observer for the isolated narration source.

No microphone is opened here and no samples, history or credentials are saved.
OBS inputLevelsMul channels contain magnitude, output peak, and input peak;
only the output peak is used. Desktop/game audio must never light this meter.
"""
import math
import threading
import time

import obsws_python as obs

STALE_SECONDS = 2.5
QUIET_SECONDS = 15
SOUND_DB = -55


class MicrophoneLevels:
    def __init__(self, source='口述', clock=time.monotonic):
        self.source = source
        self.clock = clock
        self.lock = threading.RLock()
        self.started = clock()
        self.packet_at = None
        self.sample_at = None
        self.sound_at = None
        self.loud_at = None
        self.db = -100.0
        self.muted = None
        self.track = None
        self.mute_revision = 0
        self.track_revision = 0

    def on_input_volume_meters(self, event):
        inputs = getattr(event, 'inputs', None)
        if not isinstance(inputs, list):
            return
        now = self.clock()
        with self.lock:
            self.packet_at = now
            item = next((i for i in inputs if isinstance(i, dict)
                         and i.get('inputName') == self.source), None)
            channels = item.get('inputLevelsMul', []) if item else []
            peaks = []
            if isinstance(channels, list):
                for channel in channels:
                    if not isinstance(channel, list) or len(channel) < 2:
                        continue
                    value = channel[1]
                    if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                        peaks.append(value)
            if not peaks:
                self.sample_at = None
                self.db = -100.0
                return
            peak = max(peaks)
            db = max(-100.0, min(0.0, 20 * math.log10(peak))) if peak > 0 else -100.0
            # Fast attack, short decay: a spoken syllable survives a UI refresh.
            previous = self.db - 45 * (now - self.sample_at) if self.sample_at is not None else -100
            self.db = max(db, previous)
            self.sample_at = now
            if self.muted is False and self.track is True:
                if db >= SOUND_DB:
                    self.sound_at = now
                if db >= -1:
                    self.loud_at = now

    def on_input_mute_state_changed(self, event):
        if getattr(event, 'input_name', None) != self.source:
            return
        value = getattr(event, 'input_muted', None)
        if type(value) is bool:
            with self.lock:
                self.muted = value
                self.mute_revision += 1
                self.sound_at = self.loud_at = None
                self.db = -100.0

    def on_input_audio_tracks_changed(self, event):
        if getattr(event, 'input_name', None) != self.source:
            return
        tracks = getattr(event, 'input_audio_tracks', None)
        if isinstance(tracks, dict) and type(tracks.get('2')) is bool:
            with self.lock:
                self.track = tracks['2']
                self.track_revision += 1
                self.sound_at = self.loud_at = None

    def on_input_removed(self, event):
        if getattr(event, 'input_name', None) == self.source:
            with self.lock:
                self.sample_at = None
                self.sound_at = self.loud_at = None
                self.db = -100.0

    def snapshot(self, connected=True):
        now = self.clock()
        with self.lock:
            result = dict(state='unavailable', level=0, db=None, quiet_seconds=0)
            if not connected or (self.packet_at is not None and now - self.packet_at > STALE_SECONDS):
                return result
            if self.packet_at is None:
                if now - self.started < STALE_SECONDS:
                    result['state'] = 'connecting'
                return result
            if self.track is False:
                result['state'] = 'unrouted'
                return result
            if self.muted is True:
                result['state'] = 'muted'
                return result
            if (self.muted is not False or self.track is not True or self.sample_at is None
                    or now - self.sample_at > STALE_SECONDS):
                return result
            quiet = max(0, now - (self.sound_at if self.sound_at is not None else self.started))
            db = max(-100, self.db - 45 * (now - self.sample_at))
            state = 'silent' if quiet >= QUIET_SECONDS else 'quiet'
            if self.sound_at is not None and quiet < 1:
                state = 'signal'
            if self.loud_at is not None and now - self.loud_at < .8:
                state = 'loud'
            return dict(state=state, level=round(max(0, min(1, (db + 60) / 60)), 3),
                        db=round(db, 1), quiet_seconds=int(quiet))


class MicrophoneMonitor:
    def __init__(self, request, source='口述'):
        base = request.base_client
        if base.host not in ('127.0.0.1', 'localhost') or type(base.port) is not int:
            raise ValueError('A local OBS endpoint is required')
        self.levels = MicrophoneLevels(source)
        self.client = None
        try:
            self.client = obs.EventClient(host=base.host, port=base.port, password=base.password,
                                          timeout=2, subs=(1 << 16) | 8)
            self.client.callback.register([self.levels.on_input_volume_meters,
                self.levels.on_input_mute_state_changed, self.levels.on_input_audio_tracks_changed,
                self.levels.on_input_removed])
            # Register first. Do not overwrite a newer event with a request that
            # was in flight when the user changed mute or track routing.
            mute_revision, track_revision = self.levels.mute_revision, self.levels.track_revision
            muted = request.get_input_mute(source).input_muted
            tracks = request.get_input_audio_tracks(source).input_audio_tracks
            with self.levels.lock:
                if self.levels.mute_revision == mute_revision and type(muted) is bool:
                    self.levels.muted = muted
                if self.levels.track_revision == track_revision and isinstance(tracks, dict):
                    self.levels.track = tracks.get('2') if type(tracks.get('2')) is bool else None
        except Exception:
            self.close()
            raise

    def healthy(self):
        client = self.client
        if client is None or not client.worker.is_alive():
            return False
        with self.levels.lock:
            stamp = self.levels.packet_at
            return self.levels.clock() - (stamp if stamp is not None else self.levels.started) < STALE_SECONDS

    def snapshot(self):
        client = self.client
        return self.levels.snapshot(connected=client is not None and client.worker.is_alive())

    def close(self):
        client, self.client = self.client, None
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

"""Auditable recorder recommendation; speaker IDs only identify this transcript."""
import bisect
import hashlib
import json
import math
from pathlib import Path


def valid_speaker(value):
    return type(value) is int and 0 <= value < 1000


def transcript_id(segments):
    rows = [(s['start'], s['end'], s.get('text', ''), s.get('speaker_id')) for s in segments]
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _merge(ranges):
    merged = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return merged


def _speaker_ranges(segments):
    ranges = {}
    for segment in segments:
        ident = segment.get('speaker_id')
        if not valid_speaker(ident):
            continue
        words = segment.get('words') or [segment]
        for word in words:
            start, end = word.get('start'), word.get('end')
            if (type(start) in (int, float) and type(end) in (int, float)
                    and math.isfinite(start) and math.isfinite(end)
                    and segment['start'] <= start < end <= segment['end']):
                ranges.setdefault(ident, []).append((start, end))
    return {ident: _merge(items) for ident, items in ranges.items()}


def _solo_ranges(ranges):
    """Do not attribute a mixed/overlapping voice's level to either person."""
    events = {}
    for ident, spans in ranges.items():
        for start, end in spans:
            events.setdefault(start, []).append((ident, 1))
            events.setdefault(end, []).append((ident, -1))
    active, result, previous = set(), [], 0
    for time, changes in sorted(events.items()):
        if len(active) == 1 and time > previous:
            result.append((previous, time, next(iter(active))))
        for ident, change in changes:
            if change > 0:
                active.add(ident)
            else:
                active.discard(ident)
        previous = time
    return result


def _levels(audio, ranges):
    """One bounded-memory decode, duration-weighted median RMS (not peak volume)."""
    import av
    import numpy as np
    spans = _solo_ranges(ranges)
    ends = [s[1] for s in spans]
    histograms = {ident: {} for ident in ranges}
    measured = {ident: 0.0 for ident in ranges}
    with av.open(str(audio)) as media:
        if len(media.streams.audio) != 1 or len(media.streams.audio[0].layout.channels) != 1:
            raise ValueError('Speaker levels require the independent mono microphone track')
        clock = 0.0
        for frame in media.decode(audio=0):
            start = float(frame.time) if frame.time is not None else clock
            rate = frame.sample_rate
            end = start + frame.samples / rate
            clock = end
            raw = frame.to_ndarray().reshape(-1)
            samples = raw.astype(np.float64)
            if np.issubdtype(raw.dtype, np.integer):
                samples /= max(abs(np.iinfo(raw.dtype).min), np.iinfo(raw.dtype).max)
            index = bisect.bisect_right(ends, start)
            while index < len(spans) and spans[index][0] < end:
                left, right, ident = spans[index]
                a = max(0, int(round((max(start, left) - start) * rate)))
                b = min(len(samples), int(round((min(end, right) - start) * rate)))
                if b > a:
                    power = float(np.mean(samples[a:b] ** 2))
                    # Quantized, time-weighted histogram stays bounded for hours of audio.
                    level = round(max(-96, min(0, 10 * math.log10(max(power, 1e-12)))) * 2) / 2
                    seconds = (b - a) / rate
                    histograms[ident][level] = histograms[ident].get(level, 0) + seconds
                    measured[ident] += seconds
                index += 1
    result = {}
    for ident, histogram in histograms.items():
        total = measured[ident]
        level, accumulated = None, 0
        for value, weight in sorted(histogram.items()):
            accumulated += weight
            if accumulated >= total / 2:
                level = value
                break
        result[ident] = (level, round(total, 3))
    return result


def analyze_speakers(audio, segments):
    ranges = _speaker_ranges(segments)
    result = dict(version=1, transcript_id=transcript_id(segments), speakers=[],
                  suggested_id=None, confidence='uncertain', method='duration_75_median_rms_25_v1')
    if not ranges:
        result['reason'] = 'no_speaker_ids'
        return result
    try:
        levels = _levels(audio, ranges)
    except Exception:
        # A secondary measurement must never discard a successful transcription.
        levels = {}
    total = sum(sum(end-start for start, end in spans) for spans in ranges.values())
    for ident, spans in sorted(ranges.items()):
        seconds = sum(end-start for start, end in spans)
        level, measured = levels.get(ident, (None, 0))
        example = next(s for s in segments if s.get('speaker_id') == ident and s['end'] > s['start'])
        result['speakers'].append(dict(speaker_id=ident, speech_seconds=round(seconds, 3),
            speech_share=round(seconds/total, 5) if total else 0, median_dbfs=level,
            measured_seconds=measured, sample_start=example['start'], sample_end=min(example['end'], example['start']+8)))
    usable = [s for s in result['speakers'] if s['median_dbfs'] is not None and s['median_dbfs'] > -70
              and s['measured_seconds'] >= min(2, s['speech_seconds']*.5)]
    if not usable:
        result['reason'] = 'insufficient_audio'
        return result
    loudest = max(s['median_dbfs'] for s in usable)
    for speaker in result['speakers']:
        level = speaker['median_dbfs']
        volume = max(0, 1-(loudest-level)/12) if speaker in usable else 0
        speaker['score'] = round(.75*speaker['speech_share']+.25*volume, 5)
    ordered = sorted(usable, key=lambda s: (-s['score'], -s['speech_seconds'], s['speaker_id']))
    first = ordered[0]
    # This is a heuristic recommendation, never an identity or microphone-distance claim.
    margin = first['score'] - ordered[1]['score'] if len(ordered) > 1 else first['score']
    if first['speech_seconds'] < 2:
        result['reason'] = 'too_little_speech'
    else:
        result['suggested_id'] = first['speaker_id']
        result['confidence'] = 'recommended' if margin >= .12 and first['speech_share'] >= .5 else 'uncertain'
        result['reason'] = 'duration_and_level' if result['confidence'] == 'recommended' else 'ambiguous_speakers'
    return result


def speaker_payload(folder, meta, segments):
    """Expose only measurements matching these exact words, times and speaker IDs."""
    identity = transcript_id(segments)
    ids = sorted({s['speaker_id'] for s in segments if valid_speaker(s.get('speaker_id'))})
    if not ids:
        return dict(available=False, transcript_id=identity, speakers=[], selected_id=None)
    try:
        folder = Path(folder).resolve()
        file = (folder/'录像.whisper.json').resolve()
        if file.parent != folder:
            raise ValueError('Transcript path escape')
        analysis = json.loads(file.read_text(encoding='utf-8')).get('speaker_analysis') or {}
        if analysis.get('transcript_id') != identity or analysis.get('version') != 1:
            analysis = {}
    except (OSError, ValueError, AttributeError, TypeError):
        analysis = {}
    rows = []
    sources = analysis.get('speakers')
    if not isinstance(sources, list):
        sources = []
    for ident in ids:
        source = next((s for s in sources if isinstance(s, dict) and s.get('speaker_id') == ident), {})
        example = next(s for s in segments if s.get('speaker_id') == ident)
        row = dict(speaker_id=ident, sample_start=example['start'], sample_end=min(example['end'], example['start']+8))
        for field in ('speech_seconds', 'speech_share', 'median_dbfs', 'measured_seconds', 'score'):
            value = source.get(field)
            row[field] = value if type(value) in (int, float) and math.isfinite(value) else None
        rows.append(row)
    suggested = analysis.get('suggested_id')
    if not valid_speaker(suggested) or suggested not in ids:
        suggested = None
    selection = meta.get('recorder_speaker') or {}
    manual = (isinstance(selection, dict) and selection.get('transcript_id') == identity
              and (selection.get('speaker_id') is None or
                   valid_speaker(selection.get('speaker_id')) and selection['speaker_id'] in ids))
    return dict(available=True, transcript_id=identity, speakers=rows, suggested_id=suggested,
                selected_id=selection.get('speaker_id') if manual else suggested,
                source='manual' if manual else 'auto',
                confidence=analysis.get('confidence') if analysis.get('confidence') in ('recommended', 'uncertain') else 'uncertain',
                reason=analysis.get('reason') if analysis.get('reason') in ('duration_and_level', 'ambiguous_speakers', 'insufficient_audio', 'too_little_speech') else 'unmeasured')

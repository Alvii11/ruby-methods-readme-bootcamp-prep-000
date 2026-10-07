#!/usr/bin/env python3
"""Objective audio and caption checks on final.mp4 (run in the build folder after `build.py final`).

  python3 qa.py [media]   -> loudness, peaks, longest pauses, caption sync/coverage against a fresh transcript
  (media defaults to final.mp4; an audio-only extract works too. Reuses qa_words.json if present.)

Not a substitute for listening: it can't judge delivery, pronunciation or a music mix.
"""
import json, os, re, subprocess, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else 'final.mp4'
FPS_TOL = 0.25   # caption start may lead/lag its first spoken word by this much


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def loudness():
    err = run(f'ffmpeg -nostats -i {SRC} -vn -af ebur128=peak=true -f null -').stderr
    tail = err[err.rfind('Summary:'):]
    g = lambda k: re.search(k + r':\s+(-?[\d.]+)', tail)
    return {'integrated_lufs': float(g('I').group(1)), 'lra_lu': float(g('LRA').group(1)),
            'true_peak_dbfs': float(g('Peak').group(1))}


def pauses(min_len=1.2):
    err = run(f'ffmpeg -nostats -i {SRC} -vn -af silencedetect=n=-42dB:d={min_len} -f null -').stderr
    st = [float(x) for x in re.findall(r'silence_start: (-?[\d.]+)', err)]
    en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', err)]
    return sorted(((round(b - a, 2), round(a, 1)) for a, b in zip(st, en)), reverse=True)


def ass_t(s):
    h, m, x = s.split(':')
    return int(h) * 3600 + int(m) * 60 + float(x)


def captions():
    caps = []
    for l in open('gd.ass'):
        if l.startswith('Dialogue') and ',Cap,' in l:
            f = l.rstrip('\n').split(',', 9)
            caps.append((ass_t(f[1]), ass_t(f[2]), f[9]))
    return caps


def transcript():
    if os.path.exists('qa_words.json'):
        return json.load(open('qa_words.json'))
    from faster_whisper import WhisperModel
    run(f'ffmpeg -v error -y -i {SRC} -vn -ac 1 -ar 16000 qa.wav')
    m = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=8)
    segs, _ = m.transcribe('qa.wav', word_timestamps=True)
    words = [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]
    json.dump(words, open('qa_words.json', 'w'))
    return words


def norm(w):
    return re.sub(r'[^a-z0-9]', '', w.lower())


def main():
    out = {'loudness': loudness(), 'longest_pauses_s_at': pauses()[:8]}
    caps, words = captions(), transcript()
    # coverage: share of spoken words whose midpoint falls inside some caption
    covered = sum(any(a <= (s + e) / 2 <= b for a, b, _ in caps) for s, e, _ in words)
    # sync: each caption's start against the transcript time of its first word
    lags, worst = [], []
    for a, b, txt in caps:
        first = norm(txt.split()[0])
        near = [s for s, e, w in words if norm(w) == first and abs(s - a) < 2.0]
        if near:
            d = a - min(near, key=lambda s: abs(s - a))
            lags.append(d)
            if abs(d) > FPS_TOL:
                worst.append((round(d, 2), round(a, 1), txt[:50]))
    short = [(round(b - a, 2), round(a, 1), t[:40]) for a, b, t in caps if b - a < 0.7]
    out['captions'] = {'count': len(caps), 'word_coverage_pct': round(100 * covered / max(len(words), 1), 1),
                       'matched': len(lags), 'median_lag_s': round(sorted(lags)[len(lags) // 2], 3) if lags else None,
                       'off_by_more_than_%.2fs' % FPS_TOL: sorted(worst, key=lambda x: -abs(x[0]))[:10],
                       'shorter_than_0.7s': short[:10]}
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()

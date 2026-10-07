#!/usr/bin/env python3
"""Rough-cut builder for "Fiction's Greatest Destroyers, Ranked".

Runs in the Higgsfield sandbox (ffmpeg + libass + faster-whisper).
  python3 build.py narr    -> narr.mp3 + timing.json (pause-trimmed narration from section takes)
  python3 build.py shots   -> base.mp4   (all shots, 1920x1080, 24 fps, no audio)
  python3 build.py words   -> words.json (word timestamps of the narration)
  python3 build.py final   -> final.mp4  (base + burned titles/labels/captions + narration)
"""
import difflib, json, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor

W, H, FPS = 1920, 1080, 24
RAW = 'https://raw.githubusercontent.com/Alvii11/ruby-methods-readme-bootcamp-prep-000/claude/fiction-deadliest-characters-dwwkbk/fiction-deadliest/'
CF = 'https://d8j0ntlcm91z4.cloudfront.net/user_3FINxGcP7afZzLRaKypSj3jzAYA/hf_'
NARR = 'https://d2ol7oe51mr4n9.cloudfront.net/user_3FINxGcP7afZzLRaKypSj3jzAYA/884901dc-9aca-4d01-bdac-01db9270fbe2.mp3'
FONTS = '/usr/share/fonts/truetype/higgsfield'
# Section starts (s) from the narration timing file; section 0 is pulled back to 0.
STARTS = [0.0, 61.72, 108.63, 162.89, 218.76, 277.38, 326.3, 377.14, 433.42, 483.64, 539.25, 605.65, 659.84]

ASSETS = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets.json')))
CLIPS, IMGS = ASSETS['clips'], ASSETS['imgs']


def c(k, dur=None, off=0.0, **kw):
    return dict(t='clip', k=k, dur=dur, off=off, **kw)


def i(k, **kw):
    return dict(t='img', k=k, dur=None, **kw)


def T(rank, name, sub):
    return dict(title=(rank, name, sub))


def L(text):
    return dict(label=text)


def BIG(a, b):
    return dict(big=(a, b))


PLAN = [
    # 0 Opening
    [c('01', 5.0, **BIG("FICTION'S GREATEST DESTROYERS", 'RANKED')), i('101'),
     c('03', 1.8, 1.5), c('05', 1.8, 1.5), c('04', 1.8, 1.5), c('10', 1.8, 1.5), c('11', 1.8, 1.5), c('15', 1.8, 1.5),
     i('102', **L('ANIME · BOOKS · GAMES · COMICS')), i('02', **L('RANKED BY DEMONSTRATED DESTRUCTIVE SCALE')),
     i('103', **L('MAJOR SPOILERS AHEAD'))],
    # 1 #10 Eren
    [c('03', 5.0, **T('#10', 'EREN YEAGER', 'Attack on Titan  ·  individual')), i('111'),
     i('112', **L("80% OF HIS WORLD'S HUMANITY")), i('113', **L('THE PLANET ITSELF REMAINS')), i('03')],
    # 2 #9 AM
    [c('05', 5.0, **T('#9', 'AM', 'I Have No Mouth, and I Must Scream  ·  individual AI')), i('121', **L('ALL HUMANITY EXCEPT FIVE')),
     i('06', **L('KEPT ALIVE TO BE TORMENTED')), i('122'), i('123')],
    # 3 #8 Frieza
    [c('09', 5.0, **T('#8', 'FRIEZA', 'Dragon Ball  ·  individual')), i('131', **L('PLANET VEGETA DESTROYED')),
     i('132', **L('EARTH DESTROYED  ·  LATER REVERSED')), i('133', **L('WORLDS SOLD ARE NOT ALL WORLDS DESTROYED')), i('09b')],
    # 4 #7 Paul
    [c('04', 5.0, **T('#7', 'PAUL ATREIDES', 'Dune Messiah  ·  leader')), i('141', **L('61 BILLION DEAD  ·  INDIRECT')),
     i('143'), i('142', **L('PLACEMENT VS FRIEZA: EDITORIAL')), i('04b')],
    # 5 #6 Tyranids
    [c('13', 5.0, **T('#6', 'THE TYRANIDS', 'Warhammer 40,000  ·  collective')), i('151', **L('WORLDS STRIPPED OF LIFE  ·  TOTAL UNKNOWN')),
     i('152', **L('PLACEMENT: EDITORIAL')), i('13')],
    # 6 #5 Reapers
    [c('11', 5.0, **T('#5', 'THE REAPERS', 'Mass Effect  ·  collective')), i('161', **L('RECURRING GALACTIC HARVESTS')),
     i('162', **L('TOTAL UNKNOWN  ·  PLACEMENT: EDITORIAL')), i('11')],
    # 7 #4 Galactus
    [c('10', 5.0, **T('#4', 'GALACTUS', 'Marvel Comics  ·  individual')), i('172', **L('WORLDS CONSUMED  ·  TOTAL UNKNOWN')),
     i('171', **L('PLACEMENT: EDITORIAL')), i('173'), i('10')],
    # 8 #3 Thanos
    [c('14', 5.0, **T('#3', 'THANOS', 'Infinity Gauntlet comics  ·  individual')), i('181', **L('HALF OF ALL LIFE IN THE UNIVERSE')),
     i('182', **L('A PROPORTION, NOT A CENSUS  ·  LATER REVERSED')), i('14')],
    # 9 #2 Zeno
    [c('15', 5.0, **T('#2', 'ZENO', 'Dragon Ball Super  ·  individual')), i('191', **L('A FUTURE TIMELINE ERASED')),
     i('192', **L('RANKED ON REACH, NOT A HIGHER BODY COUNT')), i('15b')],
    # 10 #1 Anti-Monitor
    [c('16', 5.0, **T('#1', 'ANTI-MONITOR', 'Crisis on Infinite Earths  ·  individual')), i('201', **L('INFINITE MULTIVERSE DEVASTATED')),
     i('202'), i('203', **L('LATER RESTORED')), i('16b')],
    # 11 Bonus
    [c('07', 5.0, **T('BONUS', 'THE QU', 'All Tomorrows  ·  species')), i('08', **L('A SPECIES REMADE  ·  NO RELIABLE DEATH TOTAL')),
     c('17', 5.0, **T('', 'THE CRIMSON KING', 'The Dark Tower')), i('17', **L('A GOAL, NOT A COMPLETED KILL')),
     c('18', 5.0, **T('', 'PENNYWISE', 'It')), i('18', **L('COSMIC ORIGIN, LOCAL VICTIMS')),
     i('103', **L('POWER  ·  CRUELTY  ·  CASUALTIES'))],
    # 12 Verdict
    [i('211', **T('', 'THE VERDICT', '')), i('16b', **L('DESTRUCTIVE REACH: ANTI-MONITOR')),
     i('04b', **L('LARGEST STATED TOLL: PAUL ATREIDES  ·  61 BILLION')), i('05', **L('CRUELTY (INDIVIDUAL): AM')),
     i('08', **L('CRUELTY (SPECIES): THE QU')), c('11', 2.5, 1.0), c('10', 2.5, 1.0), c('09', 2.5, 1.0),
     c('20', 5.0, **BIG('WHO DID WE MISS?', 'BlavkMist Explores'))],
]

CROP = {'211': 0.80}  # keep this fraction of the height (baked-in letterbox bars)

ZOOMS = [('in', 0, 0), ('out', 0, 0), ('in', 0.6, 0), ('in', -0.6, 0), ('out', 0.5, 0.3), ('in', 0, -0.5)]


def sh(cmd):
    subprocess.run(cmd, shell=True, check=True)


def fetch(url, path):
    if not os.path.exists(path):
        urllib.request.urlretrieve(url, path)
    return path


def narration_len():
    fetch(NARR, 'narr.mp3')
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', 'narr.mp3'],
                         capture_output=True, text=True).stdout
    return float(out)


def timeline():
    total = narration_len()
    starts = STARTS
    if os.path.exists('timing.json'):
        starts = json.load(open('timing.json'))['starts']
        starts = [0.0] + starts[1:]
    ends = starts[1:] + [total]
    shots = []
    for sec, (s, e) in enumerate(zip(starts, ends)):
        plan = PLAN[sec]
        fixed = sum(x['dur'] for x in plan if x['dur'])
        nimg = sum(1 for x in plan if x['dur'] is None)
        each = (e - s - fixed) / nimg
        t = s
        for j, x in enumerate(plan):
            d = x['dur'] if x['dur'] else each
            shots.append(dict(x, sec=sec, start=t, end=t + d, first=j == 0, last=j == len(plan) - 1))
            t += d
    # frame-exact boundaries
    for n, x in enumerate(shots):
        x['f0'], x['f1'] = round(x['start'] * FPS), round(x['end'] * FPS)
        x['n'] = n
    return shots, total


def render(x):
    out = f'shots/{x["n"]:03d}.mp4'
    if os.path.exists(out):
        return out
    nf = x['f1'] - x['f0']
    dur = nf / FPS
    fades = []
    if x['first']:
        fades.append('fade=t=in:st=0:d=0.35')
    if x['last']:
        fades.append(f'fade=t=out:st={max(dur - 0.35, 0):.3f}:d=0.35')
    tail = (',' + ','.join(fades)) if fades else ''
    enc = f'-an -c:v libx264 -preset veryfast -crf 17 -pix_fmt yuv420p -r {FPS} -frames:v {nf}'
    if x['t'] == 'clip':
        src = f'src/c{x["k"]}.mp4'
        vf = (f'scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,'
              f'tpad=stop_mode=clone:stop_duration=10{tail}')
        sh(f'ffmpeg -v error -y -ss {x["off"]} -i {src} -vf "{vf}" {enc} {out}')
    else:
        src = f'src/i{x["k"]}.png'
        mode, px, py = ZOOMS[x['n'] % len(ZOOMS)]
        z = f'1+0.10*on/{nf}' if mode == 'in' else f'1.10-0.10*on/{nf}'
        xs = f'(iw-iw/zoom)*(0.5+{px}*(on/{nf}-0.5))'
        ys = f'(ih-ih/zoom)*(0.5+{py}*(on/{nf}-0.5))'
        pre = f'crop=iw:ih*{CROP[x["k"]]},' if x['k'] in CROP else ''
        vf = (f'{pre}scale=3840:2160:force_original_aspect_ratio=increase,crop=3840:2160,'
              f"zoompan=z='{z}':x='{xs}':y='{ys}':d={nf}:s={W}x{H}:fps={FPS},setsar=1{tail}")
        sh(f'ffmpeg -v error -y -i {src} -vf "{vf}" {enc} {out}')
    return out


def do_shots():
    os.makedirs('src', exist_ok=True)
    os.makedirs('shots', exist_ok=True)
    shots, total = timeline()
    need = {('c', x['k']) if x['t'] == 'clip' else ('i', x['k']) for x in shots}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda p: fetch(CF + (CLIPS if p[0] == 'c' else IMGS)[p[1]] + ('.mp4' if p[0] == 'c' else '.png'),
                                    f'src/{p[0]}{p[1]}.' + ('mp4' if p[0] == 'c' else 'png')), need))
    with ThreadPoolExecutor(6) as ex:
        outs = list(ex.map(render, shots))
    with open('list.txt', 'w') as f:
        f.writelines(f"file '{o}'\n" for o in outs)
    sh('ffmpeg -v error -y -f concat -safe 0 -i list.txt -c copy base.mp4')
    print('base.mp4', total, len(shots), 'shots')


def do_words():
    fetch(NARR, 'narr.mp3')
    from faster_whisper import WhisperModel
    m = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=8)
    segs, _ = m.transcribe('narr.mp3', word_timestamps=True)
    words = [(w.start, w.end, w.word.strip()) for s in segs for w in s.words]
    json.dump(words, open('words.json', 'w'))
    print('words', len(words))


def script_sections():
    md = urllib.request.urlopen(RAW + 'Greatest_Destroyers_Ranked_Master.md').read().decode()
    v = md[md.index('## Complete voiceover'):md.index('## Storyboard in countdown order')]
    parts = re.split(r'\n### (.+)\n', v)[1:]
    return [' '.join(l.strip() for l in parts[k + 1].strip().split('\n') if l.strip()) for k in range(0, len(parts), 2)]


def norm(w):
    return re.sub(r'[^a-z0-9]', '', w.lower())


def ass_time(t):
    t = max(t, 0)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def captions(words):
    secs = script_sections()
    sw = []  # (display word, section)
    for k, txt in enumerate(secs):
        sw += [(w, k) for w in txt.split()]
    a = [norm(w) for w, _ in sw]
    b = [norm(w[2]) for w in words]
    times = [None] * len(sw)
    for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for d in range(blk.size):
            ws, we, _ = words[blk.b + d]
            times[blk.a + d] = (ws, we)
    # interpolate unmatched runs between anchors
    idx = [n for n, t in enumerate(times) if t]
    for n in range(len(sw)):
        if times[n]:
            continue
        p = max((q for q in idx if q < n), default=None)
        q = min((q for q in idx if q > n), default=None)
        t0 = times[p][1] if p is not None else 0.0
        t1 = times[q][0] if q is not None else t0 + 0.4
        np_ = (q if q is not None else n + 1) - (p if p is not None else -1)
        frac = (n - (p if p is not None else -1)) / np_
        st = t0 + (t1 - t0) * frac
        times[n] = (st, st + max((t1 - t0) / np_, 0.15))
    chunks, cur = [], []
    for n, (w, k) in enumerate(sw):
        cur.append(n)
        end_sent = w[-1] in '.?!:;,'
        nxt_sec = n + 1 < len(sw) and sw[n + 1][1] != k
        if (len(cur) >= 7) or (end_sent and len(cur) >= 3) or w[-1] in '.?!' or nxt_sec or n == len(sw) - 1:
            chunks.append(cur)
            cur = []
    ev = []
    for m, ch in enumerate(chunks):
        st = times[ch[0]][0]
        en = times[ch[-1]][1] + 0.25
        if m + 1 < len(chunks):
            en = min(en, times[chunks[m + 1][0]][0] - 0.02)
        txt = ' '.join(sw[n][0] for n in ch)
        ev.append(f'Dialogue: 0,{ass_time(st)},{ass_time(en)},Cap,,0,0,0,,{txt}')
    return ev


def overlays(shots):
    ev = []
    for x in shots:
        s, e = x['f0'] / FPS, x['f1'] / FPS
        if 'title' in x:
            rank, name, sub = x['title']
            a, b = s + 0.25, min(s + 5.0, e - 0.1)
            fad = r'{\fad(350,450)}'
            y = 70
            if rank:
                ev.append(f'Dialogue: 2,{ass_time(a)},{ass_time(b)},Rank,,0,0,0,,{{\\pos(90,{y})}}{fad}{rank}')
                y += 175
            ev.append(f'Dialogue: 2,{ass_time(a + 0.15)},{ass_time(b)},Name,,0,0,0,,{{\\pos(94,{y})}}{fad}{name}')
            if sub:
                ev.append(f'Dialogue: 2,{ass_time(a + 0.3)},{ass_time(b)},Sub,,0,0,0,,{{\\pos(98,{y + 90})}}{fad}{sub}')
        if 'label' in x:
            a, b = s + 0.5, min(s + 6.5, e - 0.2)
            ev.append(f'Dialogue: 1,{ass_time(a)},{ass_time(b)},Stat,,0,0,0,,{{\\pos(90,80)}}{{\\fad(300,400)}}{x["label"]}')
        if 'big' in x:
            top, bot = x['big']
            a, b = s + 0.3, e - 0.2
            ev.append(f'Dialogue: 2,{ass_time(a)},{ass_time(b)},Big,,0,0,0,,{{\\pos(960,470)}}{{\\fad(500,500)}}{top}')
            ev.append(f'Dialogue: 2,{ass_time(a + 0.4)},{ass_time(b)},BigSub,,0,0,0,,{{\\pos(960,590)}}{{\\fad(500,500)}}{bot}')
    return ev


HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3.2,1,2,200,200,64,1
Style: Rank,Montserrat ExtraBold,170,&H003C14DC,&H003C14DC,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,4,2,7,0,0,0,1
Style: Name,Montserrat ExtraBold,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,3.5,2,7,0,0,0,1
Style: Sub,Metropolis ExtraBold,36,&H00D8D8D8,&H00D8D8D8,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,2.5,1,7,0,0,0,1
Style: Stat,Montserrat ExtraBold,42,&H00FFFFFF,&H00FFFFFF,&H9A0A0A0A,&H00000000,0,0,0,0,100,100,1,0,3,14,0,7,0,0,0,1
Style: Big,Montserrat ExtraBold,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,3,0,1,4,3,5,0,0,0,1
Style: BigSub,Montserrat ExtraBold,56,&H003C14DC,&H003C14DC,&H00000000,&H64000000,0,0,0,0,100,100,6,0,1,3,2,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def do_final():
    shots, total = timeline()
    words = json.load(open('words.json'))
    with open('gd.ass', 'w') as f:
        f.write(HEADER + '\n'.join(overlays(shots) + captions(words)) + '\n')
    sh(f'ffmpeg -v error -y -i base.mp4 -i narr.mp3 -vf "ass=gd.ass:fontsdir={FONTS}" '
       f'-c:v libx264 -preset veryfast -crf 19 -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart -shortest final.mp4')
    print('final.mp4 done')


# Pause targets for the narration edit (silence only; the voice is never stretched).
GAP_MAX, GAP_TO = 0.45, 0.40          # ordinary sentence gaps
REVEAL = (0.8, 1.0)                   # first pause after "At number ..." in sections 1-10
TWIST = 1.2                           # first pause in the bonus ("Now the twist.")
BREAK = {11: 1.5, 12: 1.2}            # silence before these sections; others use BREAK_DEFAULT
BREAK_DEFAULT, HEAD, TAIL = 1.0, 0.4, 1.5


def do_narr():
    import numpy as np
    SR, FR = 48000, 480
    urls = ASSETS['narr']

    def load(p):
        b = subprocess.run(['ffmpeg', '-v', 'error', '-i', p, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                           capture_output=True, check=True).stdout
        return np.frombuffer(b, dtype=np.float32).reshape(-1, 2)

    def runs(x, thr=-42):
        m = x.mean(1); n = len(m) // FR
        db = 20 * np.log10(np.sqrt((m[:n * FR].reshape(n, FR) ** 2).mean(1) + 1e-12))
        sil = db < thr; out = []; k = 0
        while k < n:
            if sil[k]:
                j = k
                while j < n and sil[j]:
                    j += 1
                out.append((k * FR, j * FR)); k = j
            else:
                k += 1
        return out, n * FR

    os.makedirs('narr', exist_ok=True)
    secs = []
    for k in range(len(urls)):
        x = load(fetch(urls[k], f'narr/s{k:02d}.wav'))
        rs, end = runs(x)
        a = rs[0][1] if rs and rs[0][0] == 0 else 0
        b = rs[-1][0] if rs and rs[-1][1] >= end - FR else len(x)
        inner = [(p, q) for p, q in rs if p > a and q < b and (q - p) / SR >= 0.25]
        pieces, cur = [], a
        for gi, (p, q) in enumerate(inner):
            d = (q - p) / SR
            if gi == 0 and 1 <= k <= 10:
                t = min(max(d, REVEAL[0]), REVEAL[1])
            elif gi == 0 and k == 11:
                t = TWIST
            elif d > GAP_MAX:
                t = GAP_TO
            else:
                t = d
            h = int(t * SR / 2)
            pieces.append(x[cur:p + h]); cur = q - (int(t * SR) - h)
        pieces.append(x[cur:b])
        secs.append(np.concatenate(pieces))
    sil = lambda t: np.zeros((int(t * SR), 2), dtype=np.float32)
    out, t, starts = [sil(HEAD)], HEAD, []
    for k, y in enumerate(secs):
        if k:
            g = BREAK.get(k, BREAK_DEFAULT); out.append(sil(g)); t += g
        starts.append(round(t, 2)); out.append(y); t += len(y) / SR
    out.append(sil(TAIL))
    np.concatenate(out).astype('<f4').tofile('narr.f32')
    sh(f'ffmpeg -v error -y -f f32le -ar {SR} -ac 2 -i narr.f32 -af loudnorm=I=-16:TP=-1.5:LRA=11 -ar {SR} -c:a libmp3lame -b:a 320k narr.mp3')
    total = t + TAIL
    json.dump({'starts': starts, 'total': round(total, 2), 'words': 1445, 'overall_wpm': round(1445 / total * 60)},
              open('timing.json', 'w'))
    print('narr', round(total, 1), 's', starts)


if __name__ == '__main__':
    {'narr': do_narr, 'shots': do_shots, 'words': do_words, 'final': do_final}[sys.argv[1]]()

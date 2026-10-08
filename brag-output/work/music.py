"""Original 20-second, 96 BPM instrumental. No external samples or services."""
import numpy as np
import wave
from pathlib import Path

SR = 44100
DURATION = 20
N = SR * DURATION
mix = np.zeros((N, 2), dtype=np.float64)
rng = np.random.default_rng(77)

def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)

def add(signal, start, gain=1.0, pan=0.0):
    offset = int(start * SR)
    length = min(len(signal), N - offset)
    if length <= 0:
        return
    signal = signal[:length] * gain
    mix[offset:offset+length, 0] += signal * np.sqrt((1-pan)/2)
    mix[offset:offset+length, 1] += signal * np.sqrt((1+pan)/2)
    for delay, level in [(0.125, .14), (.25, .08)]:
        d = int(delay*SR)
        lim = min(length, N-offset-d)
        if lim > 0:
            mix[offset+d:offset+d+lim, 0] += signal[:lim] * level * np.sqrt((1+pan)/2)
            mix[offset+d:offset+d+lim, 1] += signal[:lim] * level * np.sqrt((1-pan)/2)

def tone(note, length, kind='pluck'):
    t=np.arange(int(length*SR))/SR
    f=hz(note)
    if kind=='pad':
        env=np.minimum(t/.2,1)*np.minimum((length-t)/.6,1)
        sound=np.sin(2*np.pi*f*t)+.24*np.sin(2*np.pi*(f*2+.25)*t)
    elif kind=='bass':
        env=np.minimum(t/.018,1)*np.exp(-t*3)
        sound=np.sin(2*np.pi*f*t)+.13*np.sin(2*np.pi*2*f*t)
    else:
        env=np.minimum(t/.005,1)*np.exp(-t*6)
        sound=np.sin(2*np.pi*f*t)+.25*np.sin(2*np.pi*2*f*t)+.08*np.sin(2*np.pi*3*f*t)
    return sound*env

chords=[(43,55,59,62,66),(40,55,59,64,67),(48,55,60,64,67),(50,57,62,66,69)]*2
beat=.625
for bar,(bass,*notes) in enumerate(chords):
    start=bar*2.5
    for i,note in enumerate(notes): add(tone(note,2.8,'pad'),start,.07,(-.4+.26*i))
    for b in range(4):
        at=start+b*beat
        add(tone(bass,.52,'bass'),at,.20)
        t=np.arange(int(.26*SR))/SR
        kick=np.sin(2*np.pi*(48*t+55*.022*(1-np.exp(-t/.022))))*np.exp(-t*20)*np.minimum(t/.002,1)
        add(kick,at,.27)
        if b in (1,3):
            t=np.arange(int(.15*SR))/SR
            noise=rng.standard_normal(len(t)); noise=np.concatenate(([0],np.diff(noise)))
            add(noise*np.exp(-t*38)*np.minimum(t/.003,1),at,.025)
    for step in range(8):
        at=start+step*.3125
        note=notes[[0,2,1,3,2,1,3,2][step]]+12
        add(tone(note,.7),at,.092,(-.32 if step%2 else .32))
        t=np.arange(int(.055*SR))/SR
        noise=rng.standard_normal(len(t)); noise=np.concatenate(([0],np.diff(noise)))
        add(noise*np.exp(-t*92)*np.minimum(t/.002,1),at,.012,(-.15 if step%2 else .15))

# Soft tonal cues in the same harmony, woven into scene transitions.
for at,notes in [(3,[74,78]),(7,[76,79]),(12,[74,78]),(16,[79,83,86])]:
    for j,note in enumerate(notes): add(tone(note,1),at+j*.06,.10,(-.3+j*.3))
envelope=np.ones(N)
envelope[:int(.12*SR)]=np.linspace(0,1,int(.12*SR))
envelope[-int(1.1*SR):]=np.linspace(1,0,int(1.1*SR))**1.3
mix*=envelope[:,None]
mix=np.tanh(mix*1.15)
mix*=.79/max(np.max(np.abs(mix)),.01)
Path('assets').mkdir(exist_ok=True)
with wave.open('assets/soundtrack.wav','wb') as stream:
    stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(SR)
    stream.writeframes((mix*32767).astype('<i2').tobytes())
print(f'Original soundtrack: {DURATION}s stereo, 96 BPM, peak {20*np.log10(np.max(np.abs(mix))):.1f} dBFS')

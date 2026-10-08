"""Inspect decoded frames for the reported reveal/reset/reveal regression."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ENCODER = Path(r'C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe')
video = Path(sys.argv[1] if len(sys.argv) > 1 else '../brag.mp4')
report_path = Path(sys.argv[2] if len(sys.argv) > 2 else 'jitter-verification.json')
process = subprocess.Popen([str(ENCODER), '-v', 'error', '-i', str(video), '-vf', 'scale=320:180', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], stdout=subprocess.PIPE)
frames = []
while True:
    buffer = process.stdout.read(320*180)
    if len(buffer) != 320*180:
        break
    frames.append(np.frombuffer(buffer, np.uint8).reshape(180,320))
if process.wait() != 0:
    raise RuntimeError('Video decoding failed')
frames = np.stack(frames).astype(np.float32)
assert len(frames) == 600, f'Expected 600 frames, found {len(frames)}'

# Crop out persistent header/footer and measure scene-content visibility.
dark_fraction = (frames[:, 33:147, 15:300] < 170).mean(axis=(1,2))
boundaries = []
for cut in [3,7,12,16]:
    first = cut*30
    normalizer = max(float(dark_fraction[first+28]), .001)
    levels = dark_fraction[first:first+21] / normalizer
    initial_max = float(levels[:4].max())
    largest_drop = max(0, float((-np.diff(levels)).max()))
    # A bad render is fully visible for four frames and then drops ~90%.
    passed = initial_max < .06 and largest_drop < .20
    boundaries.append({'cut_seconds':cut,'initial_visibility_max':round(initial_max,4),'largest_visibility_drop':round(largest_drop,4),'passed':passed})

opening_change = float(np.abs(frames[1]-frames[0]).mean())
# Baking a PNG into H.264 adds small RGB/YUV rounding differences. Compare
# actual edge geometry so harmless color quantization is not called motion.
opening_edges=[]
for frame in frames[:2]:
    opening_edges.append(np.hypot(np.diff(frame,axis=0)[:,:-1],np.diff(frame,axis=1)[:-1,:]) > 12)
opening_edge_overlap=float(np.logical_and(*opening_edges).sum()/max(1,np.logical_or(*opening_edges).sum()))
opening_passed = opening_edge_overlap > .98 and opening_change < .5
settled = []
for start,end in [(1,2.7),(4.2,5.5),(8.5,10),(13.3,15.5),(17.3,19.8)]:
    changes = np.abs(np.diff(frames[int(start*30):int(end*30)],axis=0)).mean(axis=(1,2))
    settled.append({'seconds':[start,end],'maximum_mean_pixel_change':round(float(changes.max()),4),'passed':float(changes.max())<.08})

report={'video':video.name,'frame_count':len(frames),'opening_adjacent_frame_change':round(opening_change,4),'opening_edge_overlap':round(opening_edge_overlap,4),'opening_passed':opening_passed,'scene_entrances':boundaries,'settled_holds':settled}
report['passed']=opening_passed and all(item['passed'] for item in boundaries+settled)
report_path.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
sys.exit(0 if report['passed'] else 1)

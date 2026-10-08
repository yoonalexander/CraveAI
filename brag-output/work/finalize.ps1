$ErrorActionPreference = 'Stop'
$taskEncoder = 'C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe'
$taskProbe = Join-Path (Split-Path $taskEncoder) 'ffprobe.exe'

# The poster is a settled frame from the actual encoded film.
& $taskEncoder -y -hide_banner -loglevel warning -ss 1.5 -i launch-render.mp4 -frames:v 1 -update 1 poster.png
if ($LASTEXITCODE -ne 0) { throw 'Poster extraction failed' }
& $taskEncoder -y -hide_banner -loglevel warning -i poster.png -frames:v 1 -q:v 2 -update 1 ../brag.jpg
if ($LASTEXITCODE -ne 0) { throw 'JPEG poster failed' }

# Replace frame zero; keep the original 600-frame timeline and audio stream.
& $taskEncoder -y -hide_banner -loglevel warning -i launch-render.mp4 -i poster.png -filter_complex '[0:v][1:v]overlay=enable=eq(n\,0):format=auto[v]' -map '[v]' -map 0:a:0 -c:v libx264 -crf 16 -preset medium -threads 2 -pix_fmt yuv420p -c:a copy -movflags +faststart ../brag.mp4
if ($LASTEXITCODE -ne 0) { throw 'Final poster bake failed' }
& $taskProbe -v error -show_entries 'stream=index,codec_name,codec_type,width,height,r_frame_rate,duration,nb_frames,sample_rate,channels:format=duration,size' -of json ../brag.mp4 | Set-Content -Encoding utf8 verification.json
if ($LASTEXITCODE -ne 0) { throw 'Media verification failed' }
Get-Content verification.json

# Decode checks and integrated loudness are retained for review.
& $taskEncoder -hide_banner -v error -i ../brag.mp4 -f null - 2> decode-check.log
if ($LASTEXITCODE -ne 0) { throw 'Final MP4 decode failed' }
& $taskEncoder -hide_banner -i ../brag.mp4 -af 'ebur128=peak=true' -vn -f null - 2> loudness.log
if ($LASTEXITCODE -ne 0) { throw 'Audio check failed' }

# Final encoded frames, including the baked first frame.
New-Item -ItemType Directory -Path final-review -Force | Out-Null
foreach ($taskMoment in @(0, 1.5, 4.8, 8.8, 13.6, 18.2)) {
    & $taskEncoder -y -hide_banner -loglevel warning -ss $taskMoment -i ../brag.mp4 -frames:v 1 -update 1 "final-review/frame-$taskMoment.png"
    if ($LASTEXITCODE -ne 0) { throw 'Final frame extraction failed' }
}

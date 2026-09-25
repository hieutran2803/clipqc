"""Regenerate the synthetic test clips in tests/fixtures/media/.

The generated files are committed, so every CI leg tests the same bytes no
matter which ffmpeg version it has. Run this only when a fixture must change:

    uv run python tests/fixtures/make_fixtures.py
"""
from __future__ import annotations

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

MEDIA = Path(__file__).parent / "media"
SIZE = "160x284"
DUR = 4
VIDEO = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p"]
AUDIO = ["-c:a", "aac", "-b:a", "64k"]
CLEAN_META = ["-map_metadata", "-1", "-fflags", "+bitexact"]
FASTSTART = ["-movflags", "+faststart"]


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-nostdin", *args], check=True)


def src(size: str = SIZE, dur: float = DUR) -> list[str]:
    """testsrc2 video plus a stereo sine at about -14 LUFS."""
    return [
        "-f", "lavfi", "-i", f"testsrc2=s={size}:r=30:d={dur}",
        "-f", "lavfi", "-i", f"sine=f=440:d={dur}:sample_rate=48000",
    ]


STEREO = ["-af", "volume=7.5dB,aformat=channel_layouts=stereo"]


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    m = lambda name: str(MEDIA / name)  # noqa: E731

    ff(*src(), *STEREO, *VIDEO, *AUDIO, *CLEAN_META, *FASTSTART, m("clean.mp4"))
    ff("-i", m("clean.mp4"), "-vf", "drawbox=t=fill:c=black:enable='between(t,1,2)'",
       *VIDEO, "-c:a", "copy", *CLEAN_META, *FASTSTART, m("black.mp4"))
    ff("-i", m("clean.mp4"), "-filter_complex",
       "[0:v]trim=0:1,setpts=PTS-STARTPTS[a];"
       "[0:v]trim=start_frame=30:end_frame=31,setpts=PTS-STARTPTS,"
       "tpad=stop_mode=clone:stop_duration=2.5[f];"
       "[0:v]trim=3.5:4,setpts=PTS-STARTPTS[c];"
       "[a][f][c]concat=n=3:v=1:a=0[v]",
       "-map", "[v]", "-map", "0:a", *VIDEO, "-c:a", "copy", *CLEAN_META, *FASTSTART,
       m("frozen.mp4"))
    ff("-i", m("clean.mp4"), "-c:v", "copy", "-af", "volume=0", *AUDIO, *CLEAN_META,
       *FASTSTART, m("silent.mp4"))
    ff("-i", m("clean.mp4"), "-c:v", "copy", "-af", "volume=30dB,aformat=sample_fmts=s16",
       *AUDIO, *CLEAN_META, *FASTSTART, m("clipped.mp4"))
    ff(*src(dur=0.5), *STEREO, *VIDEO, *AUDIO, *CLEAN_META, *FASTSTART, m("tiny.mp4"))
    ff("-i", m("clean.mp4"), "-filter_complex", "[0:v]trim=0:2,setpts=PTS-STARTPTS[v]",
       "-map", "[v]", "-map", "0:a", *VIDEO, "-c:a", "copy", *CLEAN_META, *FASTSTART,
       m("avmis.mp4"))
    ff("-i", m("clean.mp4"), "-c:v", "copy", "-an", *CLEAN_META, *FASTSTART, m("noaudio.mp4"))
    ff("-i", m("clean.mp4"), "-c", "copy", *CLEAN_META, m("moovend.mp4"))
    ff(*src(size="284x160"), *STEREO, *VIDEO, *AUDIO, *CLEAN_META, *FASTSTART,
       m("landscape.mp4"))

    ff("-i", m("clean.mp4"), "-c", "copy", *CLEAN_META, m("clean.mkv"))
    # Healthy files whose packet counts fall short of nb_frames: PCM audio in MOV counts
    # samples as frames, and a stream-copy trim drops audio packets before the edit list.
    ff("-i", m("clean.mp4"), "-c:v", "copy", "-c:a", "pcm_s16le", *CLEAN_META, *FASTSTART,
       m("pcm.mov"))
    ff("-ss", "1.5", "-i", m("clean.mp4"), "-c", "copy", *CLEAN_META, *FASTSTART, m("sscopy.mp4"))
    ff("-i", m("clean.mp4"), "-vn", "-c:a", "copy", *CLEAN_META, *FASTSTART, m("novideo.mp4"))
    with tempfile.TemporaryDirectory() as tmp:
        cover = str(Path(tmp) / "cover.png")
        ff("-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", cover)
        # Cover art as an attached picture, like raw AI-generator downloads carry.
        ff("-i", cover, "-i", m("clean.mp4"), "-map", "0", "-map", "1", "-c", "copy",
           "-disposition:v:0", "attached_pic", *CLEAN_META, *FASTSTART, m("cover.mp4"))

    data = (MEDIA / "clean.mp4").read_bytes()
    (MEDIA / "trunc.mp4").write_bytes(data[: len(data) * 6 // 10])
    mkv = (MEDIA / "clean.mkv").read_bytes()
    (MEDIA / "trunc.mkv").write_bytes(mkv[: len(mkv) * 6 // 10])
    moov_end = (MEDIA / "moovend.mp4").read_bytes()
    (MEDIA / "trunc_moovend.mp4").write_bytes(moov_end[: len(moov_end) * 6 // 10])
    corrupt = bytearray(data)
    at = len(corrupt) * 4 // 10
    corrupt[at : at + 4096] = random.Random(1234).randbytes(4096)
    (MEDIA / "corrupt.mp4").write_bytes(bytes(corrupt))

    with tempfile.TemporaryDirectory() as tmp:
        seg = []
        for name, space in (("a.ts", "bt709"), ("b.ts", "smpte170m")):
            out = str(Path(tmp) / name)
            ff(*src(dur=2), *STEREO, *VIDEO, "-colorspace", space, "-color_primaries", space,
               "-color_trc", space, *AUDIO, "-f", "mpegts", out)
            seg.append(out)
        ff("-i", "concat:" + "|".join(seg), "-c", "copy", *CLEAN_META, *FASTSTART,
           m("mixcs.mp4"))


if __name__ == "__main__":
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg not found on PATH")
    main()

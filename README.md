# clipqc

**Catch broken clips before they ship.** Point `clipqc` at a folder of exported
videos (AI-generated shorts, batch renders, client deliverables) and it tells
you which clips are broken and at which second. It exits non-zero when anything
fails, so it drops straight into a render pipeline or a CI job.

clipqc never edits your video. It does not judge hands, motion or style; that is
still a human's job.

## Install

Needs `ffmpeg` and `ffprobe` on your `PATH` (Linux or macOS).

```sh
uv tool install git+https://github.com/hieutran2803/clipqc
# or: pipx install git+https://github.com/hieutran2803/clipqc
```

## Use

```sh
clipqc check renders/
```

```text
FAIL         black.mp4
  fail  1.00-2.03s     frame.black                 black frames 1.00s-2.03s
PASS         clean.mp4
WARN         frozen.mp4
  warn  1.00-3.53s     frame.frozen                frozen picture 1.00s-3.53s
FAIL         silent.mp4
  fail  -              audio.silent                audio is silent (sample peak -inf dBFS)
FAIL         trunc.mp4
  fail  2.37s          frame.truncated             file is truncated at 2.37s: video has 74/120 packets; audio has 112/189 packets; media ends at 2.53s but the header says 4.00s; box 'mdat' at byte 5770 claims 101943 bytes, file has 58857

5 clip(s): 3 fail, 1 pass, 1 warn
```

`clipqc check renders/ --json > report.json` writes the same result as one JSON
document (`clipqc.report/v1`) that lists every clip, including the clean ones.
Progress goes to stderr, so stdout stays machine-readable.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Every clip passed (warnings allowed) |
| 1 | At least one clip failed |
| 2 | Usage error: bad config, unknown detector, no videos found, ffmpeg missing |
| 3 | Nothing failed, but some clip could not be fully checked (`--strict` turns this into 1) |

## What v0.1 checks

| Code | Level | Catches |
|---|---|---|
| `frame.unreadable_container` | fail | file cannot be opened (e.g. cut off before its index) |
| `frame.truncated` | fail | file cut short; reports the second where data ends |
| `frame.decode_error` | fail | corrupt video or audio data inside an intact file |
| `frame.no_video` | fail | no video stream |
| `frame.black` | fail | black frames lasting 0.5 s or more |
| `frame.frozen` | warn | frozen picture lasting 2 s or more |
| `frame.duration` | fail | shorter than 1 s, or outside the configured range |
| `frame.av_mismatch` | warn / fail | picture and sound end at different times |
| `frame.faststart` | warn | index at the end of the file (slow web playback) |
| `frame.batch_mismatch` | warn | resolution, frame rate or rotation differs from the rest of the batch |
| `frame.params_changed` | warn | video format changes mid-file |
| `audio.missing` | fail | no audio stream |
| `audio.silent`, `audio.near_silent` | fail | silent, or quieter than -40 LUFS |
| `audio.clipping` | warn / fail | samples stuck at full scale |
| `audio.true_peak` | warn / fail | true peak above -1 / 0 dBTP |
| `audio.loudness` | warn | more than 4 LU away from -14 LUFS |

## Config

Optional `clipqc.toml`, passed with `--config`:

```toml
audio = "required"            # required | optional | forbidden
loudness_target_lufs = -14.0
loudness_tolerance_lu = 4.0
duration_min_s = 1.0
duration_max_s = 60.0         # omit for no ceiling
```

Unknown keys are an error, so a typo never silently falls back to a default.

## Known limits

- On-screen text (typos, cut-off captions) is not checked yet; it is next.
- Look-alike character drift, hands and motion are not judged.
- Tested with ffmpeg 6.1, 8.0, 8.1 and 9.0. ffmpeg 4.x is not supported yet (its
  CI leg is informational). `frame.params_changed` needs ffmpeg 8.0 or later,
  because 6.1 does not log a mid-file format change.

## Development

```sh
uv sync
uv run pytest
uv run python tests/fixtures/make_fixtures.py   # only when a fixture must change
```

## License

Apache-2.0

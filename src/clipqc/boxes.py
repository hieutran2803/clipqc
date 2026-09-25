"""Top-level ISO-BMFF (MP4/MOV) box walk: box order for faststart, overrun for truncation."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

# A file is treated as ISO-BMFF only if its first box is one of these. Anything
# else (Matroska, WebM, MPEG-TS) is skipped instead of parsed as garbage sizes.
_LEADING_TYPES = {"ftyp", "styp", "moov", "mdat", "free", "skip", "wide", "pnot"}


@dataclass(frozen=True)
class BoxWalk:
    is_isobmff: bool
    order: tuple[str, ...] = ()
    overrun: str | None = None


def walk_boxes(path: Path, max_boxes: int = 10_000) -> BoxWalk:
    total = path.stat().st_size
    order: list[str] = []
    overrun: str | None = None
    with path.open("rb") as fh:
        offset = 0
        while offset < total and len(order) < max_boxes:
            fh.seek(offset)
            header = fh.read(8)
            if len(header) < 8:
                overrun = f"incomplete box header at byte {offset}"
                break
            size, raw_type = struct.unpack(">I4s", header)
            box_type = raw_type.decode("latin-1")
            if not order and box_type not in _LEADING_TYPES:
                return BoxWalk(is_isobmff=False)
            if size == 1:
                large = fh.read(8)
                if len(large) < 8:
                    overrun = f"incomplete 64-bit size for box '{box_type}' at byte {offset}"
                    break
                size = struct.unpack(">Q", large)[0]
            elif size == 0:
                size = total - offset
            if size < 8:
                overrun = f"corrupt box '{box_type}' at byte {offset} (size {size})"
                break
            order.append(box_type)
            if offset + size > total:
                overrun = (
                    f"box '{box_type}' at byte {offset} claims {size} bytes, "
                    f"file has {total - offset}"
                )
                break
            offset += size
    return BoxWalk(is_isobmff=bool(order), order=tuple(order), overrun=overrun)

import struct

from clipqc.boxes import walk_boxes


def test_faststart_file_has_moov_before_mdat(media):
    walk = walk_boxes(media / "clean.mp4")
    assert walk.is_isobmff
    assert walk.order.index("moov") < walk.order.index("mdat")
    assert walk.overrun is None


def test_default_mux_puts_moov_after_mdat(media):
    walk = walk_boxes(media / "moovend.mp4")
    assert walk.order.index("moov") > walk.order.index("mdat")


def test_truncated_file_reports_the_overrunning_box(media):
    walk = walk_boxes(media / "trunc.mp4")
    assert walk.overrun is not None
    assert "'mdat'" in walk.overrun


def test_non_isobmff_file_is_not_parsed(tmp_path):
    mkv = tmp_path / "x.mkv"
    mkv.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 64)
    walk = walk_boxes(mkv)
    assert walk.is_isobmff is False
    assert walk.order == ()
    assert walk.overrun is None


def test_64bit_box_size_is_followed(tmp_path):
    body = b"\x00" * 8
    ftyp = struct.pack(">I4s", 16, b"ftyp") + body
    mdat = struct.pack(">I4sQ", 1, b"mdat", 16 + 4) + b"abcd"
    p = tmp_path / "big.mp4"
    p.write_bytes(ftyp + mdat)
    walk = walk_boxes(p)
    assert walk.order == ("ftyp", "mdat")
    assert walk.overrun is None


def test_box_smaller_than_its_header_is_corrupt(tmp_path):
    p = tmp_path / "bad.mp4"
    p.write_bytes(struct.pack(">I4s", 16, b"ftyp") + b"\x00" * 8 + struct.pack(">I4s", 4, b"moov"))
    walk = walk_boxes(p)
    assert walk.overrun is not None and "corrupt box 'moov'" in walk.overrun

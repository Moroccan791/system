from clipper.cli import ACCENTS, resolve_accent


def test_accent_palette_names_and_hex():
    assert resolve_accent("gold") == "#FFC531"
    assert resolve_accent("Gold") == "#FFC531"
    assert resolve_accent("#123456") == "#123456"
    assert resolve_accent(None) is None and resolve_accent("") is None
    for name in ("crimson", "azure", "lime", "violet", "pink", "white"):
        assert name in ACCENTS and ACCENTS[name].startswith("#")

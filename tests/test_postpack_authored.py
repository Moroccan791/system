"""Campaign posting copy must not be replaced by generic hashtags/claims."""
from __future__ import annotations

import copy

import pytest

from motion import postpack


REQUIRED = ("The podcast name is Street You Grew Up On - full episode "
            "is available on YT and other podcast platforms")


def timeline():
    return {
        "duration": 22.0,
        "items": [{"type": "poster", "at": 0.0, "until": 1.0,
                   "rows": [[{"w": "husband", "at": 0.0, "kind": "hero"}]]}],
        "posting": {
            "title": "Demi Lovato: I Don't Come Home to an Award",
            "alternativeTitles": ["Demi Lovato on Joy", "Connection Comes First"],
            "hookVariants": [{"strategy": "current", "hook": "I hold space"},
                             {"strategy": "quote", "hook": "Not an award"},
                             {"strategy": "close", "hook": "Connection"}],
            "description": "Demi talks about home, her dogs, and her husband.",
            "requiredLine": REQUIRED,
            "disclosure": "#ad",
            "hashtags": ["#DemiLovato", "#StreetYouGrewUpOn", "#PodcastClips",
                         "#Interview", "#Family", "#Connection", "#MusicAndLife"],
        },
    }


def test_authored_campaign_pack_wins_over_generic_matcher(tmp_path):
    tl = timeline()
    tr = {"words": [{"text": "husband", "start": 0.0, "end": 0.5}]}
    pack = postpack.build(tl, tr, video=None, out=tmp_path)
    assert pack["description"].startswith("#ad\n")
    assert REQUIRED in pack["description"]
    assert pack["titles"][0] == tl["posting"]["title"]
    assert pack["hook_variants"] == tl["posting"]["hookVariants"]
    assert pack["hashtags"] == tl["posting"]["hashtags"]
    assert "#dating" not in pack["hashtags"]
    assert len(pack["hashtags"]) == 7


def test_duplicate_hashtags_fail_loudly(tmp_path):
    tl = timeline()
    tl["posting"]["hashtags"][-1] = tl["posting"]["hashtags"][0]
    with pytest.raises(ValueError, match="unique hashtags"):
        postpack.build(tl, [], video=None, out=tmp_path)

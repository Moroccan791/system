"""clipper - a Whop clipping pipeline.

Stages (each one reads/writes JSON artifacts so they can be run standalone):

    0  ingest/scan      campaign folder  -> manifest.json
    1  style/extract    references       -> styles/<campaign>.style.json
    2  select/moments   raw footage      -> candidate clips
    3  captions         video/audio      -> captioned video (.ass + burn-in)
    4  edit/assemble    clips + profile  -> 9:16 edit
    5  export           edit             -> platform presets

Config resolution: environment variables prefixed with CLIPPER_ (see config.py).
"""

__version__ = "0.1.0"

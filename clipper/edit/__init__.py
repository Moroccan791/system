"""Stage 4 - assembling chosen moments into vertical clips (cuts, zooms, reframe)."""
from .pipeline import (candidates_for, edit_campaign, load_style)
from .sampler import CURATED, available_blends, render_sampler
from .plan import build_plan, camera_moves, summarise
from .render import build_filtergraph, render_plan

__all__ = ["CURATED", "available_blends", "build_filtergraph", "build_plan", "camera_moves",
           "candidates_for", "edit_campaign", "load_style", "render_plan", "render_sampler",
           "summarise"]

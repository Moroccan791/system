"""Stage 4 - assembling chosen moments into vertical clips (cuts, zooms, reframe)."""
from .pipeline import (candidates_for, edit_campaign, load_style)
from .plan import build_plan, camera_moves, summarise
from .render import build_filtergraph, render_plan

__all__ = ["build_filtergraph", "build_plan", "camera_moves", "candidates_for",
           "edit_campaign", "load_style", "render_plan", "summarise"]

"""Textual UI package."""

__all__ = ["ArgosBannerManager"]


def __getattr__(name: str):
	if name == "ArgosBannerManager":
		from argos_nt.ui.banner_manager import ArgosBannerManager

		return ArgosBannerManager
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

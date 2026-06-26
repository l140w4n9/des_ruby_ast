"""Backward-compatible entry point; implementation lives in desast/ package."""

from desast import Node, beautify_ruby, decompile, parse_dump, render

__all__ = ["Node", "parse_dump", "render", "beautify_ruby", "decompile"]


if __name__ == "__main__":
    from desast.cli import main
    main()

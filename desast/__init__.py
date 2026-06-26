"""Ruby AST dump -> source decompiler (MRI node tree renderer)."""

from desast.beautify import beautify_ruby
from desast.node import Node
from desast.parser import parse_dump
from desast.render import render


def decompile(text: str) -> str:
    """解析 AST dump 并输出美化后的 Ruby 源码。"""
    root = parse_dump(text)
    if not root:
        return ''
    return beautify_ruby(render(root))


__all__ = ["Node", "parse_dump", "render", "beautify_ruby", "decompile"]

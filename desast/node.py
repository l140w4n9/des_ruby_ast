from typing import Any, Dict, List, Optional

class Node:
    def __init__(self, ntype=None, line_no=None):
        self.type = ntype
        self.line = line_no
        self.attrs: Dict[str, Any] = {}
        self.children: List['Node'] = []
        self.parent: Optional['Node'] = None
        self._pending_attr: Optional[str] = None

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def __repr__(self):
        return f"<Node {self.type} line={self.line} attrs={list(self.attrs.keys())} children={len(self.children)}>"

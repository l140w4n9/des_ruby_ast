import re
from typing import List, Optional, Tuple

from desast.node import Node

# 解析正则
RE_NODE_HDR = re.compile(r'@ (\w+)(?: \((?:line: )?(\d+)\))?')
RE_ATTR = re.compile(r'\+\-\s*([\w\-\>]+):\s*(.*)')
RE_NULL = re.compile(r'^\(null\b|\(empty\b', re.I)


def preprocess_lines(text: str) -> List[str]:
    lines = []
    for raw in text.splitlines():
        s = raw
        if '#' in s:
            idx = s.find('#')
            s = s[idx + 1:]
            if s.startswith(' '):
                s = s[1:]
        lines.append(s.rstrip('\n'))
    return lines
def calc_indent(line: str) -> Tuple[int, str]:
    i = 0
    s = line
    while True:
        if s.startswith('|   '):
            i += 1
            s = s[4:]
        elif s.startswith('    '):
            i += 1
            s = s[4:]
        else:
            break
    return i, s.lstrip()
def parse_value(val: str):
    if val.lower() == 'nil':
        return None
    if val.startswith(':'):
        return val[1:]
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if re.match(r'^-?\d+$', val):
        return int(val)
    if re.match(r'^-?\d+\.\d+$', val):
        return float(val)
    if val == '':
        return ''
    return val


def parse_dump(text: str) -> Optional[Node]:
    lines = preprocess_lines(text)
    stack: List[(int, Node)] = []
    root = None

    for raw in lines:
        if not raw.strip():
            continue

        indent, content = calc_indent(raw)
        mnode = RE_NODE_HDR.search(content)

        if mnode:
            ntype = mnode.group(1)
            lineno = int(mnode.group(2)) if mnode.group(2) else None
            node = Node(ntype, lineno)

            if not stack:
                root = node
                stack.append((indent, node))
            else:
                while stack and stack[-1][0] >= indent:
                    stack.pop()

                parent = stack[-1][1] if stack else None
                if parent:
                    parent.add_child(node)
                    if parent._pending_attr:
                        parent.attrs[parent._pending_attr] = node
                        parent._pending_attr = None

                stack.append((indent, node))
            continue

        matt = RE_ATTR.match(content)
        if matt:
            key = matt.group(1)
            val = matt.group(2).strip()
            parent = None

            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] < indent + 1:
                    parent = stack[i][1]
                    break

            if parent is None:
                parent = stack[-1][1] if stack else None
            if parent is None:
                continue

            if not val or RE_NULL.match(val):
                if RE_NULL.match(val):
                    parent.attrs[key] = None
                else:
                    parent._pending_attr = key
            else:
                parent.attrs[key] = parse_value(val)
            continue

        if RE_NULL.match(content.strip()):
            if stack and stack[-1][1]._pending_attr:
                stack[-1][1].attrs[stack[-1][1]._pending_attr] = None
                stack[-1][1]._pending_attr = None
            continue

    return root

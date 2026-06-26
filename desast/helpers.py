from typing import List, Optional

from desast.node import Node

def indent_block(s: str, level: int):
    if not s:
        return ''
    pad = '  ' * level
    return '\n'.join(pad + line if line.strip() else line for line in s.splitlines())


def find_child(node: Node, types):
    for c in node.children:
        if c.type in types:
            return c
    return None


def collect_list(array_node: Optional[Node]) -> List[Node]:
    """遍历 MRI 的 cons-list NODE_ARRAY (nd_head=本元素, nd_next=剩余链表),
    返回扁平的元素节点列表 [e0, e1, e2, ...]。
    用于 hash(交替 key/value)、数组字面量、参数列表等。"""
    elems: List[Node] = []
    cur = array_node
    seen = set()
    while isinstance(cur, Node) and cur.type in ('NODE_ARRAY', 'NODE_LIST'):
        if id(cur) in seen:  # 防御环
            break
        seen.add(id(cur))
        h = cur.attrs.get('nd_head')
        if isinstance(h, Node):
            elems.append(h)
        nxt = cur.attrs.get('nd_next')
        cur = nxt if isinstance(nxt, Node) else None
    return elems


def esc_str_content(text) -> str:
    """把字面量文本转义为可放进 Ruby 双引号字符串的内容(不含外层引号)。
    只转义反斜杠/双引号/换行/制表/#{ , 不碰已是插值的 #{...}。"""
    if not isinstance(text, str):
        text = str(text)
    out = text.replace('\\', '\\\\').replace('"', '\\"')
    out = out.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
    out = out.replace('#{', '\\#{')
    return out


def format_ruby_block(content: str, level: int) -> str:
    """格式化Ruby代码块，确保正确的缩进"""
    if not content:
        return ''

    lines = content.split('\n')
    formatted_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            formatted_lines.append('')
            continue

        # 根据内容调整缩进
        if stripped.startswith('end') or stripped.startswith('else') or stripped.startswith(
                'elsif') or stripped.startswith('rescue') or stripped.startswith('ensure') or stripped.startswith(
            'when'):
            formatted_lines.append('  ' * (level - 1) + stripped)
        else:
            formatted_lines.append('  ' * level + stripped)

    return '\n'.join(formatted_lines)

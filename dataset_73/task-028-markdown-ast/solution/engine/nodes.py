from __future__ import annotations


def make_node(node_type: str, children=None, **attrs) -> dict:
    node = {"type": node_type}
    if children is not None:
        node["children"] = children
    node.update(attrs)
    return node


def text(value):
    return {"type": "text", "value": value}

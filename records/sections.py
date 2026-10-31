def section(doc, anchor):
    """Recorte do documento: do título `anchor` até o próximo título de nível igual ou menor."""
    nodes = [n for n in (doc.get("content") or []) if isinstance(n, dict)]
    for i, node in enumerate(nodes):
        attrs = node.get("attrs") or {}
        if node.get("type") == "heading" and attrs.get("anchor") == anchor:
            level = attrs.get("level", 2)
            end = len(nodes)
            for j in range(i + 1, len(nodes)):
                other = nodes[j]
                if other.get("type") == "heading" and (other.get("attrs") or {}).get("level", 2) <= level:
                    end = j
                    break
            return {"type": "doc", "content": nodes[i:end]}
    return None

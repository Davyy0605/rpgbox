from .models import Block


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


def find_section(record, anchor):
    """Primeiro trecho `anchor` do registro: (recorte, id da aba), com aba None para campo longo."""
    for f in record.record_type.fielddef_set.filter(kind="long"):
        value = record.fields.get(f.key)
        found = section(value, anchor) if isinstance(value, dict) else None
        if found:
            return found, None
    for block in Block.objects.filter(tab__record=record, kind="text").order_by("tab__position", "position", "id"):
        found = section(block.content, anchor) if isinstance(block.content, dict) else None
        if found:
            return found, block.tab_id
    return None, None

import re

from django.db import transaction

from content.doc import clean_text, safe_href
from indexing.services import reindex_record
from records.services import create_record

HTTP_RE = re.compile(r"https?://\S+", re.I)


def parse_bulk_tracks(text):
    """Linhas "Nome: link", "Nome | link", "Nome link" ou só o link.

    Devolve (trilhas, linhas inválidas); as linhas são contadas de 1, e as vazias são ignoradas.
    """
    tracks, bad = [], []
    for n, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        m = HTTP_RE.search(line)
        if m is None:
            bad.append(n)
            continue
        url = m.group(0)
        name = (line[:m.start()] + line[m.end():]).strip(" \t:|-–—") or url
        if not safe_href(url) or not clean_text(name) or not clean_text(url) or len(name) > 160 or len(url) > 2000:
            bad.append(n)
            continue
        tracks.append((name, url))
    return tracks, bad


def create_tracks(rtype, link_key, tracks):
    with transaction.atomic():
        for name, url in tracks:
            record = create_record(rtype, name)
            record.fields = {link_key: url}
            record.save(update_fields=["fields"])
            reindex_record(record)
    return len(tracks)

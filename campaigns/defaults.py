from django.db import transaction

from .models import FieldDef, RecordType, TabDef

# (nome, [(rótulo, tipo)], [abas])
DEFAULT_TYPES = [
    ("Personagens", [("Ocupação", "short"), ("Idade", "number"), ("Resumo", "long")],
     ["Ficha", "Habilidades", "Magias", "História"]),
    ("Itens", [("Categoria", "short"), ("Raridade", "short"), ("Resumo", "long")],
     ["Descrição", "Efeitos"]),
    ("Regiões", [("Tipo de lugar", "short"), ("Resumo", "long")],
     ["Descrição", "Eventos"]),
    ("Trilhas", [("Link", "link"), ("Clima", "short")], []),
]


@transaction.atomic
def seed_campaign(campaign):
    for pos, (name, fields, tabs) in enumerate(DEFAULT_TYPES):
        rt = RecordType.objects.create(campaign=campaign, name=name, position=pos)
        for i, (label, kind) in enumerate(fields):
            FieldDef.objects.create(record_type=rt, label=label, kind=kind, position=i)
        for i, title in enumerate(tabs):
            TabDef.objects.create(record_type=rt, title=title, position=i)

from django import forms


class RecordForm(forms.Form):
    name = forms.CharField(label="Nome", max_length=160)
    group = forms.ModelChoiceField(label="Sub-aba da lista", queryset=None, required=False, empty_label="Nenhuma")

    def __init__(self, record_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = record_type.listgroup_set.order_by("position", "id")


class GroupChoiceForm(forms.Form):
    group = forms.ModelChoiceField(label="Sub-aba da lista", queryset=None, required=False, empty_label="Nenhuma")

    def __init__(self, record_type, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = record_type.listgroup_set.order_by("position", "id")


class TitleForm(forms.Form):
    title = forms.CharField(max_length=80)

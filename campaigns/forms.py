from django import forms

from .models import Campaign


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name"]
        labels = {"name": "Nome da campanha"}


class RecordTypeForm(forms.Form):
    name = forms.CharField(label="Nome do tipo", max_length=80)

    def __init__(self, campaign, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.campaign = campaign

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.campaign.recordtype_set.filter(name__iexact=name).exists():
            raise forms.ValidationError("Já existe um tipo com esse nome.")
        return name

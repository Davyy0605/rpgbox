import tempfile

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.utils.text import slugify

from campaigns.access import get_campaign

from .export import write_export


@login_required
def campaign_export(request, campaign_id):
    campaign = get_campaign(request.user, campaign_id)
    tmp = tempfile.TemporaryFile()
    write_export(campaign, tmp)
    tmp.seek(0)
    name = f"{slugify(campaign.name) or 'campanha'}.zip"
    return FileResponse(tmp, as_attachment=True, filename=name, content_type="application/zip")

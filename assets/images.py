import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 50_000_000
ALLOWED_FORMATS = ["JPEG", "PNG", "WEBP", "GIF"]
MAX_PIXELS_JPEG = 100_000_000
MAX_PIXELS_OTHER = 25_000_000


class InvalidFile(Exception):
    """Arquivo recusado; a mensagem é exibida ao usuário."""


@dataclass
class ProcessedImage:
    data: bytes
    thumb: bytes
    width: int
    height: int


def _webp(img):
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=80)
    return buf.getvalue()


def process_image(file):
    try:
        file.seek(0)
        img = Image.open(file, formats=ALLOWED_FORMATS)
        pixels = img.size[0] * img.size[1]  # lido do cabeçalho, antes de decodificar
        if pixels > (MAX_PIXELS_JPEG if img.format in ("JPEG", "MPO") else MAX_PIXELS_OTHER):
            raise InvalidFile("A imagem tem pixels demais. Reduza a resolução e envie de novo.")
        if img.format in ("JPEG", "MPO"):
            img.draft("RGB", (3200, 3200))
        img.seek(0)  # GIF animado: só o primeiro quadro
        img.load()
        img.thumbnail((1600, 1600))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        data = _webp(img)
        size = img.size
        img.thumbnail((400, 400))
        thumb = _webp(img)
    except InvalidFile:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, EOFError):
        raise InvalidFile("Não foi possível ler essa imagem. O arquivo parece corrompido.")
    return ProcessedImage(data, thumb, size[0], size[1])

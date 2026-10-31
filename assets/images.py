import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 50_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class InvalidFile(Exception):
    """Arquivo recusado; a mensagem é exibida ao usuário."""


@dataclass
class ProcessedImage:
    data: bytes
    thumb: bytes
    width: int
    height: int


def _webp(img, limit):
    img = img.copy()
    img.thumbnail((limit, limit))
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=80)
    return buf.getvalue(), img.size


def process_image(file):
    try:
        file.seek(0)
        img = Image.open(file)
        if img.format not in ALLOWED_FORMATS:
            raise InvalidFile("Imagem em formato não aceito. Use JPEG, PNG, WebP ou GIF.")
        img.seek(0)  # GIF animado: só o primeiro quadro
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        data, size = _webp(img, 1600)
        thumb, _ = _webp(img, 400)
    except InvalidFile:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, EOFError):
        raise InvalidFile("Não foi possível ler essa imagem. O arquivo parece corrompido.")
    return ProcessedImage(data, thumb, size[0], size[1])

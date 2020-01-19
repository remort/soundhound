from io import BytesIO

from PIL import Image
from PIL.Image import Image as ImageType

from app.config import THUMB_EDGE_LIMIT


def is_start_message(update):
    """Нужен на ранних стадиях обработки мессаджа чтобы удалить лок в редисе если чтото пошло не так."""
    if update.get('message'):
        if update['message'].get('text') in ('/start', '/reset'):
            return True
    return False


def resize_thumbnail(img_data: bytes, width: int, height: int) -> bytes:
    """
    Telegram в качестве thumbnail прнимает только квадратные картикни, с длиной стороны 320 px максимум.
    Подготовим полученную картинку если она не соответствует этим условиям.
    """
    if width < THUMB_EDGE_LIMIT and height < THUMB_EDGE_LIMIT:
        return img_data

    image: ImageType = Image.open(BytesIO(img_data))
    shortest_edge = min(image.size)

    left: int = (width - shortest_edge) / 2
    top: int = (height - shortest_edge) / 2
    right: int = (width + shortest_edge) / 2
    bottom: int = (height + shortest_edge) / 2

    image = image.crop((left, top, right, bottom))
    image = image.resize(size=(THUMB_EDGE_LIMIT, THUMB_EDGE_LIMIT))

    buf: BytesIO = BytesIO()
    image.save(buf, format='JPEG')

    return buf.getvalue()

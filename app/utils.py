from io import BytesIO

from PIL import Image
from PIL.Image import Image as ImageType


def is_start_message(update):
    """Нужен на ранних стадиях обработки мессаджа чтобы удалить лок в редисе если чтото пошло не так."""
    if update.get('message'):
        if update['message'].get('text') in ('/start', '/reset'):
            return True
    return False


def resize_thumbnail(img_data: bytes, width: int, height: int, edge_max_limit: int = 320) -> bytes:
    """
    TG API, InputMediaAudio: The thumbnail should be in JPEG format and less than 200 kB in size.
    A thumbnail‘s width and height should not exceed 320.
    Telegram в качестве thumbnail прнимает только квадратные картикни, с длиной стороны не больше 320 px.
    Подготовим полученную картинку если она не соответствует этим условиям.
    """
    if width < edge_max_limit and height < edge_max_limit:
        return img_data

    image: ImageType = Image.open(BytesIO(img_data))
    shortest_edge = min(image.size)

    left: int = (width - shortest_edge) / 2
    top: int = (height - shortest_edge) / 2
    right: int = (width + shortest_edge) / 2
    bottom: int = (height + shortest_edge) / 2

    image = image.crop((left, top, right, bottom))
    image = image.resize(size=(edge_max_limit, edge_max_limit))

    buf: BytesIO = BytesIO()
    image.save(buf, format='JPEG')

    return buf.getvalue()

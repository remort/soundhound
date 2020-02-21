from marshmallow import Schema
from marshmallow.fields import Boolean, Integer, List, Nested, String

from app.serializers.utils import Timestamp


class InlineQuery(Schema):
    pass


class ChosenInlineResult(Schema):
    pass


class ShippingQuery(Schema):
    pass


class PreCheckoutQuery(Schema):
    pass


class Poll(Schema):
    pass


class User(Schema):
    id = Integer()
    is_bot = Boolean()
    first_name = String()
    last_name = String(required=False)
    username = String(required=False)
    language_code = String(required=False)


class ChatPermissions(Schema):
    pass


class ChatPhoto(Schema):
    pass


class Chat(Schema):
    id = Integer()
    type = String()
    title = String(required=False)
    username = String(required=False)
    first_name = String(required=False)
    last_name = String(required=False)
    photo = Nested(ChatPhoto, required=False)
    description = String(required=False)
    invite_link = String(required=False)
    pinned_message = Nested(lambda: Chat(exclude=('pinned_message',)))
    permissions = Nested(ChatPermissions, required=False)
    sticker_set_name = String(required=False)
    can_set_sticker_set = Boolean(required=False)


class MessageEntity(Schema):
    type = String()
    offset = Integer()
    length = Integer()
    url = String(required=False)
    user = Nested(User, required=False)


class PhotoSize(Schema):
    file_id = String()
    file_unique_id = String()
    width = Integer()
    height = Integer()
    file_size = Integer(required=False)


class Audio(Schema):
    file_id = String()
    file_unique_id = String()
    duration = Integer()
    performer = String(required=False)
    title = String(required=False)
    mime_type = String(required=False)
    file_size = Integer(required=False)
    thumb = Nested(PhotoSize, required=False)


class File(Schema):
    file_id = String()
    file_unique_id = String()
    file_size = Integer(required=False)
    file_path = String(required=False)


class Voice(Schema):
    file_id = String()
    file_unique_id = String()
    duration = Integer()
    mime_type = String(required=False)
    file_size = Integer(required=False)


class Document(Schema):
    file_id = String()
    file_unique_id = String()
    thumb = Nested(PhotoSize, required=False)
    file_name = String(required=False)
    mime_type = String(required=False)
    file_size = Integer(required=False)


class Animation(Schema):
    file_id = String()
    file_unique_id = String()
    width = Integer(required=False)
    height = Integer(required=False)
    duration = Integer(required=False)
    thumb = Nested(PhotoSize, required=False)
    file_name = String(required=False)
    mime_type = String(required=False)
    file_size = Integer(required=False)


class Game(Schema):
    pass


class Sticker(Schema):
    pass


class Video(Schema):
    file_id = String()
    file_unique_id = String()
    width = Integer(required=False)
    height = Integer(required=False)
    duration = Integer(required=False)
    thumb = Nested(PhotoSize, required=False)
    mime_type = String(required=False)
    file_size = Integer(required=False)


class VideoNote(Schema):
    pass


class Contact(Schema):
    pass


class Location(Schema):
    pass


class Venue(Schema):
    pass


class Invoice(Schema):
    pass


class SuccessfulPayment(Schema):
    pass


class PassportData(Schema):
    pass


class LoginUrl(Schema):
    url = String(required=False)
    forward_text = String(required=False)
    bot_username = String(required=False)
    request_write_access = Boolean(required=False)


class CallbackGame(Schema):
    user_id = Integer()
    score = Integer()
    force = Boolean(required=False)
    disable_edit_message = Boolean(required=False)
    chat_id = Integer(required=False)
    message_id = Integer(required=False)
    inline_message_id = String(required=False)


class InlineKeyboardButton(Schema):
    text = String()
    url = String(required=False)
    login_url = LoginUrl()
    callback_data = String(required=False)
    switch_inline_query = String(required=False)
    switch_inline_query_current_chat = String(required=False)
    callback_game = CallbackGame()
    pay = Boolean(required=False)


class InlineKeyboardMarkup(Schema):
    inline_keyboard = List(List(Nested(InlineKeyboardButton())))


class Message(Schema):
    message_id = Integer()
    _from = Nested(User, required=False, data_key='from', attribute='from')
    date = Timestamp(format='timestamp')
    chat = Nested(Chat)

    forward_from = Nested(User, required=False)
    forward_from_chat = Nested(Chat, required=False)
    forward_from_message_id = Integer(required=False)
    forward_signature = String(required=False)
    forward_sender_name = String(required=False)
    forward_date = Timestamp(required=False, format='timestamp')

    reply_to_message = Nested(lambda: Message(exclude=('reply_to_message',)))
    edit_date = Timestamp(required=False, format='timestamp')
    media_group_id = String(required=False)
    author_signature = String(required=False)
    text = String(required=False)

    entities = List(Nested(MessageEntity, required=False))
    caption_entities = List(Nested(MessageEntity, required=False))

    audio = Nested(Audio, required=False)
    voice = Nested(Voice, required=False)
    document = Nested(Document, required=False)
    animation = Nested(Animation, required=False)
    game = Nested(Game, required=False)
    photo = List(Nested(PhotoSize, required=False))
    sticker = Nested(Sticker, required=False)
    video = Nested(Video, required=False)
    video_note = Nested(VideoNote, required=False)
    caption = String(required=False)
    contact = Nested(Contact, required=False)
    location = Nested(Location, required=False)
    venue = Nested(Venue, required=False)
    poll = Nested(Poll, required=False)
    new_chat_members = List(Nested(User, required=False))
    left_chat_member = Nested(User, required=False)
    new_chat_title = String(required=False)
    new_chat_photo = List(Nested(PhotoSize, required=False))
    delete_chat_photo = Boolean(required=False)
    group_chat_created = Boolean(required=False)
    supergroup_chat_created = Boolean(required=False)
    channel_chat_created = Boolean(required=False)
    migrate_to_chat_id = Integer(required=False)
    migrate_from_chat_id = Integer(required=False)
    pinned_message = Nested(lambda: Message(exclude=('pinned_message',)))
    invoice = Nested(Invoice, required=False)
    successful_payment = Nested(SuccessfulPayment, required=False)
    connected_website = String(required=False)
    passport_data = Nested(PassportData, required=False)
    reply_markup = Nested(InlineKeyboardMarkup, required=False)


class CallbackQuery(Schema):
    id = String()
    _from = Nested(User, required=False, data_key='from', attribute='from')
    message = Nested(Message, required=False)
    inline_message_id = String(required=False)
    chat_instance = String()
    data = String(required=False)
    game_short_name = String(required=False)


class Update(Schema):
    update_id = Integer()
    message = Nested(Message, required=False)
    edited_message = Nested(Message, required=False)
    channel_post = Nested(Message, required=False)
    edited_channel_post = Nested(Message, required=False)
    inline_query = Nested(InlineQuery, required=False)
    chosen_inline_result = Nested(ChosenInlineResult, required=False)
    callback_query = Nested(CallbackQuery, required=False)
    shipping_query = Nested(ShippingQuery, required=False)
    pre_checkout_query = Nested(PreCheckoutQuery, required=False)
    poll = Nested(Poll, required=False)

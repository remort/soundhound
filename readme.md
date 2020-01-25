## SoundHoundBot

Бот поможет в простых повседневных действиях с вашим аудио в Telegram.
Смотри `/info` в [Sound Hound bot](https://t.me/sound_hound_bot)

A little audio helper for your daily Telegram needs.
See `/info` in [Sound Hound bot](https://t.me/sound_hound_bot)

Feedback: @redahead.

## Запуск на dev-машине:

- Запустить ngrok: `ngrok http 7000` или nginx, проксирующий на `127.0.0.1:7000`.
- Наполнить `.env` константами `SERVER_NAME`, `PUBLIC_PORT` и `TOKEN`.
- Запустить проект `docker-compose up -d`.

`SERVER_NAME` и `PUBLIC_PORT` это домен и порт по которому будет доступен `webhook` для бота.

Telegram разрешает публиковать `webhook` для ботов только на портах `80`, `88`, `443` и `8443`.

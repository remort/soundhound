## Запуск на dev-машине:

- Запустить `ngrok http 7000`.
- Наполнить `.env` константами `SERVER_NAME`, `PUBLIC_PORT` и `TOKEN`.
- Запустить проект `docker-compose up -d`.

`SERVER_NAME` и `PUBLIC_PORT` это домен и порт по которому будет доступен webhook для бота.
Telegram разрешает публиковать webhook для ботов только на портах 80, 88, 443 и 8443

import logging
from asyncio import ensure_future, sleep as aiosleep, CancelledError, wait_for
from pprint import pprint

from actions_dict import actions
from audio import handle_file, MAX_DURATION
from botclass import bot

log = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')
TASK_TIMEOUT = 600
FILE_DOWNLOAD_TIMEOUT = 180

tasks = {}


async def create_user_task(sender):
    log.debug('in create task')
    clean_task(sender)

    result = await bot.send_action_list(sender)
    log.info(f'New sender: {sender}. Action list sent. Result is {result}')

    tasks[sender] = {
        "action_list_sent": True,
        "task_timer": ensure_future(task_timer(sender))
    }
    log.debug('task created')


async def task_timer(sender):
    try:
        await aiosleep(TASK_TIMEOUT)
    except CancelledError:
        log.info('Timer countdown was cancelled by us.')
        return

    log.info(f'Time is out for the task {sender}. Kill it.')
    await bot.send_message(sender, f'Time is out. You have {TASK_TIMEOUT} seconds to send file and action parameters.')

    clean_task(sender)


async def download_waiter():
    # Понять что и как делать если таймаут на загрузку файла истек.
    # Убивать таск и слать сообщение юзеру. Но в каком месте кода?
    try:
        await aiosleep(FILE_DOWNLOAD_TIMEOUT)
    except CancelledError:
        log.debug('File downloader waiter cancelled by us')
        return True
    log.debug('File downloader is out')
    return False


async def ask_for_action_parameters(sender, action):
    if action not in actions:
        log.error('unknown action')
    await bot.ask_action_parameters(sender, action)

    log.debug('In ask for action params')


def clean_task(sender):
    log.debug('clean task')
    if sender in tasks:
        # audio = tasks[sender].get('audio', {})

        tasks[sender]['task_timer'].cancel()

        # if audio.get('file_obj'):
        #     print('close file obj here')
        #     audio['file_obj'].close()
        # elif audio.get('file_name'):
        #     print('unlink file here')
        #     os.unlink(audio.get('file_name'))

        del (tasks[sender])


async def get_audio_file(sender, file_meta):
    tasks[sender]['audio_file_is_downloading'] = ensure_future(download_waiter())
    file_obj, file_suffix = await  get_file(sender, file_meta['file_id'], 'audio')
    # таска может уже не быть если таймер истек пока файл грузился.
    if sender not in tasks:
        return
    tasks[sender]['audio_file_is_downloading'].set_result(True)

    tasks[sender]['audio'] = file_meta
    # важно сохранять ссылку на temporary file object иначе он удалится
    tasks[sender]['audio']['file_obj'] = file_obj
    tasks[sender]['audio']['file_name'] = file_obj.name
    tasks[sender]['audio']['file_suffix'] = file_suffix.replace('.', '')

    log.debug(f'got audio file: {tasks[sender]}')
    await try_to_process_file(sender)


async def get_picture_file(sender, file_meta):
    tasks[sender]['picture_file_is_downloading'] = ensure_future(download_waiter())
    file_obj, file_suffix = await  get_file(sender, file_meta[1]['file_id'], 'picture')
    if sender not in tasks:
        return
    tasks[sender]['picture_file_is_downloading'].set_result(True)

    # важно сохранять ссылку на temporary file object иначе он удалится
    tasks[sender]['picture_file'] = file_obj
    tasks[sender]['parameters'] = {
        'file_name': file_obj.name,
        'file_suffix': file_suffix,
    }

    log.debug(f'got pic file: {tasks[sender]}')
    await try_to_process_file(sender)


async def get_file(sender, file_id, file_type):
    """
    Присланый файл из поллинга передается сюда для зарузки и обработки в try_to_process_file в соотв. с action
    file_type: 'audio' или 'picture'
    """

    await bot.send_message(
        sender,
        f'See you sent a file. Wait I download it from Telegram servers and process.'
    )
    file_obj, file_suffix = await bot.download_file(file_id, sender, file_type)
    if not file_obj:
        log.error('Unable to download file from TG CDN. Delete task.')
        clean_task(sender)
        return

    if sender not in tasks:
        log.error('File downloaded, but user still still has no task for some reason. Delete it all.')
        file_obj.close()
        clean_task(sender)
        return

    return file_obj, file_suffix


async def try_to_process_file(sender):
    """
        Пробуем обработать файл.
        Сценария выполнения таска от юзера два: Сначала загрузить файл а потом указать параметры и наоборот.
        Вызывается в обоих возможных случаях: когда пришел файл или пришли все параметры.
        Если нет действия, параметров или файла - сообщаем юзеру чего не хватает для выполлнения его задачи и выходим.
        Функция будет вызвана снова когда придут все параметры или файл.
    """
    action = tasks[sender].get('action')
    parameters = tasks[sender].get('parameters')
    audio_meta = tasks[sender].get('audio')

    # обрабатывать ситуацию что файл пришел а действия или параметров не выбрано. а именно:
    # - действия ему выслались в create_user_task, просить снова не надо
    # - действие могут и не прислать - удалять файл по саймауту (запускать корутину ?)
    # - или удалять файл и оповещать юзера
    if not action:
        await bot.send_message(
            sender,
            f'File is ready to be handled, send an action please.'
        )
        return

    # возможна ситуация что файл отправили но он еще не дошел с tg cdn. надо проверять флаг file_is_downloading
    if not parameters:
        await bot.send_message(
            sender,
            f'File is ready to be handled, action is set, send parameters.'
        )
        return

    if not audio_meta:
        if tasks[sender].get('audio_file_is_downloading'):
            if not tasks[sender]['audio_file_is_downloading'].result():
                log.debug('Audio file is downloading, wait for it, send some text to user to inform him')
                result = await wait_for(tasks[sender]['audio_file_is_downloading'], FILE_DOWNLOAD_TIMEOUT)
                if not result:
                    clean_task(sender)
                    return
        else:
            await bot.send_message(
                sender,
                f'Audio file is not uploaded, upload it now.'
            )
            return

    if action == 'set_cover':
        # не проверяем тут кейс с отсутсвием футуры на загрузку картинки так как прийти сюда можно только из get_file()
        # а не из parse_parameter() как в случае с action требующих параметров
        if tasks[sender].get('picture_file_is_downloading'):
            if not tasks[sender]['picture_file_is_downloading'].result():
                log.debug('picture file is downloading, wait for it')
                result = await wait_for(tasks[sender]['picture file is downloading'], FILE_DOWNLOAD_TIMEOUT)
                if not result:
                    clean_task(sender)
                    return

    # По причине двойственности прохождения сценария юзером тут так же вызываем валидатор параметров
    # Вызванный тут, валидатор сможет проверить параметры согласно метаданным загруженного файла (duration/mimetype)
    # Если фэйл - возврат с сообщением о конкретной ошибке юзеру. Юзер сможет доотправить верные параметры.
    if action in ('crop', 'makevoice'):
        if not await validate_duration_parameters(sender):
            return

    # Отменяем таймер ввода данных юзером для таска так как теперь у нас есть файл и параметры.
    # Обработка, отправка результата и отмена таска далее зависят от нас.
    # Тут есть гонка при загрузке файла с TG CDN. Пока он грузится, таймер истекает, таск уничтожается.
    # Но после загрузки создастся новый таск с загруженным файлом и будут запрошены параметры заново.
    tasks[sender]['task_timer'].cancel()

    audio = await handle_file(audio_meta, action, parameters)
    if not audio:
        await bot.send_message(
            sender,
            f'Unable to handle this file for some reason, try another one.'
        )
        clean_task(sender)
        return

    status = await bot.upload_file(sender, audio, action == 'makevoice', tasks[sender].get('duration'))
    if not status:
        await bot.send_message(
            sender,
            f'Unable to upload processed file to TG CDN.'
        )
        clean_task(sender)
        return

    clean_task(sender)
    return


async def validate_duration_parameters(sender):
    parameters = tasks[sender].get('parameters')
    if parameters['start_time'] > parameters['end_time']:
        await bot.send_message(
            sender,
            f"Second time mark ({parameters['end_time']}) should greater than first one ({parameters['start_time']})"
            f"\nResend parameters please."
        )
        tasks[sender]['parameters'] = None
        return False

    audio_meta = tasks[sender].get('audio')
    if not audio_meta:
        log.info('Validator has no audio meta to validate duration')
        return True

    duration = audio_meta['duration']
    if not duration:
        log.error('No duration')
    for key, param in parameters.items():
        if not param <= duration:
            await bot.send_message(
                sender,
                f'Parameter {param} mismatch audio file duration {duration}.\nResend parameters please.'
            )
            tasks[sender]['parameters'] = None
            return False

    tasks[sender]['duration'] = parameters['end_time'] - parameters['start_time']
    return True


async def validate_makevoice_parameters(sender):
    parameters = tasks[sender].get('parameters')
    duration = parameters['end_time'] - parameters['start_time']
    if duration >= MAX_DURATION:
        await bot.send_message(
            sender,
            f'Maximum duration of voice audio fragment is 250 seconds. Yours: {duration} seconds.'
        )
        parameters.pop()
        return False
    return True


async def parse_parameter(sender, parameter):
    if sender not in tasks:
        log.error('Parameters received but sender task is accidentally become empty')
        return
    action = tasks[sender].get('action')
    if not action:
        log.error('Parameters received but sender task contains no action')
        clean_task(sender)
        return

    # первично в дикте юзера параметры задаются тут
    if not tasks[sender].get('parameters'):
        tasks[sender]['parameters'] = {}
    parameters = tasks[sender]['parameters']

    # Выйдем когда параметры уже прислали и продолжают слать. А мы уже ожидаем файл или обрабатываем его.
    if len(parameters) == len(actions.get(action).get('params')):
        await bot.send_message(sender, 'Parameters are already set. Send file if not yet.')
        return

    if action in ('crop', 'makevoice'):
        if not parameters:
            incoming_parameters = parameter.split('-')
            if not 2 >= len(incoming_parameters) >= 1:
                await bot.send_message(
                    sender,
                    'Invalid parameters count. Please send two integers delimited by "-" or one integer.'
                )
                return
            for sec in incoming_parameters:
                try:
                    sec = sec.strip()
                except ValueError:
                    await bot.send_message(sender, 'Parameter is invalid')
                if incoming_parameters.index(sec) == 0:
                    parameters['start_time'] = int(sec)
                if incoming_parameters.index(sec) == 1:
                    parameters['end_time'] = int(sec)

            if len(parameters) < 2:
                await bot.send_message(sender, 'Send second time mark please.')

        elif len(parameters) == 1:
            log.info('start eating 2nd parameter')
            try:
                parameter = int(parameter.strip())
            except ValueError:
                await bot.send_message(sender, 'Parameter is invalid')
                return
            parameters['end_time'] = parameter

        # Если у нас набралось 2 параметра - провалидируем и запустим обработку файла.
        # Если нет - выйдем, из поллинга придет второй параметр.
        if len(parameters) == 2:
            if not await validate_duration_parameters(sender):
                return
            if action == 'makevoice':
                if not await validate_makevoice_parameters(sender):
                    return
            await bot.send_message(
                sender,
                'Parameters are set. Trying to process file.'
            )
            await try_to_process_file(sender)


async def dispatch(updates):
    # TODO создать класс-интерфейс для работы с диктом состояния тасков юзеров
    last_update_id = None
    results = updates.get('result')
    if not results:
        return last_update_id

    for update in results:
        if 'message' in update:
            message = update['message']
            sender = message['from']['id']
            if sender not in tasks or message.get('text') == '/start':
                await create_user_task(sender)
            if message.get('text') and not (message.get('audio') and not message.get('photo')):
                if tasks[sender].get('action'):
                    ensure_future(parse_parameter(sender, message['text']))
            elif message.get('photo'):
                ensure_future(get_picture_file(sender, message['photo']))
            elif message.get('audio'):
                ensure_future(get_audio_file(sender, message['audio']))

        elif 'callback_query' in update:
            sender = update['callback_query']['from']['id']
            action = update['callback_query']['data']
            if action:
                if not tasks[sender].get('action'):
                    tasks[sender]['action'] = action
                    ensure_future(ask_for_action_parameters(sender, action))
                else:
                    await bot.send_message(sender, 'Action already set. Send "/start" to reset current task')
        else:
            log.error('Unknown bot message type, body is')
            pprint(update)

        last_update_id = update['update_id']

        log.info(f'Tasks dict is: {tasks}')

    if last_update_id:
        return last_update_id + 1
    return last_update_id

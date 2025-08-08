import os
import time

import yt_dlp
import asyncio
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
# Исправленный импорт исключений для aiogram 3.10+
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from dotenv import load_dotenv

load_dotenv()
# Настройки
API_TOKEN = os.getenv('BOT_TOKEN')  # Замените на ваш токе
DOWNLOADS_DIR = 'downloads'
MAX_CONCURRENT_DOWNLOADS = 5
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# Инициализация
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# Состояния для FSM
class DownloadStates(StatesGroup):
    main_menu = State()        # Главное меню
    waiting_for_url = State()  # Ожидание ссылки
    downloading = State()      # Процесс загрузки

def get_main_menu():
    """Создает клавиатуру главного меню"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎥 Скачать видео"),
                KeyboardButton(text="🎵 Скачать аудио")
            ],
            [
                KeyboardButton(text="ℹ️ Помощь"),
                KeyboardButton(text="🚫 Отмена")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def is_youtube_url(url):
    """Проверяет, является ли ссылка YouTube-ссылкой"""
    if not url:
        return False
    youtube_domains = ['youtube.com', 'youtu.be', 'www.youtube.com']
    return any(domain in url.lower() for domain in youtube_domains)

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Сброс состояния и показ главного меню"""
    await state.clear()
    await state.set_state(DownloadStates.main_menu)
    
    await message.answer(
        "👋 Добро пожаловать в YouTube Downloader!\n\n"
        "Выберите действие с помощью кнопок ниже:",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "ℹ️ Помощь")
async def show_help(message: types.Message):
    """Показывает справочную информацию"""
    await message.answer(
        "ℹ️ <b>Как пользоваться ботом:</b>\n\n"
        "1. Нажмите на кнопку 'Скачать видео' или 'Скачать аудио'\n"
        "2. Отправьте ссылку на YouTube видео\n"
        "3. Дождитесь обработки и получите файл\n\n"
        "⚠️ <b>Ограничения:</b>\n"
        "- Макс. длительность видео: 1 час\n"
        "- Макс. размер файла: 1.9 ГБ\n"
        "- Не поддерживает приватные видео",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "🚫 Отмена")
async def cancel_process(message: types.Message, state: FSMContext):
    """Сбрасывает текущее состояние"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "❌ Нет активного процесса для отмены",
            reply_markup=get_main_menu()
        )
        return
    
    await state.clear()
    await state.set_state(DownloadStates.main_menu)
    
    await message.answer(
        "✅ Процесс отменен. Вы в главном меню.",
        reply_markup=get_main_menu()
    )

@router.message(F.text == "🎥 Скачать видео")
async def download_video(message: types.Message, state: FSMContext):
    """Переход в состояние ожидания ссылки для видео"""
    await state.set_state(DownloadStates.waiting_for_url)
    await state.update_data(download_type="video")
    
    await message.answer(
        "📌 Отправьте ссылку на YouTube видео\n\n",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚫 Отмена")]],
            resize_keyboard=True
        )
    )

@router.message(F.text == "🎵 Скачать аудио")
async def download_audio(message: types.Message, state: FSMContext):
    """Переход в состояние ожидания ссылки для аудио"""
    await state.set_state(DownloadStates.waiting_for_url)
    await state.update_data(download_type="audio")
    
    await message.answer(
        "📌 Отправьте ссылку на YouTube видео\n\n",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚫 Отмена")]],
            resize_keyboard=True
        )
    )

@router.message(DownloadStates.waiting_for_url, F.text)
async def process_url(message: types.Message, state: FSMContext):
    """Обработка полученной ссылки"""
    url = message.text.strip()
    
    # Проверка на отмену
    if url == "🚫 Отмена":
        await state.clear()
        await state.set_state(DownloadStates.main_menu)
        await message.answer(
            "✅ Процесс отменен. Вы в главном меню.",
            reply_markup=get_main_menu()
        )
        return
    
    # Проверка YouTube-ссылки
    if not is_youtube_url(url):
        await message.answer(
            "❌ Пожалуйста, отправьте корректную ссылку на YouTube видео.\n"
            "Пример: https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🚫 Отмена")]],
                resize_keyboard=True
            )
        )
        return
    
    # Проверка активной загрузки
    current_state = await state.get_state()
    if current_state == DownloadStates.downloading.state:
        await message.answer(
            "❗ У вас уже есть активная загрузка. Пожалуйста, дождитесь завершения.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🚫 Отмена")]],
                resize_keyboard=True
            )
        )
        return
    
    # Сохраняем данные и переходим к загрузке
    await state.set_state(DownloadStates.downloading)
    data = await state.get_data()
    format_type = data.get('download_type', 'video')
    
    # Генерируем уникальное имя файла
    user_id = message.from_user.id
    timestamp = int(time.time())
    output_template = f"{DOWNLOADS_DIR}/{user_id}_{timestamp}"
    
    # Отправляем первое сообщение о начале загрузки
    try:
        status_msg = await bot.send_message(
            user_id, 
            f"⏳ Загружаю {format_type}... Это может занять некоторое время."
        )
        await state.update_data(status_msg_id=status_msg.message_id)
    except Exception as e:
        await state.clear()
        await state.set_state(DownloadStates.main_menu)
        await message.answer(
            f"❌ Не удалось начать загрузку: {str(e)[:100]}",
            reply_markup=get_main_menu()
        )
        return
    
    # Настройки yt-dlp
    ydl_opts = {
        'outtmpl': f'{output_template}.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'format': 'bestvideo+bestaudio/best' if format_type == 'video' else 'bestaudio/best',
        'socket_timeout': 15,
        'retries': 3,
    }
    
    # Дополнительные настройки для аудио
    if format_type == 'audio':
        ydl_opts.update({
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    
    file_path = None
    try:
        # Получаем информацию о видео
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'download')
                duration = info.get('duration', 0)
                
                # Проверка длины видео
                if duration > 3600:  # 1 час
                    raise Exception("Видео слишком длинное (более 1 часа)")
            except Exception as e:
                raise Exception(f"Не удалось получить информацию: {str(e)[:100]}")
        
        # Загружаем файл
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Определяем путь к файлу
        if format_type == 'audio':
            file_path = f"{output_template}.mp3"
        else:
            for ext in ['mp4', 'mkv', 'webm']:
                potential_path = f"{output_template}.{ext}"
                if os.path.exists(potential_path):
                    file_path = potential_path
                    break
        
        # Проверка существования файла
        if not file_path or not os.path.exists(file_path):
            raise Exception("Файл не был загружен")
        
        # Проверка размера
        file_size = os.path.getsize(file_path)
        if file_size > 1.9 * 1024 * 1024 * 1024:  # 1.9 ГБ
            raise Exception("Видео слишком большое для отправки через Telegram (более 1.9 ГБ)")
        
        # Добавляем небольшую задержку перед отправкой
        await asyncio.sleep(1)
        
        # Отправляем файл
        try:
            if format_type == 'audio':
                await bot.send_audio(
                    user_id, 
                    FSInputFile(file_path), 
                    caption=f"🎧 {title[:90]}..." if len(title) > 90 else f"🎧 {title}",
                    timeout=60
                )
            else:
                await bot.send_video(
                    user_id, 
                    FSInputFile(file_path), 
                    caption=f"🎬 {title[:90]}..." if len(title) > 90 else f"🎬 {title}",
                    timeout=120
                )
        except TelegramRetryAfter as e:  # Исправлено здесь
            await asyncio.sleep(e.retry_after)
            if format_type == 'audio':
                await bot.send_audio(user_id, FSInputFile(file_path), caption=f"🎧 {title}")
            else:
                await bot.send_video(user_id, FSInputFile(file_path), caption=f"🎬 {title}")
        except TelegramAPIError as e:
            raise Exception(f"Ошибка отправки: {str(e)[:100]}")
        
        # Обновляем статус
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=status_msg.message_id,
            text=f"✅ Загрузка завершена!\n\n📌 {title[:50]}{'...' if len(title) > 50 else ''}"
        )
    
    except Exception as e:
        error_msg = str(e)[:200]
        try:
            data = await state.get_data()
            status_msg_id = data.get('status_msg_id')
            
            if status_msg_id:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=status_msg_id,
                    text=f"❌ Ошибка: {error_msg}"
                )
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg}")
        except:
            try:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg}")
            except:
                pass
    
    finally:
        # Очистка состояния и временных файлов
        await state.clear()
        await state.set_state(DownloadStates.main_menu)
        
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

@router.message(DownloadStates.main_menu, F.text)
async def main_menu_handler(message: types.Message):
    """Обработка неизвестных команд в главном меню"""
    await message.answer(
        "❌ Неизвестная команда. Пожалуйста, используйте кнопки ниже:",
        reply_markup=get_main_menu()
    )

@router.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    """Обработка всех остальных сообщений"""
    current_state = await state.get_state()
    
    if current_state == DownloadStates.waiting_for_url.state:
        await message.answer(
            "❌ Пожалуйста, отправьте корректную YouTube-ссылку или нажмите 'Отмена'",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🚫 Отмена")]],
                resize_keyboard=True
            )
        )
    else:
        await state.clear()
        await state.set_state(DownloadStates.main_menu)
        await message.answer(
            "👋 Добро пожаловать в YouTube Downloader!\n\n"
            "Выберите действие с помощью кнопок ниже:",
            reply_markup=get_main_menu()
        )

async def main():
    """Запуск бота с безопасными настройками"""
    print("Бот запущен. Ожидание сообщений...")
    
    # Настройка лимитов для предотвращения перегрузки
    await dp.start_polling(
        bot,
        skip_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
        polling_timeout=10
    )

if __name__ == "__main__":
    asyncio.run(main())

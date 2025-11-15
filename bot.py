import asyncio
import logging
import os  # <-- Імпортуємо os для роботи з 'секретами'
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

# Завантаження змінних середовища з .env файлу
from dotenv import load_dotenv
load_dotenv()

# Імпортуємо нашу функцію з файлу
from file_reader import read_message

# --- Нове: Імпорт та налаштування OpenAI ---
try:
    from openai import AsyncOpenAI
except ImportError:
    print("----------------------------------------------------")
    print("ПОПЕРЕДЖЕННЯ: Бібліотеку 'openai' не знайдено.")
    print("Якщо ви хочете використовувати функції ШІ,")
    print("виконайте: pip install openai")
    print("----------------------------------------------------")
    AsyncOpenAI = None  # Ставимо "заглушку"

# --- Завантаження текстів у змінні (без змін) ---
MSG_START = read_message('msg_start')
MSG_GREETING = read_message('msg_greeting')
MSG_ABOUT = read_message('msg_about')
MSG_RETURN = read_message('msg_return')
MSG_SITE_URL = read_message('msg_site_url')
BTN_HELLO = read_message('btn_hello')
BTN_ABOUT = read_message('btn_about')
BTN_RETURN = read_message('btn_return')
BTN_SITE = read_message('btn_site')

# --- Константи та налаштування ---
# Тепер всі ключі читаються з 'секретів'
BOT_TOKEN = os.environ.get('BOT_TOKEN')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
ASSISTANT_ID = os.environ.get('ASSISTANT_ID')  # <-- ОНОВЛЕНО

# --- Перевірка ключів ---
if not BOT_TOKEN:
    logging.critical("ПОМИЛКА: Не знайдено BOT_TOKEN. Переконайтесь, що ви додали його в Secrets.")
    exit()

if not OPENAI_API_KEY:
    logging.warning("ПОПЕРЕДЖЕННЯ: Не знайдено OPENAI_API_KEY. Функції ШІ будуть вимкнені.")

if not ASSISTANT_ID:
    logging.warning("ПОПЕРЕДЖЕННЯ: Не знайдено ASSISTANT_ID. Функції ШІ будуть вимкнені.")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# --- Ініціалізація бота ---
# Використовуємо MemoryStorage для простого зберігання історії діалогу в RAM
dp = Dispatcher(storage=MemoryStorage())
bot = Bot(token=BOT_TOKEN)

# Ініціалізація OpenAI клієнта (тільки якщо всі ключі є)
if OPENAI_API_KEY and AsyncOpenAI and ASSISTANT_ID:
    logging.info(f"Ключ OpenAI та Assistant ID ({ASSISTANT_ID[:4]}...) знайдено. Активую режим ШІ-асистента.")
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    logging.warning("Один або декілька ключів OpenAI відсутні. Бот працюватиме в базовому режимі (лише кнопки).")
    openai_client = None

# --- Клавіатури (без змін) ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_HELLO)],
        [KeyboardButton(text=BTN_RETURN)],
        [KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_SITE)]
    ],
    resize_keyboard=True
)

# --- Обробники команд (без змін) ---
@dp.message(Command("start"))
async def handle_start(message: types.Message):
    await message.answer(MSG_START, reply_markup=main_keyboard)

@dp.message(lambda message: message.text == BTN_HELLO)
async def handle_hello_button(message: types.Message):
    await message.answer(MSG_GREETING)

@dp.message(lambda message: message.text == BTN_ABOUT)
async def handle_about_button(message: types.Message):
    await message.answer(MSG_ABOUT)

@dp.message(lambda message: message.text == BTN_RETURN)
async def handle_return_button(message: types.Message):
    await message.answer(MSG_RETURN)

@dp.message(lambda message: message.text == BTN_SITE)
async def handle_site_button(message: types.Message):
    await message.answer(MSG_SITE_URL)

# --- Обробник для ChatGPT (Assistants API) ---
async def handle_chat(message: types.Message, state: FSMContext):
    if not openai_client:
        await message.answer("Вибачте, функція чату зараз недоступна.")
        return

    await bot.send_chat_action(message.chat.id, action="typing")

    try:
        user_data = await state.get_data()
        thread_id = user_data.get('thread_id')

        if not thread_id:
            thread = await openai_client.beta.threads.create()
            thread_id = thread.id
            await state.update_data(thread_id=thread_id)
            logging.info(f"Створено новий тред {thread_id} для користувача {message.from_user.id}")

        await openai_client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message.text
        )

        run = await openai_client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID  # <-- Використовуємо змінну
        )

        status = run.status
        while status in ['queued', 'in_progress']:
            await asyncio.sleep(0.5)
            run = await openai_client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            status = run.status

        if status == 'completed':
            messages = await openai_client.beta.threads.messages.list(
                thread_id=thread_id,
                limit=1,
                order='desc'
            )

            response = messages.data[0]
            if response.role == 'assistant' and response.content[0].type == 'text':
                response_text = response.content[0].text.value
                await message.answer(response_text)
            else:
                logging.error("Отримано не-текстову або не-асистент відповідь")
                await message.answer("Вибачте, сталася дивна помилка при отриманні відповіді.")

        else:
            logging.error(f"Run {run.id} завершився зі статусом {status}. Деталі: {run.last_error}")
            await message.answer(f"Вибачте, сталася помилка під час обробки. Статус: {status}")

    except Exception as e:
        logging.error(f"Критична помилка в handle_chat: {e}")
        await message.answer("Вибачте, сталася непередбачувана помилка. Спробуйте пізніше.")

# --- Реєстрація обробників ---
def register_handlers():
    # Реєструємо базові обробники
    dp.message.register(handle_start, Command("start"))
    dp.message.register(handle_hello_button, lambda message: message.text == BTN_HELLO)
    dp.message.register(handle_about_button, lambda message: message.text == BTN_ABOUT)
    dp.message.register(handle_return_button, lambda message: message.text == BTN_RETURN)
    dp.message.register(handle_site_button, lambda message: message.text == BTN_SITE)

    # Реєструємо обробник чату ТІЛЬКИ ЯКЩО є ключ
    # і ставимо його останнім, щоб він ловив весь текст,
    # який не "збігся" з кнопками
    if openai_client:
        dp.message.register(handle_chat)  # Без фільтрів, ловить увесь текст

# --- Запуск бота ---
async def main():
    register_handlers()  # Реєструємо наші обробники
    logging.info("Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot was stopped manually.")

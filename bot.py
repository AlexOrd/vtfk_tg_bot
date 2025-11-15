import asyncio
import logging
import os  # <-- Імпортуємо os для роботи з 'секретами'
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage  # <-- Додано для обробки історії

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
BOT_TOKEN = os.environ.get('BOT_TOKEN')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')  # <-- Нове: читаємо ключ OpenAI

# Промпт для вашого "знавця ВТФК"
VTFK_SYSTEM_PROMPT = """
Ти - корисний ШІ-асистент, 'Знавець ВТФК'. 
Ти спілкуєшся зі студентом Вінницького технічного фахового коледжу (ВТФК).
Відповідай на питання, пов'язані з навчанням, програмуванням, комп'ютерними дисциплінами. 
Будь привітним, але професійним. 
Якщо питання не стосується навчання або коледжу, ввічливо нагадай, що твоя спеціалізація - допомога студентам ВТФК.
Відповідай українською мовою.
"""

# Перевірка токена бота
if not BOT_TOKEN:
    logging.critical("ПОМИЛКА: Не знайдено BOT_TOKEN. Переконайтесь, що ви додали його в Secrets.")
    exit()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# --- Ініціалізація бота ---
# Використовуємо MemoryStorage для простого зберігання історії діалогу в RAM
dp = Dispatcher(storage=MemoryStorage())
bot = Bot(token=BOT_TOKEN)

# Ініціалізація OpenAI клієнта (тільки якщо є ключ)
if OPENAI_API_KEY and AsyncOpenAI:
    logging.info("Ключ OpenAI знайдено. Активую режим ШІ-асистента.")
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
else:
    logging.warning("Ключ OPENAI_API_KEY не знайдено. Бот працюватиме в базовому режимі (лише кнопки).")
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

# --- Новий обробник для ChatGPT ---
async def handle_chat(message: types.Message, state: types.Message):
    # Цей обробник спрацює, тільки якщо openai_client ініціалізовано
    if not openai_client:
        # Можна нічого не відповідати, або:
        await message.answer("Вибачте, функція чату зараз недоступна.")
        return

    # Показуємо "друкує..."
    await bot.send_chat_action(message.chat.id, action="typing")

    try:
        # (Проста версія без історії)
        # Ми просто відправляємо системний промпт + нове повідомлення
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Використовуємо нову, швидку та дешеву модель
            messages=[
                {"role": "system", "content": VTFK_SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ],
            temperature=0.7
        )
        response_text = completion.choices[0].message.content
        await message.answer(response_text)

    except Exception as e:
        logging.error(f"Помилка при запиті до OpenAI: {e}")
        await message.answer("Вибачте, сталася помилка при обробці вашого запиту. Спробуйте пізніше.")

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

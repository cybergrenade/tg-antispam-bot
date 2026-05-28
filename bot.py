import aiosqlite
import asyncio
import logging
import torch
import time
import random
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
from html import escape
from transformers import AutoTokenizer, AutoModelForSequenceClassification

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Ошибка: Токен бота не найден! Проверьте файл .env")

# Путь к модели на Hugging Face
MODEL_PATH = "super-apple/spam-classifier-ru"

logging.basicConfig(level=logging.INFO)

print("Загрузка модели в память...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH)
model.eval() 
print("Модель готова к работе!")

def check_if_spam(text: str) -> bool:
    """
    Функция пропускает текст через нейросеть и возвращает True, если это спам.
    """
    if not text:
        return False
        
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=128)

    with torch.no_grad():
        outputs = model(**inputs)

    logits = outputs.logits
    predicted_classId = torch.argmax(logits, dim=-1).item()
    
    return predicted_classId == 1


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Словарь для временного хранения цепочек сообщений
# Формат: {user_id: {"text": "Фраза 1. Фраза 2", "message_ids": [12, 13], "last_time": 1715000000.0}}
user_buffer = {}
BUFFER_WINDOW = 5.0  # Окно времени для склейки сообщений (в секундах)

# Словарь капч: храним тех, кто сейчас проходит проверку
# Формат: {user_id: {"answer": "9", "captcha_msg_id": 12345}}
active_captchas = {}
CAPTCHA_TIME = 15 # Время, которое мы отводим пользователю на решение капчи (в секндах)

#Название файла базы данных
DB_NAME = "bot_stats.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, 
                user_id INTEGER,
                action TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

async def log_action(chat_id: int, user_id: int, action: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO logs (chat_id, user_id, action) VALUES (?, ?, ?)", 
            (chat_id, user_id, action)
        )
        await db.commit()

@dp.message(Command("stats"))
async def show_statistics(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in ['creator', 'administrator']:
            return 
    except Exception:
        return
        
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM logs WHERE action = 'spam_deleted' AND chat_id = ?", 
            (chat_id,)
        ) as cursor:
            spam_count = (await cursor.fetchone())[0]
            
        async with db.execute(
            "SELECT COUNT(*) FROM logs WHERE action = 'user_banned_captcha' AND chat_id = ?", 
            (chat_id,)
        ) as cursor:
            banned_count = (await cursor.fetchone())[0]

    if spam_count == 0 and banned_count == 0:
        await message.answer("📊 Статистика для этого чата пока пуста.")
        return

    dashboard_text = (
        f"📊 **Аналитика чата: {message.chat.title}**\n\n"
        f"🗑 Удалено спам-сообщений: **{spam_count}**\n"
        f"⛔️ Выдано банов: **{banned_count}**\n\n"
        "_Система работает в штатном режиме._ 🟢"
    )
    
    await message.answer(dashboard_text, parse_mode="Markdown")


@dp.message(F.text)
@dp.edited_message(F.text)
async def handle_group_messages(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Иммунитет для админов
    # Запрашиваем информацию о пользователе в конкретном чате
    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        # Если это создатель админ - игнорируем его сообщения
        if chat_member.status in ['creator', 'administrator']:
            return 
    except Exception as e:
        logging.error(f"Не удалось получить статус пользователя {user_id}: {e}")
   
    # Формируем обращение к пользователю
    if message.from_user.username:
        user_mention = f"@{message.from_user.username}"
    else:
        safe_name = escape(message.from_user.first_name)
        user_mention = f'<a href="tg://user?id={user_id}">{safe_name}</a>'
    
    # Проверка на капчу
    if user_id in active_captchas:
        correct_answer = active_captchas[user_id]["answer"]
        captcha_msg_id = active_captchas[user_id]["captcha_msg_id"]
        
        # Проверяем, правильный ли ответ написал пользователь
        if message.text.strip() == correct_answer:
            # Если да, то человек доказал, что он не бот.
            del active_captchas[user_id]
            
            try:
                await message.delete() # Удаляем сам ответ (цифру), чтобы чат был чистым
                await bot.delete_message(chat_id, captcha_msg_id) # Удаляем вопрос капчи
                
                # Отправляем сообщение об успехе и удаляем его через 3 секунды
                success_msg = await message.answer(f"{user_mention}, проверка пройдена. Извините за беспокойство!", parse_mode="HTML")
                await asyncio.sleep(3)
                await success_msg.delete()
            except Exception:
                pass
        else:
            # Написал неправильный ответ или продолжает спамить ссылками
            # Удаляем каждое из его сообщений и ждем, пока сработает таймер
            try:
                await message.delete()
            except Exception:
                pass
                
        # Дальше текст на спам не проверяем, пока висит капча
        return 
 

    
    current_time = time.time()
    # Склеиваем сообщения, написанные с интервалом, не превышающим установленный нами в переменной BUFFER_WINDOW
    if user_id in user_buffer:
        time_diff = current_time - user_buffer[user_id]["last_time"]
        if time_diff <= BUFFER_WINDOW:
            user_buffer[user_id]["text"] += f" {message.text}"
            user_buffer[user_id]["message_ids"].append(message.message_id)
            user_buffer[user_id]["last_time"] = current_time
        else:
            user_buffer[user_id] = {"text": message.text, "message_ids": [message.message_id], "last_time": current_time}
    else:
        user_buffer[user_id] = {"text": message.text, "message_ids": [message.message_id], "last_time": current_time}
        
    combined_text = user_buffer[user_id]["text"]
    
    # Проверяем нейросетью склеенный текст
    is_spam = check_if_spam(combined_text)
    
    if is_spam:
        # Удаляем все сообщения, которые в совокупности образуют спам
        for msg_id in user_buffer[user_id]["message_ids"]:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                await log_action(chat_id, user_id, "spam_deleted")
            except Exception:
                pass
                
        user_buffer.pop(user_id, None)
        
        # Проверка на бота: выдаем капчу
        # Генерируем простой пример
        a = random.randint(1, 10)
        b = random.randint(1, 10)
        answer = str(a + b)
        
        captcha_text = f"{user_mention}, сработал антиспам-фильтр! 🤖\nРеши пример, чтобы доказать, что ты человек: {a} + {b} = ?\nУ тебя {CAPTCHA_TIME} секунд, иначе бан."
        captcha_msg = await message.answer(captcha_text, parse_mode="HTML")
        
        active_captchas[user_id] = {
            "answer": answer,
            "captcha_msg_id": captcha_msg.message_id
        }
        
        # Запускаем таймер в фоновом режиме (он кикнет юзера через CAPTCHA_TIME секунд, если тот не ответит)
        asyncio.create_task(captcha_timer(chat_id, user_id, captcha_msg.message_id))

async def cleanup_buffer():
    """
    Фоновая задача для очистки старых записей из памяти.
    Запускается каждые 60 секунд.
    """
    while True:
        await asyncio.sleep(60)
        
        current_time = time.time()
        users_to_delete = []
        
        for user_id, data in user_buffer.items():
            if current_time - data["last_time"] > 60:
                users_to_delete.append(user_id)
                
        for user_id in users_to_delete:
            del user_buffer[user_id]
            

async def captcha_timer(chat_id: int, user_id: int, captcha_msg_id: int):
    """
    Ждет CAPTCHA_TIME секунд. Если пользователь всё ещё в словаре active_captchas, 
    значит он не решил пример — баним его.
    """
    await asyncio.sleep(CAPTCHA_TIME)
    
    if user_id in active_captchas:
        del active_captchas[user_id]
        
        try:
            await bot.ban_chat_member(chat_id, user_id)
            await log_action(chat_id, user_id, "user_banned_captcha")
            logging.info(f"Пользователь {user_id} забанен за провал капчи.")
            
            await bot.delete_message(chat_id, captcha_msg_id)
        except Exception as e:
            logging.error(f"Ошибка при бане пользователя {user_id}: {e}")

async def main():
    print("Инициализация базы данных...")
    await init_db()

    print("Запуск фоновых процессов...")
    asyncio.create_task(cleanup_buffer())

    print("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
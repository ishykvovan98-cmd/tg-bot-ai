import http.server
import threading
import os
import httpx
import asyncio
import urllib.parse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

load_dotenv()

bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
dp = Dispatcher()

# История диалога (хранится в памяти, сбрасывается при перезапуске)
chat_history = {}

def get_smart_prompt(user_name: str):
    return (
        f"Тебя зовут Боб. Ты дерзкий, неформальный друг. "
        f"Ты общаешься с человеком по имени {user_name}. "
        f"Обращайся к нему по имени, когда это уместно, не каждый раз, чтобы не быть назойливым. "
        f"Отвечай кратко, с иронией, сарказмом и живым сленгом. "
        f"Если контекст позволяет, используй мат для акцента. "
        f"Не будь официозным. Отвечай только на русском."
    )

async def get_ai_reply(user_id: str, message: str, user_name: str) -> str:
    # Если это первый раз общаемся — создаем историю
    if user_id not in chat_history:
        # Динамический промт с именем!
        chat_history[user_id] = [
            {"role": "system", "content": get_smart_prompt(user_name)}
        ]
    
    # Добавляем сообщение пользователя
    chat_history[user_id].append({"role": "user", "content": message})
    
    # Ограничиваем контекст (последние 10 сообщений + системный промт)
    # Это экономит токены и держит фокус на текущей теме
    if len(chat_history[user_id]) > 12: 
        # Сохраняем системный промт (индекс 0) и последние 10 сообщений
        chat_history[user_id] = [chat_history[user_id][0]] + chat_history[user_id][-10:]

    # Отправляем запрос к ИИ
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": chat_history[user_id],
                "max_tokens": 512,
                "temperature": 1.0  # Креативность по максимуму
            }
        )
        data = resp.json()
        reply = data["choices"][0]["message"]["content"]
        
        # Запоминаем ответ бота
        chat_history[user_id].append({"role": "assistant", "content": reply})
        return reply

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я разговорный бот. Задай любой вопрос или просто поболтаем 😊")


@dp.message(Command("img"))
async def generate_image(message: types.Message):
    if not message.text.split(" ", 1)[-1]:
        await message.answer("Напиши, что нарисовать. Пример: /img кот в космосе")
        return
    
    prompt = message.text.split(" ", 1)[-1]
    loading_msg = await message.answer("🎨 Рисую картинку...")
    
    try:
        encoded_prompt = urllib.parse.quote(prompt)
        img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true"
        await message.answer_photo(img_url)
        await loading_msg.delete()
    except Exception as e:
        await loading_msg.edit_text(f"❌ Не удалось нарисовать. Сервис перегружен или промпт странный.\nОшибка: {e}")


@dp.message()
async def handle_message(message: types.Message):
    # Игнорируем, если это не текст или это сообщение от бота
    if not message.text or message.from_user.is_bot:
        return

    # --- НОВАЯ ЛОГИКА ДЛЯ ГРУПП ---
    if message.chat.type != "private":
        # Замени 'my_ai_bot' на username своего бота (без знака @)
        # Пример: если бот @SuperBot, пишем SuperBot
        if "боб" not in message.text:
            return  # Если бота не упомянули — молчим и выходим
    # -----------------------------

    # Если прошли проверку (или это личка) — обрабатываем
    typing = await message.answer("Печатает...")
    try:
        # Используем chat.id для группы, чтобы бот помнил контекст всей беседы
        target_id = str(message.chat.id) if message.chat.type != "private" else str(message.from_user.id)
        
        reply = await get_ai_reply(
            str(message.from_user.id), 
            message.text, 
            message.from_user.first_name # Передаем имя из сообщения
        )
        await typing.edit_text(reply)
    except Exception as e:
        await typing.edit_text("⚠️ Ошибка ИИ. Попробуй позже")
        print(f"AI Error: {e}")

class DummyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        pass

async def main():
    # Render требует, чтобы приложение слушало на определенном порту
    port = int(os.environ.get("PORT", 10000))
    
    # Запускаем мини-сервер в фоне, чтобы Render думал, что всё ок
    server = http.server.HTTPServer(('0.0.0.0', port), DummyHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    print(f"Bot is running on port {port}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
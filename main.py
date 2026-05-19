import http.server
import threading
import os
import httpx
import asyncio
import urllib.parse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv

# Render игнорирует .env, но load_dotenv() не мешает. 
# Главное: переменные должны быть заданы в Dashboard Render -> Environment
load_dotenv()
bot = Bot(token=os.getenv("TG_BOT_TOKEN"))
dp = Dispatcher()
chat_history = {}

def get_smart_prompt(user_name: str):
    return (
        f"Тебя зовут Боб. Ты дерзкий, грамотный, неформальный друг. "
        f"Ты общаешься с человеком по имени {user_name}. "
        f"Пиши только на правильном русском языке. Соблюдай пунктуацию и орфографию. "
        f"Отвечай кратко (1-3 предложения), с иронией и живым сленгом. "
        f"Мат используй. Не будь официальным. "
        f"Обращайся к {user_name} по имени, только когда уместно."
    )

async def get_ai_reply(user_id: str, message_text: str, user_name: str) -> str:
    if user_id not in chat_history:
        chat_history[user_id] = [{"role": "system", "content": get_smart_prompt(user_name)}]
        
    chat_history[user_id].append({"role": "user", "content": message_text})
    if len(chat_history[user_id]) > 12:
        chat_history[user_id] = [chat_history[user_id][0]] + chat_history[user_id][-10:]
        
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
                "temperature": 0.7,
                "top_p": 0.9,
                "frequency_penalty": 0.3
            }
        )
        
        # ✅ Безопасная обработка ошибок Groq
        if resp.status_code != 200:
            error_detail = resp.json().get("error", {}).get("message", "Unknown") if resp.headers.get("content-type", "").startswith("application/json") else resp.text[:150]
            raise RuntimeError(f"Groq API {resp.status_code}: {error_detail}")
            
        data = resp.json()
        if not data.get("choices"):
            raise RuntimeError("Пустой ответ от ИИ")
            
        reply = data["choices"][0]["message"]["content"]
        chat_history[user_id].append({"role": "assistant", "content": reply})
        return reply

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я Боб. Пиши что хочешь, или /img для картинок 🤖")

@dp.message(Command("img"))
async def generate_image(message: types.Message):
    args = message.text.split(maxsplit=1)
    prompt = args[1] if len(args) > 1 else ""
    if not prompt:
        await message.answer("Напиши, что нарисовать. Пример: /img кот в космосе 🚀")
        return

    loading = await message.answer("🎨 Рисую...")
    try:
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width=512&height=512&nologo=true"
        await message.answer_photo(url)
        await loading.delete()
    except Exception as e:
        await loading.edit_text(f"❌ Ошибка: {e}")

@dp.message()
async def handle_message(message: types.Message, bot: Bot):
    msg_text = (message.text or message.caption or "").strip()
    if not msg_text or message.from_user.is_bot:
        return

    # --- ТРИГГЕРЫ ДЛЯ ГРУПП ---
    if message.chat.type != "private":
        text_lower = msg_text.lower()
        is_reply = message.reply_to_message and message.reply_to_message.from_user.id == bot.id
        has_mention = bot.username and f"@{bot.username.lower()}" in text_lower
        has_name = "боб" in text_lower or "bob" in text_lower

        if not (is_reply or has_mention or has_name):
            return  # Молчим, если не обратились к боту
    # --------------------------

    target_id = str(message.chat.id) if message.chat.type != "private" else str(message.from_user.id)
    typing = await message.answer("Печатает...")
    
    try:
        reply = await get_ai_reply(target_id, msg_text, message.from_user.first_name)
        await typing.edit_text(reply)
    except Exception as e:
        print(f"🔴 AI CRASH: {e}")  # Виден в Render Logs
        await typing.edit_text(f"⚠️ Ошибка: {str(e)[:50]}")

class DummyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers()
    def log_message(self, format, *args): pass

async def main():
    port = int(os.environ.get("PORT", 10000))
    server = http.server.HTTPServer(('0.0.0.0', port), DummyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"✅ Bot started on port {port}")
    
    # ✅ Обязательно загружаем данные бота до поллинга
    await bot.get_me()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
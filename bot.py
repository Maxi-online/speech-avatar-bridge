"""Optional Telegram transport. No polling or provider access during import."""
import os
from io import BytesIO

def allowed_users():
    return {int(value.strip()) for value in os.environ.get('AVATAR_ALLOWED_USER_IDS','').split(',') if value.strip()}

def main():
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    import httpx
    token = os.environ.get('BOT_TOKEN')
    users = allowed_users()
    if not token or not users:
        raise RuntimeError('Configure BOT_TOKEN and AVATAR_ALLOWED_USER_IDS before starting the bot')
    base = os.environ.get('AVATAR_API_URL','http://127.0.0.1:8000').rstrip('/')
    async def start(update, context):
        if update.effective_user.id not in users:
            await update.message.reply_text('Access is not enabled for this account.')
            return
        await update.message.reply_text('Speech Avatar Bridge: send a question or a short voice message.')
    async def answer(update, context):
        if update.effective_user.id not in users:
            await update.message.reply_text('Access is not enabled for this account.')
            return
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                if update.message.voice:
                    if update.message.voice.file_size and update.message.voice.file_size > 10*1024*1024:
                        await update.message.reply_text('Voice message exceeds 10 MiB.')
                        return
                    voice = await update.message.voice.get_file()
                    content = await voice.download_as_bytearray()
                    response = await client.post(base+'/api/recognize_and_synthesize', content=bytes(content))
                    response.raise_for_status()
                    await update.message.reply_audio(audio=BytesIO(response.content), filename='answer.wav')
                else:
                    response = await client.post(base+'/api/get_answer_async', json={
                        'text':update.message.text, 'user_id':0, 'history':[]})
                    response.raise_for_status()
                    await update.message.reply_text(response.json()['message'])
            except httpx.HTTPError:
                await update.message.reply_text('The bridge could not complete the request.')
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler('start',start))
    application.add_handler(MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.VOICE,answer))
    application.run_polling()

if __name__ == '__main__':
    main()

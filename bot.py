import os
import re
import tempfile
import requests
import base64
import logging
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import fitz
from docx import Document

# إعداد السجل
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8469933821:AAFStidpfrR9zq18pn1m8jFEYzRqmusz3z8"
OPENROUTER_API_KEY = "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"

SUBJECTS = [
    ["رياضيات", "كيمياء"],
    ["أحياء", "إنجليزي"],
    ["إسلامية", "عربي"]
]

app_flask = Flask(__name__)

def clean_markdown_symbols(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[#*_`~#-]', '', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

def create_summary_txt(title: str, content: str) -> str:
    temp_txt = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    temp_txt.write(f"=== {title} ===\n\n")
    temp_txt.write(content)
    temp_txt.close()
    return temp_txt.name

def ask_openrouter(prompt_text: str, subject: str, image_data=None) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://telegram.me/YourBotName",
        "X-Title": "Student Academic Advisor Bot",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        f"أنت معلم خبير في مادة {subject}. قدم شرحاً أكاديمياً صافياً وواضحاً بدون أي رموز أو حشو. "
        f"اكتب الشرح في فقرات مرتبطة ومفهومة للطلاب."
    )

    messages = [{"role": "system", "content": system_prompt}]
    
    if image_data:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": image_data}}
            ]
        })
    else:
        messages.append({"role": "user", "content": prompt_text})

    data = {
        "model": "google/gemini-2.5-flash",
        "messages": messages,
        "max_tokens": 3000
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        res_json = response.json()
        if "choices" in res_json and len(res_json["choices"]) > 0:
            return clean_markdown_symbols(res_json["choices"][0]["message"]["content"])
        return "عذراً، لم يتمكن الذكاء الاصطناعي من صياغة إجابة."
    except Exception as e:
        logger.error(f"API Error: {str(e)}")
        return "حدث ضغط على النظام، يرجى إعادة المحاولة."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(SUBJECTS, resize_keyboard=True)
    await update.message.reply_text(
        "مرحباً بك في المساعد الأكاديمي الشامل.\n\n"
        "البوت متصل عبر السحابة ويعمل على مدار الساعة. اختر المادة الدراسية أولاً، ثم أرسل الملف أو الصورة أو السؤال.",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    selected_subject = context.user_data.get("selected_subject", "عامة")

    try:
        if message.text and not message.document and not message.photo:
            text = message.text
            subjects_flat = [sub for row in SUBJECTS for sub in row]
            
            if text in subjects_flat:
                context.user_data["selected_subject"] = text
                await message.reply_text(f"تم اختيار مادة {text}. تفضل بإرسال الملزمة أو الصورة أو السؤال.")
                return

            processing_msg = await message.reply_text("جاري إعداد الشرح...")
            ai_response = ask_openrouter(text, selected_subject)

            query_encoded = f"{selected_subject} {text[:30]}".replace(" ", "+")
            youtube_url = f"https://www.youtube.com/results?search_query={query_encoded}"

            final_output = f"الشرح والتحليل لمادة {selected_subject}:\n\n{ai_response}\n\nرابط مشاهدة شرح الدرس على يوتيوب:\n{youtube_url}"

            if len(final_output) > 3800:
                await processing_msg.edit_text(final_output[:3800])
                await message.reply_text(final_output[3800:])
            else:
                await processing_msg.edit_text(final_output)
            return

        if message.photo:
            processing_msg = await message.reply_text("جاري قراءة الصورة وتحليلها...")
            photo_file = await message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            encoded_image = f"data:image/jpeg;base64,{base64.b64encode(photo_bytes).decode('utf-8')}"
            
            ai_response = ask_openrouter("قم بتحليل هذه الصورة واشرح محتواها بوضوح تام.", selected_subject, image_data=encoded_image)
            youtube_url = f"https://www.youtube.com/results?search_query={selected_subject}+شرح+درس"

            full_output = f"حل وتحليل الصورة لمادة {selected_subject}:\n\n{ai_response}\n\nرابط شروحات يوتيوب المقترحة:\n{youtube_url}"
            if len(full_output) > 3800:
                await processing_msg.edit_text(full_output[:3800])
                await message.reply_text(full_output[3800:])
            else:
                await processing_msg.edit_text(full_output)
            return

        if message.document:
            file_name = message.document.file_name
            processing_msg = await message.reply_text(f"جاري قراءة الملف ({file_name})...")

            file = await message.document.get_file()
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                await file.download_to_drive(temp_file.name)
                temp_file_path = temp_file.name

            raw_text = ""
            if file_name.endswith(".pdf"):
                doc = fitz.open(temp_file_path)
                for page in doc:
                    raw_text += page.get_text() + "\n"
                doc.close()
            elif file_name.endswith(".docx"):
                doc = Document(temp_file_path)
                for para in doc.paragraphs:
                    raw_text += para.text + "\n"
            os.remove(temp_file_path)
            
            ai_summary = ask_openrouter(f"قم بتحليل هذا المستند واكتب شرحاً شاملاً وواضحاً:\n\n{raw_text[:10000]}", selected_subject)
            youtube_url = f"https://www.youtube.com/results?search_query={selected_subject}+{file_name.rsplit('.', 1)[0]}".replace(" ", "+")

            text_output = f"الشرح الشامل للملف لمادة {selected_subject}:\n\n{ai_summary}\n\nرابط مشاهدة شرح الدرس على يوتيوب:\n{youtube_url}"
            if len(text_output) > 3800:
                await processing_msg.edit_text(f"الجزء الأول:\n\n{text_output[:3800]}")
                await message.reply_text(f"الجزء الثاني:\n\n{text_output[3800:]}")
            else:
                await processing_msg.edit_text(text_output)

            txt_path = create_summary_txt(file_name, ai_summary)
            with open(txt_path, 'rb') as txt_file:
                await message.reply_document(document=txt_file, filename=f"Summary_{file_name}.txt", caption="ملف الملخص النصي الصافي.")
            os.remove(txt_path)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await message.reply_text("حدث خطأ تقني، يرجى المحاولة مرة أخرى.")

# إعداد التطبيق ليعمل مع الويب
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL | filters.PHOTO, handle_message))

@app_flask.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok", 200

@app_flask.route("/")
def index():
    return "Bot is active and running 24/7!", 200

if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(application.initialize())
    app_flask.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

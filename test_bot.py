import logging
import os
import requests
import fitz  # PyMuPDF
from huggingface_hub import InferenceClient
from google import genai
from google.genai import types
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters,
)
from test_prompt import build_prompt
from validator import validate_input

load_dotenv()

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
HF_CLIENT = InferenceClient(api_key=os.environ.get("HUGGINGFACE_API_KEY", ""))
try:
    GEMINI_CLIENT = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
except Exception:
    GEMINI_CLIENT = None

HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"  # Adjusted per request to a working Qwen model
WAITING_JD, WAITING_RESUME = range(2)
_JD_KEY = "jd"


def _split_send(text: str) -> list[str]:
    chunks = []
    while len(text) > 4000:
        i = text.rfind("\n", 0, 3800)
        if i == -1:
            i = 3800
        chunks.append(text[:i])
        text = text[i:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks

async def _extract_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Extract text from message or uploaded document (PDF/TXT)."""
    if update.message.text:
        return update.message.text

    if not update.message.document:
        return None

    doc = update.message.document
    if not (doc.file_name.lower().endswith(".pdf") or doc.mime_type in ["application/pdf", "text/plain"]):
        await update.message.reply_text("❌ Please upload a PDF or text file.")
        return None

    file = await context.bot.get_file(doc.file_id)
    download_path = f"temp_{doc.file_id}"
    await file.download_to_drive(download_path)

    text = ""
    try:
        if doc.file_name.lower().endswith(".pdf"):
            with fitz.open(download_path) as pdf:
                for page in pdf:
                    text += page.get_text()
        else:
            with open(download_path, "r", encoding="utf-8") as f:
                text = f.read()
    except Exception as e:
        logger.error("Failed to extract text: %s", e)
        await update.message.reply_text("❌ Failed to read the file. Please try pasting the text instead.")
        text = None
    finally:
        if os.path.exists(download_path):
            os.remove(download_path)

    return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 I score resumes against job descriptions using ATS-style AI analysis.\n"
        "I'll give you a score out of 10, a breakdown, gaps, and tailored recommendations.\n\n"
        "📋 Paste the *job description* to begin (plain text only, no links).",
        parse_mode="Markdown",
    )
    return WAITING_JD


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "ℹ️ *How this bot works:*\n"
        "1️⃣ Paste a JD → 2️⃣ Paste a resume → 3️⃣ Get a full AI report.\n\n"
        "Plain text only · 80–12,000 chars per input.\n"
        "/same — reuse current JD · /cancel — exit\n",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Send /start to begin a new session.")
    return ConversationHandler.END


async def same(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not context.user_data.get(_JD_KEY):
        await update.message.reply_text(
            "No stored JD found. Please send /start to paste a new job description."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "✅ Using the same job description.\n\n📄 Now paste the *candidate's resume*:",
        parse_mode="Markdown",
    )
    return WAITING_RESUME


async def receive_jd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _extract_text(update, context)
    if not text:
        return WAITING_JD

    user_id = update.effective_user.id
    logger.info("user=%d received JD len=%d", user_id, len(text))

    ok, msg = validate_input(text, "job description")
    if not ok:
        await update.message.reply_text(f"⚠️ {msg}")
        return WAITING_JD

    context.user_data[_JD_KEY] = text
    if msg:
        await update.message.reply_text(f"⚠️ {msg}")
    await update.message.reply_text(
        "✅ Job description saved.\n\n📄 Now paste the *candidate's resume*:",
        parse_mode="Markdown",
    )
    return WAITING_RESUME


async def receive_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = await _extract_text(update, context)
    if not text:
        return WAITING_RESUME

    user_id = update.effective_user.id
    jd = context.user_data.get(_JD_KEY, "")
    logger.info("user=%d received resume len=%d", user_id, len(text))

    ok, msg = validate_input(text, "resume")
    if not ok:
        await update.message.reply_text(f"⚠️ {msg}")
        return WAITING_RESUME

    if msg:
        await update.message.reply_text(f"⚠️ {msg}")

    await update.message.reply_text("⏳ Analysing… this takes 15–30 seconds.")

    system_prompt = (
        "You are a precise, structured recruiter. "
        "Always follow the exact output format. "
        "Never skip sections. Never inflate scores. "
        "Show your score arithmetic."
    )
    user_prompt = build_prompt(jd, text)

    result = None
    # Try Hugging Face first
    try:
        if not os.environ.get("HUGGINGFACE_API_KEY"):
            raise ValueError("No HF Key")
            
        hf_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        response = HF_CLIENT.chat_completion(
            model=HF_MODEL,
            messages=[{"role": "user", "content": hf_prompt}],
            max_tokens=3000,
            seed=42
        )
        result = response.choices[0].message.content
        logger.info("user=%d HuggingFace response len=%d", user_id, len(result))
    except Exception as hf_e:
        logger.warning("user=%d HF failed (%s). Falling back to Gemini.", user_id, hf_e)
        # Fallback to Gemini
        try:
            if not GEMINI_CLIENT:
                raise ValueError("Gemini is not configured.")
            response = GEMINI_CLIENT.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=3000,
                    temperature=0.3,
                )
            )
            result = response.text
            logger.info("user=%d Gemini response len=%d", user_id, len(result))
        except Exception as gem_e:
            logger.error("user=%d Gemini fallback failed: %s", user_id, gem_e)
            await update.message.reply_text(
                "❌ Both Hugging Face and Gemini engines failed (likely rate-limited or exhausted). Please try again later."
            )
            return ConversationHandler.END

    if result:
        for chunk in _split_send(result):
            await update.message.reply_text(chunk)
        await update.message.reply_text(
            "Test another resume against the same JD? /same\nNew job? /start"
        )

    return ConversationHandler.END


async def reject_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Catch unsupported document types (photos/audio) and tell the user to upload PDF/text."""
    state = WAITING_RESUME if context.user_data.get(_JD_KEY) else WAITING_JD
    await update.message.reply_text(
        "📎 I can't read photos or media. Please send text or a PDF document.",
        parse_mode="Markdown",
    )
    return state


def main() -> None:
    token = os.environ["TELEGRAM_TOKEN"]
    app = (
        Application.builder()
        .token(token)
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("same", same),
        ],
        states={
            WAITING_JD: [
                MessageHandler(filters.TEXT | filters.Document.MimeType("application/pdf") | filters.Document.MimeType("text/plain"), receive_jd),
                MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL, reject_file),
            ],
            WAITING_RESUME: [
                MessageHandler(filters.TEXT | filters.Document.MimeType("application/pdf") | filters.Document.MimeType("text/plain"), receive_resume),
                MessageHandler(filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.Document.ALL, reject_file),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("same", same),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    logger.info("Bot starting (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

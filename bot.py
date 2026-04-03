import logging
import os
import requests
import fitz  # PyMuPDF
from fpdf import FPDF
from huggingface_hub import AsyncInferenceClient
from google import genai
from google.genai import types
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, ContextTypes, filters,
)

from prompt import build_prompt, build_rewrite_prompt
from validator import validate_input

load_dotenv()

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
HF_CLIENT = AsyncInferenceClient(api_key=os.environ.get("HUGGINGFACE_API_KEY", ""))
try:
    GEMINI_CLIENT = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))
except Exception:
    GEMINI_CLIENT = None

HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"  # Adjust to your preferred free HF model, e.g. "mistralai/Mistral-7B-Instruct-v0.2"
WAITING_JD, WAITING_RESUME, CHATTING = range(3)
_JD_KEY = "jd"
_RESUME_KEY = "resume"


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


async def _get_ai_response(system_prompt: str, user_prompt: str, user_id: int) -> str | None:
    """Helper to get response from HF with Gemini fallback."""
    # Try Hugging Face first
    try:
        if not os.environ.get("HUGGINGFACE_API_KEY"):
            raise ValueError("No HF Key")
            
        hf_prompt = f"System: {system_prompt}\n\nUser: {user_prompt}"
        response = await HF_CLIENT.chat_completion(
            model=HF_MODEL,
            messages=[{"role": "user", "content": hf_prompt}],
            max_tokens=3000,
            temperature=0.01,
            top_p=1.0,
            seed=42
        )
        result = response.choices[0].message.content
        logger.info("user=%d HF response len=%d", user_id, len(result))
        return result
    except Exception as hf_e:
        logger.warning("user=%d HF failed (%s). Falling back to Gemini.", user_id, hf_e)
        # Fallback to Gemini
        try:
            if not GEMINI_CLIENT:
                raise ValueError("Gemini is not configured.")
            response = await GEMINI_CLIENT.aio.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    max_output_tokens=3000,
                    temperature=0.0,
                    top_p=1.0,
                )
            )
            logger.info("user=%d Gemini response len=%d", user_id, len(response.text))
            return response.text
        except Exception as gem_e:
            logger.error("user=%d Gemini fallback failed: %s", user_id, gem_e)
            return None


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
        "📋 Paste the *job description* or upload it as a *PDF* to begin.",
        parse_mode="Markdown",
    )
    return WAITING_JD


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "ℹ️ *How this bot works:*\n"
        "1️⃣ Paste a JD → 2️⃣ Paste a resume → 3️⃣ Get a full AI report.\n\n"
        "Plain text or PDF supported.\n"
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
        "✅ Using the same job description.\n\n📄 Now paste the *candidate's resume* or upload it as a *PDF*:",
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
        "✅ Job description saved.\n\n📄 Now paste the *candidate's resume* or upload it as a *PDF*:",
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

    context.user_data[_RESUME_KEY] = text
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

    result = await _get_ai_response(system_prompt, user_prompt, user_id)

    if result:
        for chunk in _split_send(result):
            await update.message.reply_text(chunk)
        await update.message.reply_text(
            "💬 *Any follow-up questions?*\n"
            "You can now freely chat with the senior recruiter. "
            "Ask about specific sections, how to improve, or career advice.\n\n"
            "📥 *Want an improved version?*\n"
            "Use /download to generate an ATS-optimized resume file based on this JD!\n\n"
            "_Or send /start to begin with a new job._",
            parse_mode="Markdown"
        )
        return CHATTING
    else:
        await update.message.reply_text(
            "❌ AI engines failed. Please try again later."
        )
        return ConversationHandler.END


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle follow-up questions after scoring."""
    user_id = update.effective_user.id
    user_msg = update.message.text
    jd = context.user_data.get(_JD_KEY, "")
    resume = context.user_data.get(_RESUME_KEY, "")

    if not jd or not resume:
        await update.message.reply_text("❌ Session lost. Please send /start to begin.")
        return ConversationHandler.END

    logger.info("user=%d chat message: %s", user_id, user_msg)
    await update.message.reply_chat_action("typing")

    system_prompt = (
        "You are an expert senior recruiter. Answer the user's questions about their resume "
        "and how it relates to the job description. Be professional, honest, and helpful. "
        "Use your 15 years of experience to provide strategic advice. "
        f"\n\nJOB DESCRIPTION:\n{jd}\n\nRESUME:\n{resume}"
    )
    
    result = await _get_ai_response(system_prompt, user_msg, user_id)

    if result:
        for chunk in _split_send(result):
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text("❌ Something went wrong. Please try again.")

    return CHATTING


def _clean_text(text: str) -> str:
    """Replace common Unicode characters that break standard PDF encoding."""
    if not text:
        return ""
    replacements = {
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2022": "*",  # bullet point
        "\u00b7": "*",  # middle dot
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Filter out characters that are not in Latin-1
    # This is a bit aggressive but ensures the PDF never crashes
    return "".join(c for c in text if ord(c) < 256)


def _create_pdf(text: str, filename: str):
    """Convert AI-generated resume text into a formatted ATS-style PDF."""
    sanitized_text = _clean_text(text)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(15, 15, 15)
    
    # Header logic
    header_patterns = ["SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION", "PROJECTS", "CERTIFICATIONS", "CONTACT"]
    
    for line in sanitized_text.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(2)
            continue
            
        # Detect Headers
        is_header = (line.startswith("#") or 
                     (line.isupper() and any(h in line for h in header_patterns) and len(line) < 35))
            
        if is_header:
            pdf.ln(5)
            pdf.set_x(15)
            pdf.set_font("Helvetica", style="B", size=11)
            header_text = line.replace("#", "").strip().upper()
            pdf.cell(180, 8, header_text, ln=True)
            # Underline
            curr_y = pdf.get_y()
            pdf.set_line_width(0.2)
            pdf.line(15, curr_y, 195, curr_y)
            pdf.ln(2)
        else:
            pdf.set_x(15)
            # Bullet point detection
            if line.startswith("-") or line.startswith("*") or line.startswith("+"):
                pdf.set_font("Helvetica", size=9)
                # Use a simple dash for bullets
                content = " - " + line[1:].strip()
                pdf.multi_cell(180, 5, content)
            else:
                pdf.set_font("Helvetica", size=9)
                pdf.multi_cell(180, 5, line)
                
    pdf.output(filename)


async def download(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generate a downloadable improved ATS resume in PDF format."""
    user_id = update.effective_user.id
    jd = context.user_data.get(_JD_KEY, "")
    resume = context.user_data.get(_RESUME_KEY, "")

    if not jd or not resume:
        await update.message.reply_text("❌ Session lost. Please send /start to begin.")
        return ConversationHandler.END

    await update.message.reply_text("⏳ Generating your improved ATS-style PDF resume… this takes a moment.")
    await update.message.reply_chat_action("upload_document")

    system_prompt = "You are a senior professional resume writer. Output ONLY the resume content in clear Markdown."
    user_prompt = build_rewrite_prompt(jd, resume)

    result = await _get_ai_response(system_prompt, user_prompt, user_id)

    if result:
        file_path = f"Improved_Resume_{user_id}.pdf"
        try:
            _create_pdf(result, file_path)
            
            with open(file_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"Improved_Resume_ATS.pdf",
                    caption="✅ Here is your improved, ATS-optimized PDF resume template! Ready for final review."
                )
        except Exception as e:
            logger.error("PDF generation/send failed: %s", e)
            await update.message.reply_text("❌ Failed to generate PDF. I'll paste the text below instead.\n\n" + result[:2000])
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        await update.message.reply_text("❌ Failed to generate resume. Please try again.")

    return CHATTING


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
                CommandHandler("download", download),
            ],
            CHATTING: [
                CommandHandler("download", download),
                MessageHandler(filters.TEXT & (~filters.COMMAND), chat),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("same", same),
            CommandHandler("start", start),
            CommandHandler("download", download),
        ],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    logger.info("Bot starting (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

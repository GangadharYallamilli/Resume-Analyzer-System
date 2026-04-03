<<<<<<< HEAD
# JD Scorer Bot 🎯

A Telegram bot that scores a candidate's resume against a job description using Hugging Face and Gemini AI. It returns a score out of 10, a weighted dimension breakdown, detected skills, identified gaps, and prioritised senior-level recruiter recommendations — powered by ATS-style analysis.

---

## Prerequisites

- Python 3.11+
- A Telegram bot token (from BotFather)
- A Hugging Face API key (Primary model)
- A Google Gemini API key (Fallback model)
- (Optional) A [Railway.app](https://railway.app) account for deployment

---

## 1. Get your Telegram Bot Token

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow the prompts (choose a name and username).
3. BotFather will reply with your token — it looks like `123456:ABC-...`.
4. Copy and save it.

---

## 2. Get your AI API Keys

1. **Hugging Face:** Go to Settings -> Access Tokens to create a free read key.
2. **Google Gemini:** Go to Google AI Studio to generate an API key for Gemini 2.5 Flash fallback.

---

## 3. Local Setup

```bash
# 1. Clone / navigate into the project directory
cd jd-scorer-bot

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows (CMD / PowerShell)
.venv\Scripts\activate
# Windows (Git Bash / WSL)
source .venv/Scripts/activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux

# Open .env and fill in your keys:
# TELEGRAM_TOKEN=<your token>
# HUGGINGFACE_API_KEY=<your HF key>
# GEMINI_API_KEY=<your Gemini key>

# 5. Run the bot
python bot.py
```

The bot will log `Bot starting (polling)…` when it's live. Open Telegram, find your bot, and send `/start`.

---

## 4. Deploy to Railway

1. Push the project to a GitHub repository.
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. Select your repo. Railway detects the `Procfile` automatically.
4. Go to the project **Settings → Variables** and add:
   - `TELEGRAM_TOKEN` = your bot token
   - `ANTHROPIC_API_KEY` = your Anthropic key
5. Click **Deploy**. Railway starts the `worker: python bot.py` process. Done.

> The `Procfile` uses `worker:` (not `web:`) because this bot uses polling — no HTTP port is needed.

---

## 5. Bot Commands

| Command   | Description                                          |
|-----------|------------------------------------------------------|
| `/start`  | Begin a new session — paste a JD first               |
| `/same`   | Re-use the current JD, test a new resume against it  |
| `/help`   | Show usage tips                                      |
| `/cancel` | Exit the current session and clear state             |

---

## 6. Example Output

```
🎯 MATCH SCORE: 6.4/10

📊 BREAKDOWN:
Hard skills     7/10  ███████░░░  (30%)
Experience      6/10  ██████░░░░  (20%)
ATS keywords    5/10  █████░░░░░  (20%)
Domain fit      8/10  ████████░░  (15%)
Soft skills     7/10  ███████░░░  (15%)

Score = (7×0.30)+(6×0.20)+(5×0.20)+(8×0.15)+(7×0.15) = 6.4

📝 SENIOR RECRUITER SUMMARY:
The candidate demonstrates strong domain alignment and relevant hard skills, particularly with Python and AWS. However, ATS keyword density is below threshold because the resume relies heavily on synonyms rather than literal terminology. The most critical gap is the absence of explicitly stated "CI/CD" and "Docker" terminology, which are essential requirements for this role.

✅ SKILLS DETECTED:
Python 3.11, AWS infrastructure, Team Leadership

❌ GAPS IDENTIFIED:
Docker, CI/CD pipelines, 5 years minimum experience (only 3.5 explicitly shown)

💡 RECRUITER'S RECOMMENDATIONS:
1. Keyword Alignment: Add `Docker` and `CI/CD pipelines` immediately to your Core Competencies section.
2. Impact Bullet Points: For your projects, use the STAR method. e.g., "Managed CI/CD pipelines using Jenkins and Docker, reducing deployment time by 40%".
3. Formatting: Ensure your resume is single-column for ATS readability. 
4. Context: Add a clear start date to your earliest related role to definitively showcase your full 5 years of industry experience.

⚡ VERDICT: NEEDS TAILORING
Incorporating the missing ATS keywords and surfacing at least one explicit Docker project would push this resume into the APPLY + COVER LETTER tier.
```

---

## 7. Known Limitations

- **12,000 character limit** — very long documents must be trimmed before pasting.
- **English optimised** — the rubric and keyword detection are tuned for English-language JDs and resumes.
- **No persistent storage** — stored JD lives only for the current bot session. If the bot restarts, use `/start` to re-enter the JD.
- **Rate limits** — heavy concurrent usage may hit Anthropic rate limits; the bot will prompt you to retry after 30 seconds.
=======

Author: Gangadhar Yallamilli

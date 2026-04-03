"""Input validation for the JD Scorer Telegram bot."""

import re

# Keywords that suggest a JD contains real requirements
JD_KEYWORD_LIST = {
    "years", "experience", "required", "skills", "responsibilities",
    "qualifications", "degree", "role", "position", "requirements",
    "duties", "knowledge", "proficiency", "ability", "team",
}

MIN_CHARS = 80
MAX_CHARS = 12_000
RESUME_SHORT_WARN = 300


def validate_input(text: str, input_type: str) -> tuple[bool, str]:
    """
    Validate a JD or resume text input.

    Args:
        text:       The raw input string from the user.
        input_type: Either "job description" or "resume".

    Returns:
        (True, "")            — clean pass
        (True, "warning: …")  — passes but with a caution message
        (False, "error …")    — rejected; message tells user what to do
    """
    stripped = text.strip()

    # --- Hard rejections (apply to both types) ---

    if len(stripped) < MIN_CHARS:
        return (
            False,
            f"Too short to analyse. Please paste the full {input_type}.",
        )

    if len(stripped) > MAX_CHARS:
        return (
            False,
            f"Too long. Please trim your {input_type} to under 12,000 characters.",
        )

    # Looks like a bare URL (starts with http/https and has no spaces)
    if re.match(r"^https?://\S+$", stripped):
        return (
            False,
            "Please paste the text content, not a link.",
        )

    # Contains no alphabetic words at all
    if not re.search(r"[A-Za-z]", stripped):
        return (
            False,
            f"This doesn't look like a real {input_type}. Please paste plain text.",
        )

    # --- Type-specific warnings ---

    if input_type == "resume":
        if len(stripped) < RESUME_SHORT_WARN:
            return (
                True,
                "warning: resume seems very short — results may be limited",
            )

    if input_type == "job description":
        words_lower = set(re.findall(r"[a-z]+", stripped.lower()))
        if not words_lower.intersection(JD_KEYWORD_LIST):
            return (
                True,
                "warning: JD seems vague — scoring may be less precise",
            )

    return (True, "")

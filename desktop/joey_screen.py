"""
JOEY & RYAN - screen help
"Ryan, what's this error?"  "Joey, what does this say?"  "Which button do I click?"
They take a screenshot ONLY when you ask about something on your screen, look at it, and explain.
The screenshot is sent to Claude to read; it is not saved anywhere.
Needs:  pip install pillow
"""

import base64
import io

ALL_SCREENS = False   # True = capture every monitor, False = just the main one
MAX_SIDE = 1568       # shrink big screens to this size (sharp enough to read, cheaper to send)


def take_screenshot():
    from PIL import ImageGrab

    img = ImageGrab.grab(all_screens=ALL_SCREENS).convert("RGB")
    scale = MAX_SIDE / max(img.size)
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii"), img.size


def look_at_screen(question: str = "") -> list:
    """Take a screenshot of the user's screen and look at it. Use this ONLY when the user asks about
    something on their screen, e.g. "what's this error?", "what does this say?", "which button do I
    press?", "can you see this?". Never use it otherwise. Describe only what helps answer the question,
    briefly, for speaking out loud.

    Args:
        question: What the user wants to know about their screen.
    """
    print("  [looking at your screen]")
    try:
        data, size = take_screenshot()
    except Exception as e:
        return f"Couldn't take a screenshot ({e})."
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
        {"type": "text", "text": f"Screenshot of the user's screen ({size[0]}x{size[1]}). "
                                 f"Their question: {question or '(see conversation)'}"},
    ]


SCREEN_TOOLS = [look_at_screen]

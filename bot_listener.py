"""
מצפן AI — Telegram Bot Listener
Polls for messages and responds to commands.
"""

import json
import time
import sys
import os
import requests
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
STATE_FILE = Path(__file__).parent / "bot_state.json"
PROMPT_FILE = Path(__file__).parent / "briefing_prompt.txt"
FEEDBACK_FILE = Path(__file__).parent / "feedback_log.json"

COMMANDS_HELP = """🧭 מצפן AI — פקודות זמינות:

/now — הרץ סקירה עכשיו
/topics — הצג נושאי מעקב
/add נושא — הוסף נושא מעקב
/remove נושא — הסר נושא מעקב
/feedback טקסט — שלח משוב לשיפור
/status — סטטוס המערכת
/help — הצג פקודות"""


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"last_update_id": 0, "custom_topics": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_feedback():
    if FEEDBACK_FILE.exists():
        return json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
    return []


def save_feedback(feedback_list):
    FEEDBACK_FILE.write_text(json.dumps(feedback_list, ensure_ascii=False, indent=2), encoding="utf-8")


def send_message(text):
    resp = requests.post(f"{API_BASE}/sendMessage", json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    })
    return resp.json().get("ok", False)


def get_updates(offset=0):
    resp = requests.get(f"{API_BASE}/getUpdates", params={
        "offset": offset,
        "timeout": 5,
    })
    data = resp.json()
    if data.get("ok"):
        return data.get("result", [])
    return []


def get_topics(state):
    # Read base topics from prompt file
    base_topics = [
        "כלים ושירותי AI חדשים",
        "מתחרים ושוק היעוץ",
        "טכניקות וטיפים",
        "טרנדים ורגולציה",
    ]
    custom = state.get("custom_topics", [])
    lines = ["📋 נושאי מעקב קבועים:"]
    for t in base_topics:
        lines.append(f"  • {t}")
    if custom:
        lines.append("\n📌 נושאים שנוספו:")
        for t in custom:
            lines.append(f"  • {t}")
    else:
        lines.append("\nאין נושאים מותאמים אישית. הוסף עם /add")
    return "\n".join(lines)


def add_topic(state, topic):
    custom = state.get("custom_topics", [])
    if topic in custom:
        return state, f"הנושא '{topic}' כבר קיים ברשימה."
    custom.append(topic)
    state["custom_topics"] = custom

    # Also update the prompt file to include custom topics
    update_prompt_with_topics(custom)

    return state, f"✅ הנושא '{topic}' נוסף בהצלחה. ייכלל בסקירה הבאה."


def remove_topic(state, topic):
    custom = state.get("custom_topics", [])
    # Find partial match
    matched = [t for t in custom if topic in t]
    if matched:
        for m in matched:
            custom.remove(m)
        state["custom_topics"] = custom
        update_prompt_with_topics(custom)
        return state, f"✅ הנושא '{matched[0]}' הוסר."
    return state, f"❌ הנושא '{topic}' לא נמצא ברשימה המותאמת."


def update_prompt_with_topics(custom_topics):
    """Update the prompt file to include custom topics."""
    prompt = PROMPT_FILE.read_text(encoding="utf-8")

    # Remove old custom section if exists
    marker_start = "## נושאים מותאמים אישית"
    marker_end = "## שורה תחתונה"
    if marker_start in prompt:
        before = prompt[:prompt.index(marker_start)]
        after = prompt[prompt.index(marker_end):]
        prompt = before + after

    # Add custom topics section before שורה תחתונה
    if custom_topics:
        custom_section = f"\n{marker_start}\n"
        for topic in custom_topics:
            custom_section += f'Search for: "{topic}"\nList 1-2 relevant findings.\n\n'
        prompt = prompt.replace(marker_end, custom_section + marker_end)

    PROMPT_FILE.write_text(prompt, encoding="utf-8")


def add_feedback(text):
    feedback_list = load_feedback()
    feedback_list.append({
        "date": datetime.now().isoformat(),
        "text": text,
    })
    save_feedback(feedback_list)
    return f"📝 המשוב נשמר, תודה!\n\n'{text}'"


def run_briefing_now():
    """Trigger an immediate briefing run."""
    import subprocess
    from config import ANTHROPIC_API_KEY
    send_message("⏳ מריץ סקירה... זה ייקח 2-3 דקות.")
    script = Path(__file__).parent / "ai_daily_briefing.py"
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=360,
        encoding="utf-8",
        env=env,
    )
    if result.returncode == 0:
        return None  # The script already sends the briefing
    else:
        return f"❌ שגיאה בהרצה:\n{result.stderr[:300]}"


def get_status(state):
    custom_count = len(state.get("custom_topics", []))
    feedback_count = len(load_feedback())
    return f"""🧭 מצפן AI — סטטוס

📅 סקירה יומית: כל בוקר 10:00
📋 נושאים מותאמים: {custom_count}
📝 משובים שנשמרו: {feedback_count}
🤖 בוט: פעיל ומאזין"""


def handle_message(text, state):
    """Process a command and return response + updated state."""
    text = text.strip()

    if text == "/help" or text == "/start":
        return COMMANDS_HELP, state

    elif text == "/now":
        err = run_briefing_now()
        if err:
            return err, state
        return None, state  # briefing script sends its own messages

    elif text == "/topics":
        return get_topics(state), state

    elif text.startswith("/add "):
        topic = text[5:].strip()
        if not topic:
            return "שימוש: /add נושא למעקב", state
        state, msg = add_topic(state, topic)
        return msg, state

    elif text.startswith("/remove "):
        topic = text[8:].strip()
        if not topic:
            return "שימוש: /remove נושא", state
        state, msg = remove_topic(state, topic)
        return msg, state

    elif text.startswith("/feedback "):
        fb = text[10:].strip()
        if not fb:
            return "שימוש: /feedback הטקסט שלך", state
        msg = add_feedback(fb)
        return msg, state

    elif text == "/status":
        return get_status(state), state

    elif text.startswith("/"):
        return f"פקודה לא מוכרת. שלח /help לרשימת פקודות.", state

    else:
        # Free text — treat as feedback
        msg = add_feedback(text)
        return f"קיבלתי: {text}\n\nאם זה משוב — נשמר. לפקודות שלח /help", state


def main():
    print(f"[{datetime.now()}] Bot listener started. Polling for messages...")
    state = load_state()

    while True:
        try:
            offset = state.get("last_update_id", 0) + 1
            updates = get_updates(offset)

            for update in updates:
                state["last_update_id"] = update["update_id"]
                msg = update.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")

                # Only respond to our user
                if chat_id != TELEGRAM_CHAT_ID:
                    continue

                if not text:
                    continue

                print(f"[{datetime.now()}] Received: {text}")
                response, state = handle_message(text, state)
                save_state(state)

                if response:
                    send_message(response)

        except KeyboardInterrupt:
            print("\nStopping bot listener.")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error: {e}")
            time.sleep(10)

        time.sleep(3)


if __name__ == "__main__":
    main()

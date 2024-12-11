import telebot
import subprocess
import qrcode
import io
import json
import os
import shlex
import re
from dotenv import load_dotenv
from telebot import types
import time
import logging
from datetime import datetime
from collections import defaultdict
import threading
import schedule

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

# Bot Configuration
API_TOKEN = os.getenv('API_TOKEN')
ADMIN_USER_IDS = json.loads(os.getenv('ADMIN_USER_IDS', '[]'))

logging.info(f"API Token: {'Present' if API_TOKEN else 'Missing'}")
logging.info(f"Admin IDs: {ADMIN_USER_IDS}")

if not API_TOKEN:
    raise ValueError("API_TOKEN not found in environment variables")

if not ADMIN_USER_IDS:
    raise ValueError("ADMIN_USER_IDS not found or invalid in environment variables")

CLI_PATH = '/etc/hysteria/core/cli.py'
BACKUP_DIRECTORY = '/opt/hysbackup'
USER_DATA_FILE = '/etc/hysteria/user_data.json'
HELP_MESSAGE_FILE = '/etc/hysteria/help_message.txt'
ANALYTICS_FILE = '/etc/hysteria/analytics.json'
FEEDBACK_FILE = '/etc/hysteria/feedback.json'
LOG_DIRECTORY = '/var/log/hysteria'

# Create necessary directories
os.makedirs(LOG_DIRECTORY, exist_ok=True)
os.makedirs(BACKUP_DIRECTORY, exist_ok=True)

# Configuration Constants
MAX_BACKUPS = 5  # Maximum number of backup files to keep
NOTIFICATION_THRESHOLDS = {
    'traffic': 0.9,  # 90% of traffic limit
    'expiry': 3      # 3 days before expiry
}

# Config Templates
CONFIG_TEMPLATES = {
    'basic': {'traffic': 30, 'days': 30, 'name': 'Basic Plan'},
    'premium': {'traffic': 60, 'days': 30, 'name': 'Premium Plan'},
    'ultimate': {'traffic': 100, 'days': 30, 'name': 'Ultimate Plan'}
}

# Rate Limiting
class RateLimit:
    def __init__(self, max_requests=5, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, user_id):
        now = time.time()
        self.requests[user_id] = [t for t in self.requests[user_id] 
                                if now - t < self.window_seconds]
        if len(self.requests[user_id]) >= self.max_requests:
            return False
        self.requests[user_id].append(now)
        return True

# Initialize rate limiter
rate_limiter = RateLimit()

# Initialize bot with exception handling
try:
    bot = telebot.TeleBot(API_TOKEN)
    logging.info("Bot initialized successfully")
except Exception as e:
    logging.error(f"Failed to initialize bot: {e}")
    raise

# Analytics Functions
def save_analytics(data):
    try:
        analytics = []
        if os.path.exists(ANALYTICS_FILE):
            with open(ANALYTICS_FILE, 'r') as f:
                analytics = json.load(f)
        analytics.append(data)
        with open(ANALYTICS_FILE, 'w') as f:
            json.dump(analytics, f)
    except Exception as e:
        logging.error(f"Error saving analytics: {e}")

def track_command(user_id, command):
    analytics_data = {
        'timestamp': time.time(),
        'user_id': user_id,
        'command': command,
        'user_type': 'admin' if is_admin(user_id) else 'user'
    }
    save_analytics(analytics_data)

def save_feedback(feedback_data):
    try:
        feedback_list = []
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, 'r') as f:
                feedback_list = json.load(f)
        feedback_list.append(feedback_data)
        with open(FEEDBACK_FILE, 'w') as f:
            json.dump(feedback_list, f)
    except Exception as e:
        logging.error(f"Error saving feedback: {e}")

def notify_admin_feedback(feedback_data):
    feedback_msg = (
        f"📝 *New Feedback Received*\n\n"
        f"From: {feedback_data['username'] or 'Anonymous'}\n"
        f"User ID: {feedback_data['user_id']}\n"
        f"Time: {datetime.fromtimestamp(feedback_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Feedback:\n{feedback_data['feedback']}"
    )
    for admin_id in ADMIN_USER_IDS:
        try:
            bot.send_message(admin_id, feedback_msg, parse_mode="Markdown")
        except:
            logging.error(f"Failed to notify admin {admin_id} about feedback")

def is_critical_error(error):
    critical_patterns = [
        "authentication failed",
        "permission denied",
        "connection refused",
        "database error",
        "fatal error"
    ]
    return any(pattern in str(error).lower() for pattern in critical_patterns)

def notify_admin(message):
    for admin_id in ADMIN_USER_IDS:
        try:
            bot.send_message(admin_id, message, parse_mode="Markdown")
        except:
            logging.error(f"Failed to notify admin {admin_id}")

def log_error(error, context=None):
    logging.error(f"Error: {error}, Context: {context}")
    if is_critical_error(error):
        notify_admin(f"🚨 *Critical Error*\n\n{error}\nContext: {context}")

diagnose_mode = False

def run_cli_command(command):
    try:
        args = shlex.split(command)
        result = subprocess.check_output(args, stderr=subprocess.STDOUT)
        return result.decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        return f'Error: {e.output.decode("utf-8")}'

def create_main_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('➕ Add User', '👥 Show User')
    markup.row('❌ Delete User', '📊 Server Info')
    markup.row('💾 Backup Server', '📈 Sales Stats')
    markup.row('📊 User Stats', '🔔 Notifications')
    markup.row('🔄 Update All Users', '📝 Edit Help Message')
    markup.row('📢 Broadcast Message', '🔍 Toggle Diagnose Mode')
    return markup

def create_client_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📱 View My Config', '💰 View Available Plans')
    markup.row('⬇️ Downloads', '❓ Support/Help')
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    try:
        logging.info(f"Welcome message for user {message.from_user.id}")
        track_command(message.from_user.id, 'start')
        if is_admin(message.from_user.id):
            markup = create_main_markup()
            bot.reply_to(message, "Welcome Admin! Choose an option:", reply_markup=markup)
        else:
            markup = create_client_markup()
            help_text = load_help_message() or DEFAULT_HELP_MESSAGE
            bot.reply_to(message, help_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in welcome handler: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: message.text == '👤 View My Config')
def handle_view_config(message):
    try:
        logging.info(f"View config request from {message.from_user.id}")
        view_my_config(message)
    except Exception as e:
        logging.error(f"Error in view config: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: message.text == '💰 View Available Plans')
def handle_view_plans(message):
    try:
        logging.info(f"View plans request from {message.from_user.id}")
        view_available_plans(message)
    except Exception as e:
        logging.error(f"Error in view plans: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: message.text == '📥 Downloads')
def handle_downloads(message):
    try:
        logging.info(f"Downloads request from {message.from_user.id}")
        show_downloads(message)
    except Exception as e:
        logging.error(f"Error in downloads: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: message.text == '❓ Support/Help')
def handle_support(message):
    try:
        logging.info(f"Support request from {message.from_user.id}")
        support_help(message)
    except Exception as e:
        logging.error(f"Error in support: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text in [
    '➕ Add User', '👥 Show User', '❌ Delete User', '📊 Server Info',
    '💾 Backup Server', '📈 Sales Stats', '📊 User Stats', '🔔 Notifications',
    '🔄 Update All Users', '📝 Edit Help Message', '📢 Broadcast Message',
    '🔍 Toggle Diagnose Mode', '📋 Templates'
])
def handle_admin_menu(message):
    try:
        logging.info(f"Admin menu request: {message.text} from {message.from_user.id}")
        track_command(message.from_user.id, message.text)
        
        admin_functions = {
            '➕ Add User': add_user,
            '👥 Show User': show_user,
            '❌ Delete User': delete_user,
            '📊 Server Info': server_info,
            '💾 Backup Server': backup_server,
            '📈 Sales Stats': show_sales_stats,
            '📊 User Stats': show_user_stats,
            '🔄 Update All Users': update_all_users,
            '📝 Edit Help Message': edit_help_message,
            '📢 Broadcast Message': broadcast_message,
            '🔍 Toggle Diagnose Mode': toggle_diagnose_mode,
            '📋 Templates': show_templates
        }
        
        if message.text in admin_functions:
            admin_functions[message.text](message)
        else:
            bot.reply_to(message, "Invalid admin command")
            
    except Exception as e:
        logging.error(f"Error in admin menu handler: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        logging.info(f"Callback query: {call.data} from {call.from_user.id}")
        
        if call.data.startswith('edit_') or call.data.startswith('renew_') or call.data.startswith('block_') or call.data.startswith('reset_') or call.data.startswith('ipv6_'):
            handle_edit_callback(call)
        elif call.data.startswith('confirm_block:'):
            handle_block_confirmation(call)
        elif call.data.startswith('broadcast:'):
            handle_broadcast_selection(call)
        elif call.data.startswith('update_all:'):
            handle_update_all(call)
        elif call.data.startswith('purchase_plan:'):
            handle_purchase(call)
        elif call.data.startswith('template_'):
            handle_template_selection(call)
        else:
            bot.answer_callback_query(call.id, "Invalid callback query")
            
    except Exception as e:
        logging.error(f"Error in callback handler: {e}")
        bot.answer_callback_query(call.id, "An error occurred")

@bot.message_handler(commands=['feedback'])
def handle_feedback(message):
    try:
        logging.info(f"Feedback command from {message.from_user.id}")
        collect_feedback(message)
    except Exception as e:
        logging.error(f"Error in feedback handler: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    try:
        logging.info(f"Unknown message: {message.text} from {message.from_user.id}")
        if is_admin(message.from_user.id):
            bot.reply_to(message, "Unknown command. Please use the menu buttons.")
        else:
            bot.reply_to(message, "Unknown command. Please use the menu or type /help")
    except Exception as e:
        logging.error(f"Error in fallback handler: {e}")
        bot.reply_to(message, "An error occurred. Please try again.")

def add_user(message):
    msg = bot.reply_to(message, "Enter username:")
    bot.register_next_step_handler(msg, process_add_user_step1)

def process_add_user_step1(message):
    username = message.text.strip()
    if username == "":
        bot.reply_to(message, "Username cannot be empty. Please enter a valid username.")
        return

    command = f"python3 {CLI_PATH} list-users"
    result = run_cli_command(command)
    
    try:
        users = json.loads(result)
        existing_users = {user.lower() for user in users.keys()}

        if username.lower() in existing_users:
            bot.reply_to(message, f"Username '{username}' already exists. Please choose a different username.")
            msg = bot.reply_to(message, "Enter a new username:")
            bot.register_next_step_handler(msg, process_add_user_step1)
            return
    except json.JSONDecodeError:
        if "No such file or directory" in result or result.strip() == "":
            bot.reply_to(message, "User list file does not exist. Adding the first user.")
        else:
            bot.reply_to(message, "Error retrieving user list. Please try again later.")
            return

    msg = bot.reply_to(message, "Enter traffic limit (GB):")
    bot.register_next_step_handler(msg, process_add_user_step2, username)

def process_add_user_step2(message, username):
    try:
        traffic_limit = int(message.text.strip())
        msg = bot.reply_to(message, "Enter expiration days:")
        bot.register_next_step_handler(msg, process_add_user_step3, username, traffic_limit)
    except ValueError:
        bot.reply_to(message, "Invalid traffic limit. Please enter a number.")

def process_add_user_step3(message, username, traffic_limit):
    try:
        expiration_days = int(message.text.strip())
        lower_username = username.lower()
        command = f"python3 {CLI_PATH} add-user -u {username} -t {traffic_limit} -e {expiration_days}"
        result = run_cli_command(command)
        bot.send_chat_action(message.chat.id, 'typing')
        qr_command = f"python3 {CLI_PATH} show-user-uri -u {lower_username} -ip 4"
        qr_result = run_cli_command(qr_command).replace("IPv4:\n", "").strip()

        if not qr_result:
            bot.reply_to(message, "Failed to generate QR code.")
            return

        qr_v4 = qrcode.make(qr_result)
        bio_v4 = io.BytesIO()
        qr_v4.save(bio_v4, 'PNG')
        bio_v4.seek(0)
        caption = f"{result}\n\n`{qr_result}`"
        bot.send_photo(message.chat.id, bio_v4, caption=caption, parse_mode="Markdown")

    except ValueError:
        bot.reply_to(message, "Invalid expiration days. Please enter a number.")

def show_user(message):
    msg = bot.reply_to(message, "Enter username:")
    bot.register_next_step_handler(msg, process_show_user)

def process_show_user(message):
    username = message.text.strip().lower()
    bot.send_chat_action(message.chat.id, 'typing')
    command = f"python3 {CLI_PATH} list-users"
    result = run_cli_command(command)

    try:
        users = json.loads(result)
        existing_users = {user.lower(): user for user in users.keys()}

        if username not in existing_users:
            bot.reply_to(message, f"Username '{message.text.strip()}' does not exist. Please enter a valid username.")
            return

        actual_username = existing_users[username]
    except json.JSONDecodeError:
        bot.reply_to(message, "Error retrieving user list. Please try again later.")
        return

    command = f"python3 {CLI_PATH} get-user -u {actual_username}"
    user_result = run_cli_command(command)

    try:
        user_details = json.loads(user_result)
        
        upload_bytes = user_details.get('upload_bytes')
        download_bytes = user_details.get('download_bytes')
        status = user_details.get('status', 'Unknown')

        if upload_bytes is None or download_bytes is None:
            traffic_message = "**Traffic Data:**\nUser not active or no traffic data available."
        else:
            upload_gb = upload_bytes / (1024 ** 3)  # Convert bytes to GB
            download_gb = download_bytes / (1024 ** 3)  # Convert bytes to GB
            
            traffic_message = (
                f"**Traffic Data:**\n"
                f"Upload: {upload_gb:.2f} GB\n"
                f"Download: {download_gb:.2f} GB\n"
                f"Status: {status}"
            )
    except json.JSONDecodeError:
        bot.reply_to(message, "Failed to parse JSON data. The command output may be malformed.")
        return

    formatted_details = (
        f"**User Details:**\n\n"
        f"Name: {actual_username}\n"
        f"Traffic Limit: {user_details['max_download_bytes'] / (1024 ** 3):.2f} GB\n"
        f"Days: {user_details['expiration_days']}\n"
        f"Account Creation: {user_details['account_creation_date']}\n"
        f"Blocked: {user_details['blocked']}\n\n"
        f"{traffic_message}"
    )

    combined_command = f"python3 {CLI_PATH} show-user-uri -u {actual_username} -ip 4 -s -n"
    combined_result = run_cli_command(combined_command)

    if "Error" in combined_result or "Invalid" in combined_result:
        bot.reply_to(message, combined_result)
        return

    result_lines = combined_result.strip().split('\n')
    
    uri_v4 = ""
    singbox_sublink = ""
    normal_sub_sublink = ""

    for line in result_lines:
        line = line.strip()
        if line.startswith("hy2://"):
            uri_v4 = line
        elif line.startswith("Singbox Sublink:"):
            singbox_sublink = result_lines[result_lines.index(line) + 1].strip()
        elif line.startswith("Normal-SUB Sublink:"):
            normal_sub_sublink = result_lines[result_lines.index(line) + 1].strip()

    if not uri_v4:
        bot.reply_to(message, "No valid URI found.")
        return

    qr_v4 = qrcode.make(uri_v4)
    bio_v4 = io.BytesIO()
    qr_v4.save(bio_v4, 'PNG')
    bio_v4.seek(0)

    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(types.InlineKeyboardButton("Reset User", callback_data=f"reset_user:{actual_username}"),
               types.InlineKeyboardButton("IPv6-URI", callback_data=f"ipv6_uri:{actual_username}"))
    markup.add(types.InlineKeyboardButton("Edit Username", callback_data=f"edit_username:{actual_username}"),
               types.InlineKeyboardButton("Edit Traffic Limit", callback_data=f"edit_traffic:{actual_username}"))
    markup.add(types.InlineKeyboardButton("Edit Expiration Days", callback_data=f"edit_expiration:{actual_username}"),
               types.InlineKeyboardButton("Renew Password", callback_data=f"renew_password:{actual_username}"))
    markup.add(types.InlineKeyboardButton("Renew Creation Date", callback_data=f"renew_creation:{actual_username}"),
               types.InlineKeyboardButton("Block User", callback_data=f"block_user:{actual_username}"))

    caption = f"{formatted_details}\n\n**IPv4 URI:**\n\n`{uri_v4}`"
    if singbox_sublink:
        caption += f"\n\n**SingBox SUB:**\n{singbox_sublink}"
    if normal_sub_sublink:
        caption += f"\n\n**Normal SUB:**\n{normal_sub_sublink}"

    bot.send_photo(
        message.chat.id,
        bio_v4,
        caption=caption,
        reply_markup=markup,
        parse_mode="Markdown"
    )


def server_info(message):
    command = f"python3 {CLI_PATH} server-info"
    result = run_cli_command(command)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.reply_to(message, result)

def delete_user(message):
    msg = bot.reply_to(message, "Enter username:")
    bot.register_next_step_handler(msg, process_delete_user)

def process_delete_user(message):
    username = message.text.strip().lower()
    command = f"python3 {CLI_PATH} remove-user -u {username}"
    result = run_cli_command(command)
    
    if "Error" not in result:
        # Remove from user_data.json
        user_data = load_user_data()
        for user_id, user_configs in user_data.items():
            if isinstance(user_configs, list):
                user_data[user_id] = [config for config in user_configs if config.get('username') != username]
            elif isinstance(user_configs, dict) and user_configs.get('username') == username:
                del user_data[user_id]
        save_user_data(user_data)
    
    bot.reply_to(message, result)

def backup_server(message):
    bot.reply_to(message, "Starting backup. This may take a few moments...")
    bot.send_chat_action(message.chat.id, 'typing')
    
    backup_command = f"python3 {CLI_PATH} backup-hysteria"
    result = run_cli_command(backup_command)

    if "Error" in result:
        bot.reply_to(message, f"Backup failed: {result}")
    else:
        bot.reply_to(message, "Backup completed successfully!")

    
    try:
        files = [f for f in os.listdir(BACKUP_DIRECTORY) if f.endswith('.zip')]
        files.sort(key=lambda x: os.path.getctime(os.path.join(BACKUP_DIRECTORY, x)), reverse=True)
        latest_backup_file = files[0] if files else None
    except Exception as e:
        bot.reply_to(message, f"Failed to locate the backup file: {str(e)}")
        return
    
    if latest_backup_file:
        backup_file_path = os.path.join(BACKUP_DIRECTORY, latest_backup_file)
        with open(backup_file_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"Backup completed: {latest_backup_file}")
    else:
        bot.reply_to(message, "No backup file found after the backup process.")

def show_downloads(message):
    markup = types.InlineKeyboardMarkup()
    
    # Android buttons
    android_play = types.InlineKeyboardButton(
        "📱 Android (PlayStore)", 
        url="https://play.google.com/store/apps/details?id=app.hiddify.com&hl=en"
    )
    android_github = types.InlineKeyboardButton(
        "📱 Android (Github)", 
        url="https://github.com/hiddify/hiddify-next/releases/download/v2.0.5/Hiddify-Android-arm64.apk"
    )
    markup.row(android_play)
    markup.row(android_github)
    
    # iOS button
    ios = types.InlineKeyboardButton(
        "🍎 iOS (AppStore)", 
        url="https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532"
    )
    markup.row(ios)
    
    # Windows button
    windows = types.InlineKeyboardButton(
        "💻 Windows (Github)", 
        url="https://github.com/hiddify/hiddify-next/releases/download/v2.0.5/Hiddify-Windows-Setup-x64.exe"
    )
    markup.row(windows)
    
    # Other platforms button
    other_platforms = types.InlineKeyboardButton(
        "🌐 Other platforms (Github)", 
        url="https://github.com/hiddify/hiddify-app/releases/tag/v2.0.5"
    )
    markup.row(other_platforms)
    
    bot.send_message(
        message.chat.id,
        "📶 *Download Hiddify Client*\n\n"
        "Please select your platform to download the Hiddify client for your VPN connection:",
        parse_mode="Markdown",
        reply_markup=markup
    )

def toggle_diagnose_mode(message):
    global diagnose_mode
    diagnose_mode = not diagnose_mode
    status = "ON" if diagnose_mode else "OFF"
    bot.reply_to(message, f"Diagnose mode is now {status}.")

def broadcast_message(message):
    markup = types.InlineKeyboardMarkup()
    all_users = types.InlineKeyboardButton("👥 All Users", callback_data="broadcast:all")
    active_users = types.InlineKeyboardButton("✅ Active Users", callback_data="broadcast:active")
    expired_users = types.InlineKeyboardButton("⛔️ Expired Users", callback_data="broadcast:expired")
    markup.row(all_users)
    markup.row(active_users)
    markup.row(expired_users)
    
    bot.reply_to(message, "Select users to send message to:", reply_markup=markup)

def handle_broadcast_selection(call):
    _, user_type = call.data.split(':')
    msg = bot.send_message(
        call.message.chat.id, 
        "Enter your message to broadcast:\n\n"
        "Note: You can use Markdown formatting.\n"
        "Use /cancel to cancel broadcasting."
    )
    bot.register_next_step_handler(msg, process_broadcast_message, user_type)

def process_broadcast_message(message, user_type):
    if message.text == '/cancel':
        bot.reply_to(message, "Broadcasting cancelled.")
        return

    # Get all users from CLI
    command = f"python3 {CLI_PATH} list-users"
    result = run_cli_command(command)
    try:
        users = json.loads(result)
    except json.JSONDecodeError:
        bot.reply_to(message, "❌ Error: Could not get user list.")
        return

    # Load user_data.json to get Telegram IDs
    user_data = load_user_data()
    
    # Create a mapping of usernames to telegram IDs
    username_to_tid = {}
    for tid, configs in user_data.items():
        if isinstance(configs, list):
            for config in configs:
                username = config.get('username')
                if username:
                    username_to_tid[username] = tid

    sent_count = 0
    failed_count = 0
    
    # Filter users based on selection
    target_users = []
    for username, details in users.items():
        if user_type == 'all':
            target_users.append(username)
        elif user_type == 'active' and not details.get('blocked', False):
            target_users.append(username)
        elif user_type == 'expired' and details.get('blocked', False):
            target_users.append(username)

    # Send progress message
    progress_msg = bot.reply_to(message, f"📤 Sending messages to {len(target_users)} users...")

    # Send messages
    for username in target_users:
        tid = username_to_tid.get(username)
        if tid:
            try:
                bot.send_message(int(tid), message.text, parse_mode="Markdown")
                sent_count += 1
                # Update progress every 5 messages
                if sent_count % 5 == 0:
                    bot.edit_message_text(
                        f"📤 Sending messages... ({sent_count}/{len(target_users)})",
                        message.chat.id,
                        progress_msg.message_id
                    )
            except Exception as e:
                print(f"Failed to send message to {username}: {str(e)}")
                failed_count += 1

    # Final report
    report = (
        f"📢 *Broadcast Complete*\n\n"
        f"✅ Successfully sent: {sent_count}\n"
        f"❌ Failed: {failed_count}\n"
        f"👥 Total users targeted: {len(target_users)}\n\n"
        f"User group: {user_type.title()}"
    )
    bot.edit_message_text(report, message.chat.id, progress_msg.message_id, parse_mode="Markdown")

def load_user_data():
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading user data: {str(e)}")
        return {}

def save_user_data(data):
    try:
        os.makedirs(os.path.dirname(USER_DATA_FILE), exist_ok=True)
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving user data: {str(e)}")

def load_help_message():
    try:
        if os.path.exists(HELP_MESSAGE_FILE):
            with open(HELP_MESSAGE_FILE, 'r') as f:
                return f.read()
    except Exception as e:
        print(f"Error loading help message: {str(e)}")
    return DEFAULT_HELP_MESSAGE

def save_help_message(message):
    try:
        with open(HELP_MESSAGE_FILE, 'w') as f:
            f.write(message)
    except Exception as e:
        print(f"Error saving help message: {str(e)}")

DEFAULT_HELP_MESSAGE = """**Welcome to Our VPN Service!**\n\n
🔹 To view your configurations, click 'View My Config'\n
🔹 To see available plans, click 'View Available Plans'\n
🔹 To download VPN client, click 'Downloads'\n\n
For support, contact: @admin_username"""

def edit_help_message(message):
    current_message = load_help_message()
    msg = bot.reply_to(message, 
                      "Current help message is:\n\n" + current_message + 
                      "\n\nSend the new help message (or 'cancel' to keep current):")
    bot.register_next_step_handler(msg, process_edit_help_message)

def process_edit_help_message(message):
    if message.text.lower() == 'cancel':
        bot.reply_to(message, "Help message update cancelled.")
        return
    
    save_help_message(message.text)
    bot.reply_to(message, "Help message updated successfully!")

def update_all_users(message):
    markup = types.InlineKeyboardMarkup()
    days_btn = types.InlineKeyboardButton("➕ Add Days", callback_data="update_all:days")
    data_btn = types.InlineKeyboardButton("📊 Add Data", callback_data="update_all:data")
    markup.row(days_btn, data_btn)
    
    bot.reply_to(message, "Choose what to update for all users:", reply_markup=markup)

def handle_update_all(call):
    _, update_type = call.data.split(':')
    if update_type == 'days':
        msg = bot.send_message(call.message.chat.id, "Enter the number of days to add:")
        bot.register_next_step_handler(msg, process_update_all_days)
    else:
        msg = bot.send_message(call.message.chat.id, "Enter the amount of data to add (in GB):")
        bot.register_next_step_handler(msg, process_update_all_data)

def process_update_all_days(message):
    try:
        days = int(message.text)
        command = f"python3 {CLI_PATH} list-users"
        result = run_cli_command(command)
        users = json.loads(result)
        
        success_count = 0
        for username in users.keys():
            update_command = f"python3 {CLI_PATH} edit-user -u {username} -e {days}"
            update_result = run_cli_command(update_command)
            if "Error" not in update_result:
                success_count += 1
                
                # Update user_data.json
                user_data = load_user_data()
                for user_id, user_configs in user_data.items():
                    if isinstance(user_configs, list):
                        for config in user_configs:
                            if config.get('username') == username:
                                config['days'] = config.get('days', 30) + days
                save_user_data(user_data)
        
        bot.reply_to(message, f"✅ Successfully added {days} days to {success_count} users!")
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number.")

def process_update_all_data(message):
    try:
        gb = int(message.text)
        command = f"python3 {CLI_PATH} list-users"
        result = run_cli_command(command)
        users = json.loads(result)
        
        success_count = 0
        for username in users.keys():
            update_command = f"python3 {CLI_PATH} edit-user -u {username} -t {gb}"
            update_result = run_cli_command(update_command)
            if "Error" not in update_result:
                success_count += 1
                
                # Update user_data.json
                user_data = load_user_data()
                for user_id, user_configs in user_data.items():
                    if isinstance(user_configs, list):
                        for config in user_configs:
                            if config.get('username') == username:
                                config['gb'] = config.get('gb', 0) + gb
                save_user_data(user_data)
        
        bot.reply_to(message, f"✅ Successfully added {gb}GB to {success_count} users!")
    except ValueError:
        bot.reply_to(message, "❌ Please enter a valid number.")

def view_my_config(message):
    user_id = str(message.from_user.id)
    user_data = load_user_data()

    if user_id not in user_data:
        bot.reply_to(message, "You don't have any active configuration. Please purchase a plan first.")
        return

    user_configs = user_data[user_id]
    if not isinstance(user_configs, list):
        user_configs = [user_configs]
        user_data[user_id] = user_configs
        save_user_data(user_data)

    # Send a processing message
    bot.reply_to(message, "Fetching your configurations, please wait...")

    # Process each config one by one
    for config in user_configs:
        username = config.get('username')
        if not username:
            continue

        # Check if config exists and is not blocked
        details_command = f"python3 {CLI_PATH} get-user -u {username}"
        details_result = run_cli_command(details_command)
        
        try:
            user_details = json.loads(details_result)
            if user_details.get('blocked', False):
                continue  # Skip blocked configs
        except json.JSONDecodeError:
            print(f"Failed to parse user details for {username}: {details_result}")
            continue
        except Exception as e:
            print(f"Error checking user {username}: {str(e)}")
            continue

        # Get config URI
        uri_command = f"python3 {CLI_PATH} show-user-uri -u {username} -ip 4 -s"
        uri_result = run_cli_command(uri_command)
        
        if "Error" in uri_result:
            print(f"Error getting URI for {username}: {uri_result}")
            continue

        qr_result = uri_result.replace("IPv4:\n", "").strip()
        if "Warning: IP4 or IP6" in qr_result:
            qr_result = qr_result.split('\n')[-1].strip()
        
        try:
            qr = qrcode.make(qr_result)
            bio = io.BytesIO()
            qr.save(bio, 'PNG')
            bio.seek(0)

            traffic_limit = user_details.get('max_download_bytes', 0) / (1024 ** 3)
            used_traffic = (user_details.get('upload_bytes', 0) + user_details.get('download_bytes', 0)) / (1024 ** 3)
            expiration_days = user_details.get('expiration_days', 0)
            
            is_diagnose = username.endswith('d')
            mode_text = "(Diagnose Mode)" if is_diagnose else ""
            
            caption = (
                f"**Configuration {mode_text}**\n\n"
                f"Plan: {config['plan'].title()}\n"
                f"Username: {username}\n"
                f"Traffic Usage: {used_traffic:.2f}GB / {traffic_limit:.2f}GB\n"
                f"Days Remaining: {expiration_days}\n"
                f"Purchase Date: {config['purchase_date']}\n\n"
                f"**Connection URI:**\n`{qr_result}`"
            )
            
            # Send each config as a separate message
            bot.send_photo(
                message.chat.id,
                bio,
                caption=caption,
                parse_mode="Markdown"
            )
            
            # Add a small delay between messages to avoid flooding
            time.sleep(1)
            
        except Exception as e:
            print(f"Error sending config {username}: {str(e)}")
            continue

def view_available_plans(message):
    plans = [
        "🚀 Basic Plan\n- 30GB Traffic\n- 30 Days\n- Price: $1.8",
        "⭐ Premium Plan\n- 60GB Traffic\n- 30 Days\n- Price: $3",
        "💎 Ultimate Plan\n- 100GB Traffic\n- 30 Days\n- Price: $4.2"
    ]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Purchase Basic Plan (30GB)", callback_data="purchase_plan:basic:30"),
        types.InlineKeyboardButton("Purchase Premium Plan (60GB)", callback_data="purchase_plan:premium:60"),
        types.InlineKeyboardButton("Purchase Ultimate Plan (100GB)", callback_data="purchase_plan:ultimate:100")
    )
    
    response = "**Available Plans:**\n\n" + "\n\n".join(plans)
    if not diagnose_mode:
        response += "\n\n_Payment system coming soon!_"
    else:
        response += "\n\n_⚠️ Diagnose Mode Active: Test purchases available_"
    
    bot.reply_to(message, response, reply_markup=markup, parse_mode="Markdown")

def handle_purchase(call):
    if not diagnose_mode:
        bot.answer_callback_query(call.id, "Payment system is not available yet!")
        return

    _, plan_type, gb = call.data.split(':')
    user_id = str(call.from_user.id)
    gb = int(gb)
    
    # Generate username with numeric ID and timestamp
    current_time = time.strftime('%Y%m%d%H%M%S')
    username = f"{user_id}d{current_time}"
    if diagnose_mode:
        username = f"{username}d"
    
    command = f"python3 {CLI_PATH} add-user -u {username} -t {gb} -e 30"
    result = run_cli_command(command)
    
    if "Error" in result:
        bot.answer_callback_query(call.id, "Failed to create configuration")
        bot.reply_to(call.message, f"Error creating configuration: {result}")
        return

    uri_command = f"python3 {CLI_PATH} show-user-uri -u {username} -ip 4 -s"
    uri_result = run_cli_command(uri_command)
    
    if "Error" not in uri_result:
        qr_result = uri_result.replace("IPv4:\n", "").strip()
        if "Warning: IP4 or IP6" in qr_result:
            qr_result = qr_result.split('\n')[-1].strip()
        
        user_data = load_user_data()
        new_config = {
            'username': username,
            'plan': plan_type,
            'purchase_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'gb': gb,
            'days': 30
        }

        if user_id not in user_data:
            user_data[user_id] = []
        elif not isinstance(user_data[user_id], list):
            user_data[user_id] = [user_data[user_id]]
        
        user_data[user_id].append(new_config)
        save_user_data(user_data)

        qr = qrcode.make(qr_result)
        bio = io.BytesIO()
        qr.save(bio, 'PNG')
        bio.seek(0)
        
        mode_text = "(Diagnose Mode)" if diagnose_mode else ""
        caption = (
            f"**Configuration Created! {mode_text}**\n\n"
            f"Plan: {plan_type.title()} ({gb}GB)\n"
            f"Username: {username}\n"
            f"Duration: 30 days\n\n"
            f"**Connection URI:**\n`{qr_result}`"
        )
        
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_photo(
            call.message.chat.id,
            bio,
            caption=caption,
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(call.message, "Failed to generate configuration URI. Please contact support.")

def generate_stats(user_data, start_time, end_time=None, diagnose_only=False):
    total_profit = 0
    total_configs = 0
    plan_counts = {'basic': 0, 'premium': 0, 'ultimate': 0}
    plan_prices = {'basic': 1.8, 'premium': 3, 'ultimate': 4.2}

    for user_configs in user_data.values():
        if not isinstance(user_configs, list):
            user_configs = [user_configs]

        for config in user_configs:
            username = config.get('username', '')
            purchase_date = config.get('purchase_date', '')
            
            if not purchase_date:
                continue

            try:
                purchase_time = time.strptime(purchase_date, '%Y-%m-%d %H:%M:%S')
                purchase_timestamp = time.mktime(purchase_time)
            except ValueError:
                continue
            
            if purchase_timestamp < start_time:
                continue
            if end_time and purchase_timestamp > end_time:
                continue

            # Check if it's a diagnose mode config
            is_diagnose = username.endswith('d')
            if diagnose_only and not is_diagnose:
                continue
            if not diagnose_only and is_diagnose:
                continue

            plan_type = config.get('plan', 'basic')
            plan_counts[plan_type] += 1
            total_profit += plan_prices[plan_type]
            total_configs += 1

    return total_configs, total_profit, plan_counts

def show_sales_stats(message):
    user_data = load_user_data()
    current_time = time.time()
    
    day_start = current_time - (24 * 60 * 60)  # 24 hours ago
    week_start = current_time - (7 * 24 * 60 * 60)  # 7 days ago

    day_configs, day_profit, day_plans = generate_stats(user_data, day_start)
    week_configs, week_profit, week_plans = generate_stats(user_data, week_start)

    day_test_configs, day_test_profit, day_test_plans = generate_stats(user_data, day_start, diagnose_only=True)
    week_test_configs, week_test_profit, week_test_plans = generate_stats(user_data, week_start, diagnose_only=True)

    stats_message = (
        "📊 **Sales Statistics**\n\n"
        "**Today's Sales:**\n"
        f"Total Configs: {day_configs}\n"
        f"Total Profit: ${day_profit:.2f}\n"
        f"Basic Plans: {day_plans['basic']}\n"
        f"Premium Plans: {day_plans['premium']}\n"
        f"Ultimate Plans: {day_plans['ultimate']}\n\n"
        
        "**Weekly Sales:**\n"
        f"Total Configs: {week_configs}\n"
        f"Total Profit: ${week_profit:.2f}\n"
        f"Basic Plans: {week_plans['basic']}\n"
        f"Premium Plans: {week_plans['premium']}\n"
        f"Ultimate Plans: {week_plans['ultimate']}\n\n"
        
        "🧪 **Diagnose Mode Stats**\n\n"
        "**Today's Test Configs:**\n"
        f"Total Test Configs: {day_test_configs}\n"
        f"Basic Plans: {day_test_plans['basic']}\n"
        f"Premium Plans: {day_test_plans['premium']}\n"
        f"Ultimate Plans: {day_test_plans['ultimate']}\n\n"
        
        "**Weekly Test Configs:**\n"
        f"Total Test Configs: {week_test_configs}\n"
        f"Basic Plans: {week_test_plans['basic']}\n"
        f"Premium Plans: {week_test_plans['premium']}\n"
        f"Ultimate Plans: {week_test_plans['ultimate']}"
    )

    bot.reply_to(message, stats_message, parse_mode="Markdown")

def support_help(message):
    help_text = load_help_message()
    bot.reply_to(message, help_text, parse_mode="Markdown")

def is_admin(user_id):
    return user_id in ADMIN_USER_IDS

def show_user_stats(message):
    track_command(message.from_user.id, 'user_stats')
    try:
        command = f"python3 {CLI_PATH} list-users"
        result = run_cli_command(command)
        users = json.loads(result)
        
        # Calculate statistics
        active_users = sum(1 for u in users.values() if not u.get('blocked', False))
        expired_users = sum(1 for u in users.values() if u.get('blocked', False))
        total_traffic = sum((u.get('upload_bytes', 0) + u.get('download_bytes', 0)) 
                          for u in users.values()) / (1024**3)
        
        # Calculate average usage
        active_traffic = 0
        active_count = 0
        for u in users.values():
            if not u.get('blocked', False):
                active_traffic += (u.get('upload_bytes', 0) + u.get('download_bytes', 0))
                active_count += 1
        avg_usage = (active_traffic / (1024**3)) / active_count if active_count > 0 else 0
        
        stats = (
            "📊 *User Statistics*\n\n"
            f"👥 *Total Users:* {len(users)}\n"
            f"✅ *Active Users:* {active_users}\n"
            f"⛔️ *Expired Users:* {expired_users}\n"
            f"📈 *Total Traffic:* {total_traffic:.2f}GB\n"
            f"📊 *Average Usage:* {avg_usage:.2f}GB per active user\n\n"
            f"*Usage Distribution:*\n"
            f"🟢 Low Usage (<5GB): {sum(1 for u in users.values() if (u.get('upload_bytes', 0) + u.get('download_bytes', 0)) < 5*(1024**3))}\n"
            f"🟡 Medium Usage (5-20GB): {sum(1 for u in users.values() if 5*(1024**3) <= (u.get('upload_bytes', 0) + u.get('download_bytes', 0)) < 20*(1024**3))}\n"
            f"🔴 High Usage (>20GB): {sum(1 for u in users.values() if (u.get('upload_bytes', 0) + u.get('download_bytes', 0)) >= 20*(1024**3))}"
        )
        
        bot.reply_to(message, stats, parse_mode="Markdown")
    except Exception as e:
        log_error(e, "show_user_stats")
        bot.reply_to(message, "❌ Error fetching user statistics.")

def check_and_notify_users():
    try:
        command = f"python3 {CLI_PATH} list-users"
        result = run_cli_command(command)
        users = json.loads(result)
        user_data = load_user_data()
        
        for username, details in users.items():
            # Find Telegram ID
            telegram_id = None
            for tid, configs in user_data.items():
                if isinstance(configs, list):
                    for config in configs:
                        if config.get('username') == username:
                            telegram_id = int(tid)
                            break
            
            if not telegram_id:
                continue
                
            traffic_used = (details.get('upload_bytes', 0) + details.get('download_bytes', 0))
            traffic_limit = details.get('max_download_bytes', 0)
            days_left = details.get('expiration_days', 0)
            
            # Traffic warning
            if traffic_limit > 0:
                usage_percent = traffic_used / traffic_limit
                if usage_percent > NOTIFICATION_THRESHOLDS['traffic']:
                    remaining_gb = (traffic_limit - traffic_used) / (1024**3)
                    msg = (
                        "⚠️ *Traffic Warning*\n\n"
                        f"You have used {usage_percent*100:.1f}% of your traffic allowance.\n"
                        f"Remaining: {remaining_gb:.2f}GB"
                    )
                    try:
                        bot.send_message(telegram_id, msg, parse_mode="Markdown")
                    except:
                        logging.error(f"Failed to send traffic warning to user {username}")
            
            # Expiry warning
            if 0 < days_left <= NOTIFICATION_THRESHOLDS['expiry']:
                msg = (
                    "⚠️ *Expiration Warning*\n\n"
                    f"Your configuration will expire in {days_left} days.\n"
                    "Please renew your subscription to avoid service interruption."
                )
                try:
                    bot.send_message(telegram_id, msg, parse_mode="Markdown")
                except:
                    logging.error(f"Failed to send expiry warning to user {username}")
    
    except Exception as e:
        log_error(e, "check_and_notify_users")

def scheduled_backup():
    try:
        # Create backup
        backup_command = f"python3 {CLI_PATH} backup-hysteria"
        result = run_cli_command(backup_command)
        
        if "Error" in result:
            notify_admin(f"❌ Scheduled backup failed:\n{result}")
            return
            
        # Rotate old backups
        files = sorted(
            [f for f in os.listdir(BACKUP_DIRECTORY) if f.endswith('.zip')],
            key=lambda x: os.path.getctime(os.path.join(BACKUP_DIRECTORY, x))
        )
        
        if len(files) > MAX_BACKUPS:
            for old_file in files[:-MAX_BACKUPS]:
                try:
                    os.remove(os.path.join(BACKUP_DIRECTORY, old_file))
                except Exception as e:
                    logging.error(f"Failed to remove old backup {old_file}: {e}")
        
        notify_admin("✅ Scheduled backup completed successfully")
    
    except Exception as e:
        log_error(e, "scheduled_backup")

def run_scheduler():
    schedule.every().day.at("00:00").do(scheduled_backup)
    schedule.every(6).hours.do(check_and_notify_users)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Start scheduler in a separate thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()

def collect_feedback(message):
    track_command(message.from_user.id, 'feedback')
    if not rate_limiter.is_allowed(message.from_user.id):
        bot.reply_to(message, "⚠️ Please wait a few minutes before submitting another feedback.")
        return
        
    msg = bot.reply_to(message, "📝 Please share your feedback (or /cancel):")
    bot.register_next_step_handler(msg, process_feedback)

def process_feedback(message):
    if message.text == '/cancel':
        bot.reply_to(message, "❌ Feedback cancelled.")
        return
        
    feedback_data = {
        'user_id': message.from_user.id,
        'username': message.from_user.username,
        'feedback': message.text,
        'timestamp': time.time()
    }
    
    try:
        save_feedback(feedback_data)
        notify_admin_feedback(feedback_data)
        bot.reply_to(message, "✅ Thank you for your feedback! Our team will review it.")
    except Exception as e:
        log_error(e, "process_feedback")
        bot.reply_to(message, "❌ Sorry, there was an error saving your feedback. Please try again later.")

def show_templates(message):
    track_command(message.from_user.id, 'show_templates')
    markup = types.InlineKeyboardMarkup()
    
    for template_id, template in CONFIG_TEMPLATES.items():
        btn_text = f"{template['name']} ({template['traffic']}GB, {template['days']} days)"
        markup.add(types.InlineKeyboardButton(
            btn_text,
            callback_data=f"template_{template_id}"
        ))
    
    bot.reply_to(
        message,
        "📋 *Available Templates*\nSelect a template to create a new user:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

def handle_template_selection(call):
    if not is_admin(call.from_user.id):
        return
        
    template_id = call.data.split('_')[1]
    if template_id not in CONFIG_TEMPLATES:
        bot.answer_callback_query(call.id, "❌ Invalid template")
        return
        
    template = CONFIG_TEMPLATES[template_id]
    msg = bot.send_message(
        call.from_user.id,
        f"Enter username for new user with template: {template['name']}\n"
        f"Traffic: {template['traffic']}GB\n"
        f"Days: {template['days']}"
    )
    bot.register_next_step_handler(msg, create_user_from_template, template)

def create_user_from_template(message, template):
    username = message.text.strip()
    if not username:
        bot.reply_to(message, "❌ Invalid username")
        return
        
    try:
        command = (
            f"python3 {CLI_PATH} add-user "
            f"-u {username} "
            f"-t {template['traffic']} "
            f"-e {template['days']}"
        )
        result = run_cli_command(command)
        
        if "Error" in result:
            bot.reply_to(message, f"❌ Failed to create user:\n{result}")
            return
            
        # Update user_data.json
        user_data = load_user_data()
        if str(message.from_user.id) not in user_data:
            user_data[str(message.from_user.id)] = []
            
        user_data[str(message.from_user.id)].append({
            'username': username,
            'template': template['name'],
            'created_at': time.time()
        })
        save_user_data(user_data)
        
        bot.reply_to(
            message,
            f"✅ User created successfully with template {template['name']}\n"
            f"Username: {username}\n"
            f"Traffic: {template['traffic']}GB\n"
            f"Days: {template['days']}"
        )
        
    except Exception as e:
        log_error(e, f"create_user_from_template: {username}")
        bot.reply_to(message, "❌ Error creating user. Please try again.")

def main():
    logging.info("Starting bot...")
    while True:
        try:
            logging.info("Bot polling started")
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            logging.error(f"Error in main polling loop: {e}")
            time.sleep(10)
            continue

if __name__ == '__main__':
    main()

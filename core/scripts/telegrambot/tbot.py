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
from crmus import CryptomusHandler

load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
ADMIN_USER_IDS = json.loads(os.getenv('ADMIN_USER_IDS'))
CLI_PATH = '/etc/hysteria/core/cli.py'
BACKUP_DIRECTORY = '/opt/hysbackup'
USER_DATA_FILE = '/etc/hysteria/user_data.json'  # Changed to server directory
HELP_MESSAGE_FILE = '/etc/hysteria/help_message.txt'
DEFAULT_HELP_MESSAGE = """**Welcome to Our VPN Service!**\n\n
🔹 To view your configurations, click '📱 View My Config'\n
🔹 To see available plans, click '💰 View Available Plans'\n
🔹 To download VPN client, click '⬇️ Downloads'\n\n
For support, contact: @admin_username"""
diagnose_mode = False

bot = telebot.TeleBot(API_TOKEN)

# Initialize Cryptomus handler
cryptomus = CryptomusHandler()

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
    markup.row('📢 Broadcast Message', '📝 Edit Help')
    markup.row('🔍 Toggle Diagnose Mode', '⚙️ Payment Settings')
    return markup

def create_client_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📱 View My Config', '💰 View Available Plans')
    markup.row('⬇️ Downloads', '❓ Support/Help')
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_admin(message.from_user.id):
        markup = create_main_markup()
        bot.reply_to(message, "Welcome to the User Management Bot!", reply_markup=markup)
    else:
        markup = create_client_markup()
        bot.reply_to(message, "Welcome to our VPN service!", reply_markup=markup)

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '➕ Add User')
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
        bot.send_photo(message.chat.id, photo=bio_v4, caption=caption, parse_mode="Markdown")

    except ValueError:
        bot.reply_to(message, "Invalid expiration days. Please enter a number.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '👥 Show User')
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


@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '📊 Server Info')
def server_info(message):
    command = f"python3 {CLI_PATH} server-info"
    result = run_cli_command(command)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.reply_to(message, result)

@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_') or call.data.startswith('renew_') or call.data.startswith('block_') or call.data.startswith('reset_') or call.data.startswith('ipv6_'))
def handle_edit_callback(call):
    action, username = call.data.split(':')
    if action == 'edit_username':
        msg = bot.send_message(call.message.chat.id, f"Enter new username for {username}:")
        bot.register_next_step_handler(msg, process_edit_username, username)
    elif action == 'edit_traffic':
        msg = bot.send_message(call.message.chat.id, f"Enter new traffic limit (GB) for {username}:")
        bot.register_next_step_handler(msg, process_edit_traffic, username)
    elif action == 'edit_expiration':
        msg = bot.send_message(call.message.chat.id, f"Enter new expiration days for {username}:")
        bot.register_next_step_handler(msg, process_edit_expiration, username)
    elif action == 'renew_password':
        command = f"python3 {CLI_PATH} edit-user -u {username} -rp"
        result = run_cli_command(command)
        bot.send_message(call.message.chat.id, result)
    elif action == 'renew_creation':
        command = f"python3 {CLI_PATH} edit-user -u {username} -rc"
        result = run_cli_command(command)
        bot.send_message(call.message.chat.id, result)
    elif action == 'block_user':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("True", callback_data=f"confirm_block:{username}:true"),
                   types.InlineKeyboardButton("False", callback_data=f"confirm_block:{username}:false"))
        bot.send_message(call.message.chat.id, f"Set block status for {username}:", reply_markup=markup)
    elif action == 'reset_user':
        command = f"python3 {CLI_PATH} reset-user -u {username}"
        result = run_cli_command(command)
        bot.send_message(call.message.chat.id, result)
    elif action == 'ipv6_uri':
        command = f"python3 {CLI_PATH} show-user-uri -u {username} -ip 6"
        result = run_cli_command(command)
        if "Error" in result or "Invalid" in result:
            bot.send_message(call.message.chat.id, result)
            return
        
        uri_v6 = result.split('\n')[-1].strip()
        qr_v6 = qrcode.make(uri_v6)
        bio_v6 = io.BytesIO()
        qr_v6.save(bio_v6, 'PNG')
        bio_v6.seek(0)
        
        bot.send_photo(
            call.message.chat.id,
            bio_v6,
            caption=f"**IPv6 URI for {username}:**\n\n`{uri_v6}`",
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_block:'))
def handle_block_confirmation(call):
    _, username, block_status = call.data.split(':')
    command = f"python3 {CLI_PATH} edit-user -u {username} {'-b' if block_status == 'true' else ''}"
    result = run_cli_command(command)
    bot.send_message(call.message.chat.id, result)

def process_edit_username(message, username):
    new_username = message.text.strip()
    command = f"python3 {CLI_PATH} edit-user -u {username} -nu {new_username}"
    result = run_cli_command(command)
    bot.reply_to(message, result)

def process_edit_traffic(message, username):
    try:
        new_traffic_limit = int(message.text.strip())
        command = f"python3 {CLI_PATH} edit-user -u {username} -nt {new_traffic_limit}"
        result = run_cli_command(command)
        bot.reply_to(message, result)
    except ValueError:
        bot.reply_to(message, "Invalid traffic limit. Please enter a number.")

def process_edit_expiration(message, username):
    try:
        new_expiration_days = int(message.text.strip())
        command = f"python3 {CLI_PATH} edit-user -u {username} -ne {new_expiration_days}"
        result = run_cli_command(command)
        bot.reply_to(message, result)
    except ValueError:
        bot.reply_to(message, "Invalid expiration days. Please enter a number.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '❌ Delete User')
def delete_user(message):
    msg = bot.reply_to(message, "Enter username:")
    bot.register_next_step_handler(msg, process_delete_user)

def process_delete_user(message):
    username = message.text.strip().lower()
    command = f"python3 {CLI_PATH} remove-user -u {username}"
    result = run_cli_command(command)
    bot.reply_to(message, result)

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '💾 Backup Server')
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

@bot.inline_handler(lambda query: is_admin(query.from_user.id))
def handle_inline_query(query):
    command = f"python3 {CLI_PATH} list-users"
    result = run_cli_command(command)
    try:
        users = json.loads(result)
    except json.JSONDecodeError:
        bot.answer_inline_query(query.id, results=[], switch_pm_text="Error retrieving users.", switch_pm_user_id=query.from_user.id)
        return

    query_text = query.query.lower()
    results = []
    for username, details in users.items():
        if query_text in username.lower():
            title = f"{username}"
            description = f"Traffic Limit: {details['max_download_bytes'] / (1024 ** 3):.2f} GB, Expiration Days: {details['expiration_days']}"
            results.append(types.InlineQueryResultArticle(
                id=username,
                title=title,
                description=description,
                input_message_content=types.InputTextMessageContent(
                    message_text=f"Name: {username}\n"
                                 f"Traffic limit: {details['max_download_bytes'] / (1024 ** 3):.2f} GB\n"
                                 f"Days: {details['expiration_days']}\n"
                                 f"Account Creation: {details['account_creation_date']}\n"
                                 f"Blocked: {details['blocked']}"
                )
            ))

    bot.answer_inline_query(query.id, results, cache_time=0)

@bot.message_handler(func=lambda message: message.text == '⬇️ Downloads')
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

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '📢 Broadcast Message')
def broadcast_message(message):
    markup = types.InlineKeyboardMarkup()
    all_users = types.InlineKeyboardButton("👥 All Users", callback_data="broadcast:all")
    active_users = types.InlineKeyboardButton("✅ Active Users", callback_data="broadcast:active")
    expired_users = types.InlineKeyboardButton("⛔️ Expired Users", callback_data="broadcast:expired")
    markup.row(all_users)
    markup.row(active_users)
    markup.row(expired_users)
    
    bot.reply_to(message, "Select users to send message to:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast:'))
def handle_broadcast_selection(call):
    _, user_type = call.data.split(':')
    msg = bot.send_message(
        call.message.chat.id,
        "Enter your message to broadcast (or /cancel):"
    )
    bot.register_next_step_handler(msg, process_broadcast_message, user_type)

def process_broadcast_message(message, user_type):
    if message.text == '/cancel':
        bot.reply_to(message, "Broadcast cancelled.")
        return
        
    try:
        # Get list of users
        command = f"python3 {CLI_PATH} list-users"
        result = run_cli_command(command)
        users = json.loads(result)
        
        # Load user_data.json to get Telegram IDs
        user_data = load_user_data()
        
        # Create a mapping of username to telegram_id to avoid duplicates
        username_to_tid = {}
        for tid, configs in user_data.items():
            if isinstance(configs, list):
                for config in configs:
                    username = config.get('username')
                    if username and username in users:  # Only include if user exists in CLI list
                        username_to_tid[username] = int(tid)
        
        # Initialize counters
        sent_count = 0
        failed_count = 0
        processed_tids = set()  # Track which Telegram IDs we've already sent to
        
        # Process each unique username
        for username, details in users.items():
            # Filter based on user type
            if user_type == 'active' and details.get('blocked', False):
                continue
            if user_type == 'expired' and not details.get('blocked', False):
                continue
            
            telegram_id = username_to_tid.get(username)
            
            if not telegram_id or telegram_id in processed_tids:
                continue
                
            try:
                bot.send_message(telegram_id, message.text, parse_mode="Markdown")
                sent_count += 1
                processed_tids.add(telegram_id)
                
                # Show progress every 5 messages
                if sent_count % 5 == 0:
                    bot.reply_to(
                        message,
                        f"Progress: {sent_count}/{len(username_to_tid)} messages sent..."
                    )
                    
            except Exception as e:
                failed_count += 1
                continue
        
        # Send final report
        report = (
            "📢 *Broadcast Complete*\n\n"
            f"✅ Successfully sent: {sent_count}\n"
            f"❌ Failed to send: {failed_count}\n"
            f"👥 Total unique users: {len(username_to_tid)}\n"
            f"🎯 Selected group: {user_type}"
        )
        bot.reply_to(message, report, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Error during broadcast: {str(e)}")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '📝 Edit Help')
def edit_help_message(message):
    current_message = load_help_message()
    msg = bot.reply_to(message, 
                      "Current help message is:\n\n" + current_message + 
                      "\n\nSend the new help message (or /cancel to keep current):")
    bot.register_next_step_handler(msg, process_edit_help_message)

def process_edit_help_message(message):
    if message.text.lower() == '/cancel':
        bot.reply_to(message, "❌ Help message update cancelled.")
        return
    
    save_help_message(message.text)
    bot.reply_to(message, "✅ Help message updated successfully!")

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

@bot.message_handler(func=lambda message: message.text == '❓ Support/Help')
def support_help(message):
    help_text = load_help_message()
    bot.reply_to(message, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '🔍 Toggle Diagnose Mode')
def toggle_diagnose_mode(message):
    global diagnose_mode
    diagnose_mode = not diagnose_mode
    status = "ON" if diagnose_mode else "OFF"
    bot.reply_to(message, f"Diagnose mode is now {status}.")

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '⚙️ Payment Settings')
def payment_settings(message):
    markup = types.InlineKeyboardMarkup()
    setup_btn = types.InlineKeyboardButton("🔑 Setup Cryptomus", callback_data="setup_cryptomus")
    status_btn = types.InlineKeyboardButton("📊 Payment Status", callback_data="payment_status")
    markup.row(setup_btn)
    markup.row(status_btn)
    
    bot.reply_to(message, "Select a payment setting option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "setup_cryptomus")
def setup_cryptomus(call):
    msg = bot.send_message(
        call.message.chat.id,
        "Please enter your Cryptomus Merchant ID:"
    )
    bot.register_next_step_handler(msg, process_merchant_id)

def process_merchant_id(message):
    merchant_id = message.text.strip()
    if not merchant_id:
        bot.reply_to(message, "❌ Invalid Merchant ID. Please try again.")
        return
    
    # Store merchant ID temporarily
    bot.send_message(
        message.chat.id,
        "Now enter your Cryptomus Payment API Key:"
    )
    bot.register_next_step_handler(message, lambda m: process_payment_key(m, merchant_id))

def process_payment_key(message, merchant_id):
    payment_key = message.text.strip()
    if not payment_key:
        bot.reply_to(message, "❌ Invalid Payment API Key. Please try again.")
        return
    
    # Save credentials
    if cryptomus.save_credentials(merchant_id, payment_key):
        bot.reply_to(message, "✅ Cryptomus credentials saved successfully!")
    else:
        bot.reply_to(message, "❌ Failed to save Cryptomus credentials. Please try again.")

@bot.callback_query_handler(func=lambda call: call.data == "payment_status")
def check_payment_status(call):
    if not cryptomus.is_configured():
        bot.answer_callback_query(
            call.id,
            "⚠️ Cryptomus is not configured. Please setup credentials first.",
            show_alert=True
        )
        return
    
    bot.answer_callback_query(call.id)
    bot.reply_to(
        call.message,
        "✅ Cryptomus is configured and ready to accept payments!"
    )

@bot.message_handler(func=lambda message: is_admin(message.from_user.id) and message.text == '📈 Sales Stats')
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

@bot.message_handler(func=lambda message: message.text == '📱 View My Config')
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

@bot.message_handler(func=lambda message: message.text == '💰 View Available Plans')
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('purchase_plan:'))
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

def is_admin(user_id):
    return user_id in ADMIN_USER_IDS

if __name__ == '__main__':
    bot.polling(none_stop=True)

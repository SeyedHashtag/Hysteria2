from telebot import types
from utils.command import *
from utils.common import create_main_markup, create_purchase_markup, create_downloads_markup
from utils.payments import CryptomusPayment
import threading
import time
import asyncio

# Initialize payment processor
payment_processor = CryptomusPayment()

# Store payment sessions
payment_sessions = {}

@bot.message_handler(func=lambda message: message.text == '📱 My Configs')
def show_my_configs(message):
    user_id = str(message.from_user.id)
    command = f"python3 {CLI_PATH} list-users"
    result = run_cli_command(command)
    
    try:
        users = json.loads(result)
        user_configs = []
        
        for username, details in users.items():
            # Assuming you store telegram_id in user details
            if details.get('telegram_id') == user_id:
                user_configs.append({
                    'username': username,
                    'traffic': details['max_download_bytes'] / (1024 ** 3),
                    'days': details['expiration_days']
                })
        
        if not user_configs:
            bot.reply_to(message, "You don't have any active configs. Use the Purchase Plan option to get started!")
            return
            
        for config in user_configs:
            text = (
                f"📱 Config: {config['username']}\n"
                f"📊 Traffic: {config['traffic']:.2f} GB\n"
                f"📅 Days: {config['days']}"
            )
            bot.reply_to(message, text)
            
    except json.JSONDecodeError:
        bot.reply_to(message, "Error retrieving configs. Please try again later.")

@bot.message_handler(func=lambda message: message.text == '💰 Purchase Plan')
def show_purchase_options(message):
    bot.reply_to(
        message,
        "Select a plan to purchase:",
        reply_markup=create_purchase_markup()
    )

def check_payment_status(payment_id, chat_id, plan_gb):
    while True:
        status = payment_processor.check_payment_status(payment_id)
        if status and status['result']['payment_status'] in ('paid', 'paid_over'):
            # Create user config after successful payment
            username = f"user_{chat_id}_{int(time.time())}"
            command = f"python3 {CLI_PATH} add-user -u {username} -t {plan_gb} -e 30 -tid {chat_id}"
            result = run_cli_command(command)
            
            bot.send_message(
                chat_id,
                f"✅ Payment received! Your config has been created.\n\n{result}"
            )
            del payment_sessions[payment_id]
            break
        elif status and status['result']['payment_status'] == 'expired':
            bot.send_message(
                chat_id,
                "❌ Payment session expired. Please try again."
            )
            del payment_sessions[payment_id]
            break
        time.sleep(30)

@bot.callback_query_handler(func=lambda call: call.data.startswith('purchase:'))
def handle_purchase(call):
    plan_gb = int(call.data.split(':')[1])
    
    # Set price based on plan
    prices = {
        30: 1.80,
        60: 3.00,
        100: 4.20
    }
    amount = prices.get(plan_gb)
    
    if not amount:
        bot.answer_callback_query(call.id, "Invalid plan selected")
        return

    # Create payment asynchronously
    async def create_payment_async():
        payment = await create_payment(amount, plan_gb)
        
        if not payment or 'result' not in payment:
            bot.reply_to(
                call.message,
                "❌ Failed to create payment. Please try again later or contact support.",
                reply_markup=create_main_markup(is_admin=False)
            )
            return

        payment_id = payment['result']['uuid']
        payment_url = payment['result']['url']
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Pay Now", url=payment_url))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=(
                f"💰 Payment for {plan_gb}GB Plan\n\n"
                f"Amount: ${amount:.2f}\n"
                f"Payment ID: {payment_id}\n\n"
                "Click the button below to proceed with payment.\n"
                "The config will be created automatically after payment is confirmed."
            ),
            reply_markup=markup
        )

        # Start payment status checking
        asyncio.create_task(
            check_payment_status(payment_id, call.message.chat.id, plan_gb)
        )

    # Run the async function
    asyncio.run(create_payment_async())

@bot.message_handler(func=lambda message: message.text == '⬇️ Downloads')
def show_downloads(message):
    bot.reply_to(
        message,
        "Download our apps:",
        reply_markup=create_downloads_markup()
    )

@bot.message_handler(func=lambda message: message.text == '📞 Support')
def show_support(message):
    support_text = (
        "Need help? Contact our support:\n\n"
        "📱 Telegram: @your_support_username\n"
        "📧 Email: support@yourdomain.com\n"
        "⏰ Working hours: 24/7"
    )
    bot.reply_to(message, support_text) 

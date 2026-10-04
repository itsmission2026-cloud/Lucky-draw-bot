import logging
import os
import random
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# 1. Enable Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)

# 2. Dummy HTTP Server for Render Health Check
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is live!")

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# 3. Conversation States
DRAW_SELECTION, TICKET_QTY, USER_NAME, PHONE_NUM, PAYMENT_PROOF = range(5)

# --- HELPER FUNCTIONS ---

def get_start_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Weekly Draw (99 / 249)", callback_data="draw_weekly")],
        [InlineKeyboardButton("Monthly Mega Draw (499)", callback_data="draw_monthly")],
        [InlineKeyboardButton("🔄 Restart / Start Over", callback_data="restart_flow")]
    ])

# --- USER FLOW ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg_text = "👋 Welcome to the Lucky Draw Bot!\nPlease select a draw to participate:"
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(msg_text, reply_markup=get_start_keyboard())
    else:
        await update.message.reply_text(msg_text, reply_markup=get_start_keyboard())
        
    return DRAW_SELECTION

async def handle_draw_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "restart_flow":
        return await start(update, context)

    if query.data == "draw_weekly":
        keyboard = [
            [InlineKeyboardButton("99 Ticket (Win 9,999)", callback_data="price_99")],
            [InlineKeyboardButton("249 Ticket (Win 24,999)", callback_data="price_249")],
            [InlineKeyboardButton("🔄 Restart / Start Over", callback_data="restart_flow")]
        ]
        await query.edit_message_text("Weekly Draw selected. Choose your ticket tier:", reply_markup=InlineKeyboardMarkup(keyboard))
        return DRAW_SELECTION
    else:
        context.user_data['ticket_price'] = 499
        await query.edit_message_text(
            "Monthly Mega Draw selected (499 per ticket).\n"
            "How many tickets would you like to buy?\n\n"
            "💡 Tip: Send /restart at any time to start over."
        )
        return TICKET_QTY

async def handle_tier_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "restart_flow":
        return await start(update, context)

    price = 99 if query.data == "price_99" else 249
    context.user_data['ticket_price'] = price
    await query.edit_message_text(
        f"Selected {price} Tier.\n🎁 Offer: Buy 2 Get 1 Free!\n"
        f"How many tickets would you like to buy?\n\n"
        f"💡 Tip: Send /restart at any time to start over."
    )
    return TICKET_QTY

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Please enter a valid number, or send /restart to start over.")
        return TICKET_QTY
    qty = int(text)
    price = context.user_data['ticket_price']
    total_tickets = qty + (qty // 2) if price in [99, 249] else qty
    context.user_data['quantity'] = qty
    context.user_data['total_tickets'] = total_tickets
    await update.message.reply_text(
        f"Got it ({total_tickets} tickets total)!\n"
        f"Please enter your Full Name (or send /restart to reset):"
    )
    return USER_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Please enter your 10-digit Phone / WhatsApp number (or send /restart to reset):")
    return PHONE_NUM

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    price = context.user_data['ticket_price']
    total_amount = price * context.user_data['quantity']
    upi_id = "naseemudheenn@oksbi"
    
    summary = (
        f"📋 Order Summary:\n"
        f"Name: {context.user_data['full_name']}\n"
        f"Phone: {context.user_data['phone']}\n"
        f"Tickets: {context.user_data['total_tickets']}\n"
        f"Total Amount: ₹{total_amount}\n\n"
        f"💳 Pay via UPI to: {upi_id}\n\n"
        f"After payment, reply with your Transaction ID or Screenshot.\n"
        f"Or send /restart to start over."
    )
    await update.message.reply_text(summary)
    return PAYMENT_PROOF

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        user_id = user.id
        full_name = context.user_data.get('full_name', 'N/A')
        phone = context.user_data.get('phone', 'N/A')
        total_tickets = context.user_data.get('total_tickets', 1)
        price = context.user_data.get('ticket_price', 0)
        qty = context.user_data.get('quantity', 1)
        total_amount = price * qty

        admin_msg = (
            f"🚨 NEW PAYMENT PROOF RECEIVED\n\n"
            f"👤 User: {full_name} (@{user.username or 'NoUsername'})\n"
            f"📞 Phone: {phone}\n"
            f"🎟️ Tickets Requested: {total_tickets} ({qty} paid)\n"
            f"💰 Amount Paid: ₹{total_amount}\n"
            f"🆔 User ID: {user_id}"
        )

        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{total_tickets}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}_0")
            ]
        ])

        admin_group_id = os.getenv("ADMIN_GROUP_ID")
        
        if admin_group_id:
            chat_id = int(admin_group_id)
            if update.message.photo:
                photo_file_id = update.message.photo[-1].file_id
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file_id,
                    caption=admin_msg,
                    reply_markup=admin_keyboard
                )
            elif update.message.document:
                doc_file_id = update.message.document.file_id
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_file_id,
                    caption=admin_msg,
                    reply_markup=admin_keyboard
                )
            else:
                text_proof = update.message.text
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{admin_msg}\n\n📝 Proof/UTR: {text_proof}",
                    reply_markup=admin_keyboard
                )

        await update.message.reply_text(
            "✅ Payment proof received!\n"
            "Our admin team is verifying your payment. You will receive your confirmation shortly.\n\n"
            "📢 Join our official channel:\nhttps://t.me/indiaLuckyDraw\n\n"
            "Want to buy more tickets? Send /start or /restart."
        )

    except Exception as e:
        logging.error(f"Error handling payment proof: {e}")
        await update.message.reply_text("There was an issue processing your submission. Send /restart to start over.")

    return ConversationHandler.END

# --- ADMIN ACTION HANDLER ---

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action = data[0]
    target_user_id = int(data[1])
    ticket_qty = int(data[2]) if len(data) > 2 else 1

    channel_link = "https://t.me/indiaLuckyDraw"

    if action == "approve":
        ticket_numbers = [str(random.randint(12001, 19999)) for _ in range(ticket_qty)]
        formatted_tickets = ", ".join(ticket_numbers)

        await context.bot.send_message(
            chat_id=target_user_id,
            text=f"🎉 PAYMENT CONFIRMED! 🎉\n\n"
                 f"Congratulations! You are enrolled into the draw.\n"
                 f"🎟 Ticket Number(s): {formatted_tickets}\n\n"
                 f"Good luck! 🍀\n\n"
                 f"📢 Stay tuned for winner announcements here:\n{channel_link}"
        )

        status_text = f"\n\n✅ APPROVED | Ticket Number(s): {formatted_tickets}"
        if query.message.photo or query.message.document:
            await query.edit_message_caption(caption=query.message.caption + status_text)
        else:
            await query.edit_message_text(text=query.message.text + status_text)

    elif action == "reject":
        await context.bot.send_message(
            chat_id=target_user_id,
            text="❌ Payment Verification Failed\n\n"
                 "We could not verify your payment proof. Please verify your transaction details and submit again using /start."
        )

        status_text = "\n\n❌ STATUS: REJECTED"
        if query.message.photo or query.message.document:
            await query.edit_message_caption(caption=query.message.caption + status_text)
        else:
            await query.edit_message_text(text=query.message.text + status_text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Send /start or /restart to begin again.")
    return ConversationHandler.END

# --- MAIN RUNNER ---

if __name__ == "__main__":
    token = os.getenv("BOT_TOKEN")
    if not token:
        logging.error("CRITICAL ERROR: BOT_TOKEN is missing!")
        sys.exit(1)
        
    app = ApplicationBuilder().token(token).build()
    
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CommandHandler('restart', start)
        ],
        states={
            DRAW_SELECTION: [
                CallbackQueryHandler(handle_draw_selection, pattern="^draw_"),
                CallbackQueryHandler(handle_tier_selection, pattern="^price_"),
                CallbackQueryHandler(start, pattern="^restart_flow$")
            ],
            TICKET_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_quantity)],
            USER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            PHONE_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            PAYMENT_PROOF: [MessageHandler(filters.ALL & ~filters.COMMAND, handle_payment_proof)]
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('restart', start),
            CallbackQueryHandler(start, pattern="^restart_flow$")
        ]
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve|reject)_"))
    
    app.run_polling()
    

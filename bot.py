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
            "💡 Send /restart at any time to start over."
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
        f"Selected ₹{price} Tier.\n🎁 Offer: Buy 2 Get 1 Free!\n"
        f"How many tickets would you like to buy?\n\n"
        f"💡 Send /restart at any time to start over."
    )
    return TICKET_QTY

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Please enter a valid number, or send /restart to start over.")
        return TICKET_QTY
    qty = int(text)
    price = context.user_data.get('ticket_price', 99)
    total_tickets = qty + (qty // 2) if price in [99, 249] else qty
    context.user_data['quantity'] = qty
    context.user_data['total_tickets'] = total_tickets
    await update.message.reply_text("Got it! Please enter your **Full Name**:")
    return USER_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Please enter your 10-digit **Phone / WhatsApp number**:")
    return PHONE_NUM

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text
    price = context.user_data.get('ticket_price', 99)
    total_amount = price * context.user_data.get('quantity', 1)
    upi_id = "naseemudheenn@oksbi"
    
    summary = (
        f"📋 **Order Summary**\n"
        f"───────────────\n"
        f"👤 Name: {context.user_data['full_name']}\n"
        f"📞 Phone: {context.user_data['phone']}\n"
        f"🎟️ Total Tickets: {context.user_data['total_tickets']}\n"
        f"💰 Payable Amount: ₹{total_amount}\n"
        f"───────────────\n\n"
        f"💳 **Pay via UPI**: `{upi_id}`\n\n"
        f"📸 Please send the payment screenshot or UTR/Transaction ID now:"
    )
    await update.message.reply_text(summary, parse_mode="Markdown")
    return PAYMENT_PROOF

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    full_name = context.user_data.get('full_name', 'N/A')
    phone = context.user_data.get('phone', 'N/A')
    total_tickets = context.user_data.get('total_tickets', 1)
    price = context.user_data.get('ticket_price', 0)
    qty = context.user_data.get('quantity', 1)
    total_amount = price * qty

    # 1. Caption for Admin Group
    admin_caption = (
        f"🚨 **NEW PAYMENT PROOF RECEIVED**\n\n"
        f"👤 **Name:** {full_name}\n"
        f"📞 **Phone:** `{phone}`\n"
        f"🎟️ **Tickets:** {total_tickets} ({qty} paid)\n"
        f"💰 **Amount Paid:** ₹{total_amount}\n"
        f"🆔 **Telegram ID:** `{user_id}`\n"
        f"Username: @{user.username or 'None'}"
    )

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{total_tickets}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}_{total_tickets}")
        ]
    ])

    admin_group_id = os.getenv("ADMIN_GROUP_ID")
    
    # 2. Try sending proof to Admin Group
    if admin_group_id:
        try:
            chat_id = int(admin_group_id.strip())
            if update.message.photo:
                photo_id = update.message.photo[-1].file_id
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_id,
                    caption=admin_caption,
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
            elif update.message.document:
                doc_id = update.message.document.file_id
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=doc_id,
                    caption=admin_caption,
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
            else:
                text_proof = update.message.text
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"{admin_caption}\n\n📝 **Proof/UTR:** {text_proof}",
                    reply_markup=admin_keyboard,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logging.error(f"Failed to send to admin group: {e}")

    # 3. Always Reply to User
    await update.message.reply_text(
        "✅ **Payment proof received!**\n\n"
        "Our admin team is verifying your payment. Your ticket details will be delivered here once approved.\n\n"
        "📢 Join our official updates channel:\nhttps://t.me/indiaLuckyDraw\n\n"
        "To buy more tickets, send /start.",
        parse_mode="Markdown"
    )

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
        # Generate random unique 5-digit coupon numbers
        ticket_numbers = [f"#{random.randint(12000, 99999)}" for _ in range(ticket_qty)]
        formatted_tickets = "\n".join([f"🎫 **{num}**" for num in ticket_numbers])

        # Centered message format to user
        user_message = (
            f"🎉 **PAYMENT APPROVED!** 🎉\n\n"
            f"Congratulations! You are officially enrolled in the draw.\n\n"
            f"👇 **YOUR TICKET NUMBER(S)** 👇\n\n"
            f"{formatted_tickets}\n\n"
            f"───────────────\n"
            f"📢 **Join Official Telegram Channel:**\n"
            f"👉 {channel_link} 👈\n"
            f"───────────────\n\n"
            f"🍀 Good luck!"
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=user_message,
                parse_mode="Markdown"
            )
            status_text = f"\n\n✅ **APPROVED**\nTickets Issued:\n{', '.join(ticket_numbers)}"
        except Exception as e:
            status_text = f"\n\n⚠️ **Approved but failed to notify user:** {e}"

    elif action == "reject":
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ **Payment Verification Failed**\n\n"
                     "We could not verify your payment screenshot. Please verify your transaction and try again using /start.",
                parse_mode="Markdown"
            )
            status_text = "\n\n❌ **REJECTED**"
        except Exception as e:
            status_text = f"\n\n⚠️ **Rejected but failed to notify user:** {e}"

    # Update Admin Group Message
    try:
        if query.message.photo or query.message.document:
            await query.edit_message_caption(caption=query.message.caption + status_text, parse_mode="Markdown")
        else:
            await query.edit_message_text(text=query.message.text + status_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error editing admin message: {e}")

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
            

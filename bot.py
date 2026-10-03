import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
import os

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

DRAW_SELECTION, TICKET_QTY, USER_NAME, PHONE_NUM, PAYMENT_PROOF = range(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Weekly Draw (₹99 / ₹249)", callback_data="draw_weekly")],
        [InlineKeyboardButton("Monthly Mega Draw (₹499)", callback_data="draw_monthly")]
    ]
    await update.message.reply_text(
        "👋 Welcome to the Lucky Draw Bot!\nPlease select a draw to participate:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return DRAW_SELECTION

async def handle_draw_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "draw_weekly":
        keyboard = [
            [InlineKeyboardButton("₹99 Ticket (Win ₹9,999)", callback_data="price_99")],
            [InlineKeyboardButton("₹249 Ticket (Win ₹24,999)", callback_data="price_249")]
        ]
        await query.edit_message_text("Weekly Draw selected. Choose your ticket tier:", reply_markup=InlineKeyboardMarkup(keyboard))
        return DRAW_SELECTION
    else:
        context.user_data['ticket_price'] = 499
        await query.edit_message_text("Monthly Mega Draw selected (₹499 per ticket).\nHow many tickets would you like to buy?")
        return TICKET_QTY

async def handle_tier_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    price = 99 if query.data == "price_99" else 249
    context.user_data['ticket_price'] = price
    await query.edit_message_text(f"Selected ₹{price} Tier.\n🎁 Offer: Buy 2 Get 1 Free!\nHow many tickets would you like to buy?")
    return TICKET_QTY

async def handle_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("Please enter a valid number.")
        return TICKET_QTY
    qty = int(text)
    price = context.user_data['ticket_price']
    total_tickets = qty + (qty // 2) if price in [99, 249] else qty
    context.user_data['quantity'] = qty
    context.user_data['total_tickets'] = total_tickets
    await update.message.reply_text(f"Got it ({total_tickets} tickets total)! Please enter your Full Name:")
    return USER_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Please enter your 10-digit Phone / WhatsApp number:")
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
        f"After payment, reply with your Transaction ID / Screenshot."
    )
    await update.message.reply_text(summary)
    return PAYMENT_PROOF

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Payment details received!\nOur team will verify and confirm shortly.\n\n"
        "📢 Join our channel for updates:\nhttps://t.me/your_channel_username"
    )
    return ConversationHandler.END

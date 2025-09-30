import os
import random
import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from flask import Flask
from threading import Thread

# ==================== CONFIG ====================
BOT_TOKEN = "7920917990:AAEFcd40t0h698IXhnR0v8E_WAOTrRPHIPc"
ADMIN_ID = 6073096069
GROUP_CHAT_ID = -1002461779684

print("🎲 BOT TÀI XỈU VIP ĐANG KHỞI ĐỘNG...")

# ==================== KEEP ALIVE ====================
app = Flask(__name__)
@app.route('/')
def home():
    return "🤖 BOT TÀI XỈU VIP ĐANG CHẠY 24/7"
def run_flask():
    app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🌐 Keep-alive server đã khởi động")

# ==================== DATABASE VIP ====================
def init_db():
    conn = sqlite3.connect('taixiu_vip.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT, 
                  full_name TEXT,
                  balance INTEGER DEFAULT 5000000,
                  total_win INTEGER DEFAULT 0,
                  total_bet INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS games
                 (game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  dice1 INTEGER, dice2 INTEGER, dice3 INTEGER,
                  total INTEGER, result TEXT,
                  total_bet_tai INTEGER DEFAULT 0,
                  total_bet_xiu INTEGER DEFAULT 0,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS bets
                 (bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  game_id INTEGER, user_id INTEGER,
                  bet_type TEXT, amount INTEGER, win_amount INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS vip_codes
                 (code TEXT PRIMARY KEY, amount INTEGER,
                  used_by INTEGER, used_at TIMESTAMP,
                  created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Bảng mới: Yêu cầu nạp/rút
    c.execute('''CREATE TABLE IF NOT EXISTS deposit_requests
                 (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, amount INTEGER, type TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()
    print("💾 Database VIP đã khởi tạo")

def get_db():
    return sqlite3.connect('taixiu_vip.db', check_same_thread=False)

def get_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def create_user(user_id, username, full_name):
    conn = get_db()
    conn.execute('INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)',
                 (user_id, username, full_name))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = get_db()
    conn.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

# ==================== GAME ENGINE VIP ====================
class VIPGameState:
    def __init__(self):
        self.current_game_id = None
        self.game_start_time = None
        self.game_duration = 60
        self.is_game_active = False
        self.bets = {}
        self.total_bet_tai = 0
        self.total_bet_xiu = 0
        self.players = set()

game_state = VIPGameState()

def format_money(amount):
    return f"{amount:,}"

def calculate_vip_result(dice1, dice2, dice3):
    total = dice1 + dice2 + dice3
    return 'tai' if total >= 11 else 'xiu'

# ==================== USER COMMANDS ====================
def vip_start(update: Update, context: CallbackContext):
    user = update.effective_user
    create_user(user.id, user.username, user.full_name)
    
    user_info = get_user(user.id)
    
    update.message.reply_text(
        f"""🎉 **CHÀO MỪNG ĐẾN TÀI XỈU VIP!**

👤 **Thông tin player:**
🆔 {user.mention_markdown()}
💰 Số dư: **{format_money(user_info['balance'])}** xu

🎯 **LỆNH CHƠI:**
/tai [số tiền] - Cược TÀI (11-17)
/xiu [số tiền] - Cược XỈU (4-10)

📊 **LỆNH KHÁC:**
/xemdiem - Xem số dư
/lichsu - Lịch sử cược
/top - Bảng xếp hạng

💳 **NẠP/RÚT:**
/nap [số tiền] - Yêu cầu nạp tiền
/rut [số tiền] - Yêu cầu rút tiền

🔧 **ADMIN:**
/naptien @user amount
/ruttien @user amount  
/taocode amount
/tongsodu
/checkuser @username - Xem thông tin user
/chinhketqua [tai/xiu] - Chỉnh kết quả (admin)

⚡ **Bot chạy 24/7 trên Render Cloud**
        """,
        parse_mode='Markdown'
    )

def vip_xemdiem(update: Update, context: CallbackContext):
    user = get_user(update.effective_user.id)
    if user:
        update.message.reply_text(
            f"""💎 **THÔNG TIN TÀI KHOẢN**

👤 {user['full_name']}
💰 Số dư: **{format_money(user['balance'])}** xu
🏆 Tổng thắng: **{format_money(user['total_win'])}** xu
🎯 Tổng cược: **{format_money(user['total_bet'])}** xu
            """,
            parse_mode='Markdown'
        )

# ==================== NẠP/RÚT USER ====================
def user_nap(update: Update, context: CallbackContext):
    """User yêu cầu nạp tiền"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        update.message.reply_text("❌ Vui lòng /start để đăng ký!")
        return
    
    if not context.args:
        update.message.reply_text("📝 Sử dụng: /nap [số tiền]\n💡 Ví dụ: /nap 50000")
        return
    
    try:
        amount = int(context.args[0])
        if amount < 1000:
            update.message.reply_text("❌ Số tiền tối thiểu: 1,000 xu")
            return
    except:
        update.message.reply_text("❌ Số tiền không hợp lệ!")
        return
    
    # Lưu yêu cầu nạp
    conn = get_db()
    conn.execute('INSERT INTO deposit_requests (user_id, amount, type) VALUES (?, ?, ?)',
                 (user_id, amount, 'deposit'))
    conn.commit()
    conn.close()
    
    # Thông báo cho user
    user_display = f"@{user['username']}" if user['username'] else user['full_name']
    update.message.reply_text(
        f"""📨 **ĐÃ GỬI YÊU CẦU NẠP TIỀN**

👤 {user_display}
💳 Số tiền: **{format_money(amount)}** xu
⏳ Vui lòng chờ admin duyệt!

🔔 Admin sẽ xử lý trong thời gian sớm nhất.
        """,
        parse_mode='Markdown'
    )
    
    # Thông báo cho admin
    try:
        context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 **YÊU CẦU NẠP TIỀN MỚI**\n\n👤 User: {user_display}\n💰 Số tiền: {format_money(amount)} xu\n🆔 User ID: {user_id}\n\n💳 Duyệt ngay: /naptien @{user['username']} {amount}",
            parse_mode='Markdown'
        )
    except:
        pass

def user_rut(update: Update, context: CallbackContext):
    """User yêu cầu rút tiền"""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    if not user:
        update.message.reply_text("❌ Vui lòng /start để đăng ký!")
        return
    
    if not context.args:
        update.message.reply_text("📝 Sử dụng: /rut [số tiền]\n💡 Ví dụ: /rut 50000")
        return
    
    try:
        amount = int(context.args[0])
        if amount < 1000:
            update.message.reply_text("❌ Số tiền tối thiểu: 1,000 xu")
            return
        if amount > user['balance']:
            update.message.reply_text(f"❌ Số dư không đủ! Bạn có {format_money(user['balance'])} xu")
            return
    except:
        update.message.reply_text("❌ Số tiền không hợp lệ!")
        return
    
    # Lưu yêu cầu rút
    conn = get_db()
    conn.execute('INSERT INTO deposit_requests (user_id, amount, type) VALUES (?, ?, ?)',
                 (user_id, amount, 'withdraw'))
    conn.commit()
    conn.close()
    
    # Thông báo cho user
    user_display = f"@{user['username']}" if user['username'] else user['full_name']
    update.message.reply_text(
        f"""📨 **ĐÃ GỬI YÊU CẦU RÚT TIỀN**

👤 {user_display}
💳 Số tiền: **{format_money(amount)}** xu
⏳ Vui lòng chờ admin duyệt!

🔔 Admin sẽ xử lý trong thời gian sớm nhất.
        """,
        parse_mode='Markdown'
    )
    
    # Thông báo cho admin
    try:
        context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🆕 **YÊU CẦU RÚT TIỀN MỚI**\n\n👤 User: {user_display}\n💰 Số tiền: {format_money(amount)} xu\n🆔 User ID: {user_id}\n\n💳 Duyệt ngay: /ruttien @{user['username']} {amount}",
            parse_mode='Markdown'
        )
    except:
        pass

# ==================== ADMIN COMMANDS NÂNG CAO ====================
def admin_checkuser(update: Update, context: CallbackContext):
    """Admin xem thông tin user chi tiết"""
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Chỉ Admin mới có quyền!")
        return
    
    if not context.args:
        update.message.reply_text("📝 Sử dụng: /checkuser @username")
        return
    
    username = context.args[0].lstrip('@')
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    if not user:
        update.message.reply_text("❌ User không tồn tại!")
        conn.close()
        return
    
    # Lấy thống kê cược
    bets_stats = conn.execute('''
        SELECT COUNT(*) as total_bets, 
               SUM(amount) as total_bet_amount,
               SUM(CASE WHEN win_amount > 0 THEN 1 ELSE 0 END) as win_bets
        FROM bets WHERE user_id = ?
    ''', (user['user_id'],)).fetchone()
    
    conn.close()
    
    update.message.reply_text(
        f"""🔍 **THÔNG TIN USER CHI TIẾT**

👤 **Username:** @{user['username']}
🆔 **User ID:** {user['user_id']}
📛 **Tên:** {user['full_name']}
💰 **Số dư:** {format_money(user['balance'])} xu
🏆 **Tổng thắng:** {format_money(user['total_win'])} xu
🎯 **Tổng cược:** {format_money(user['total_bet'])} xu

📊 **THỐNG KÊ CƯỢC:**
• Tổng số cược: {bets_stats['total_bets']}
• Tổng tiền cược: {format_money(bets_stats['total_bet_amount'] or 0)} xu
• Số lần thắng: {bets_stats['win_bets']}

⏰ **Tham gia:** {user['created_at'][:16]}
        """,
        parse_mode='Markdown'
    )

def admin_chinhketqua(update: Update, context: CallbackContext):
    """Admin chỉnh kết quả tài xỉu"""
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("❌ Chỉ Admin mới có quyền!")
        return
    
    if not context.args:
        update.message.reply_text("📝 Sử dụng: /chinhketqua [tai/xiu]\n💡 Ví dụ: /chinhketqua tai")
        return
    
    result = context.args[0].lower()
    if result not in ['tai', 'xiu']:
        update.message.reply_text("❌ Kết quả phải là 'tai' hoặc 'xiu'!")
        return
    
    if not game_state.is_game_active:
        update.message.reply_text("❌ Không có phiên game đang hoạt động!")
        return
    
    # Force kết quả
    game_state.is_game_active = False
    
    # Xử lý kết quả forced
    conn = get_db()
    conn.execute('UPDATE games SET dice1=?, dice2=?, dice3=?, total=?, result=? WHERE game_id=?',
                 (0, 0, 0, 0, result, game_state.current_game_id))
    
    # Xử lý thắng thua
    winners = []
    for user_id, bet_info in game_state.bets.items():
        user = get_user(user_id)
        if user and bet_info['type'] == result:
            win_amount = bet_info['amount']
            update_balance(user_id, win_amount)
            conn.execute('UPDATE users SET total_win = total_win + ?, total_bet = total_bet + ? WHERE user_id = ?',
                        (win_amount, bet_info['amount'], user_id))
            winners.append((user['username'] or user['full_name'], win_amount))
            conn.execute('UPDATE bets SET win_amount=? WHERE game_id=? AND user_id=?',
                        (win_amount, game_state.current_game_id, user_id))
    
    conn.commit()
    conn.close()
    
    # Thông báo kết quả forced
    result_emoji = "🔴" if result == 'tai' else "🔵"
    
    winner_text = ""
    if winners:
        winner_text = "\n\n🏆 **NGƯỜI THẮNG:**\n"
        for username, amount in winners[:5]:
            winner_text += f"💎 {username}: **+{format_money(amount)}**\n"
    
    forced_result = f"""
🎲 **KẾT QUẢ TÀI XỈU** - Phiên #{game_state.current_game_id}

⚡ **KẾT QUẢ ĐƯỢC CHỈNH BỞI ADMIN**
🎯 Kết quả: {result_emoji} **{result.upper()}**

💰 **TỔNG CƯỢC:**
🔴 TÀI: {format_money(game_state.total_bet_tai)}
🔵 XỈU: {format_money(game_state.total_bet_xiu)}
{winner_text}

⏳ **Phiên mới bắt đầu sau 5s...**
    """
    
    try:
        context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=forced_result,
            parse_mode='Markdown'
        )
    except:
        pass
    
    # Game mới sau 5s
    context.job_queue.run_once(
        start_vip_game, 5,
        context={'chat_id': GROUP_CHAT_ID},
        name="vip_new_game"
    )
    
    update.message.reply_text(f"✅ Đã chỉnh kết quả thành: **{result.upper()}**", parse_mode='Markdown')

# ==================== GAME FUNCTIONS ====================
def start_vip_game(context: CallbackContext):
    conn = get_db()
    cursor = conn.execute('INSERT INTO games (result) VALUES (?)', ('pending',))
    game_id = cursor.lastrowid
    
    game_state.current_game_id = game_id
    game_state.game_start_time = datetime.now()
    game_state.is_game_active = True
    game_state.bets = {}
    game_state.total_bet_tai = 0
    game_state.total_bet_xiu = 0
    game_state.players = set()
    
    vip_start_message = f"""
🎲 **TÀI XỈU VIP ROOM** - Phiên #{game_id}
⏰ Thời gian còn lại: **60s**

💰 **TỔNG CƯỢC HIỆN TẠI:**
🔴 TÀI: **0**
🔵 XỈU: **0**

🎯 **LỆNH NHANH:**
/tai [số tiền] - Cược TÀI (11-17)
/xiu [số tiền] - Cược XỈU (4-10)
    """
    
    msg = context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=vip_start_message,
        parse_mode='Markdown'
    )
    
    game_state.game_message_id = msg.message_id
    
    # Kết thúc game
    context.job_queue.run_once(
        end_vip_game, game_state.game_duration,
        context={'chat_id': GROUP_CHAT_ID},
        name=f"vip_end_{game_id}"
    )
    
    conn.commit()
    conn.close()
    print(f"🎮 Bắt đầu phiên game VIP #{game_id}")

def end_vip_game(context: CallbackContext):
    game_state.is_game_active = False
    
    # Tung xúc xắc VIP
    dice1, dice2, dice3 = random.randint(1,6), random.randint(1,6), random.randint(1,6)
    total = dice1 + dice2 + dice3
    result = calculate_vip_result(dice1, dice2, dice3)
    
    conn = get_db()
    conn.execute('UPDATE games SET dice1=?, dice2=?, dice3=?, total=?, result=?, total_bet_tai=?, total_bet_xiu=? WHERE game_id=?',
                 (dice1, dice2, dice3, total, result, game_state.total_bet_tai, game_state.total_bet_xiu, game_state.current_game_id))
    
    # Xử lý thắng thua
    winners = []
    for user_id, bet_info in game_state.bets.items():
        user = get_user(user_id)
        if user and bet_info['type'] == result:
            win_amount = bet_info['amount']
            update_balance(user_id, win_amount)
            conn.execute('UPDATE users SET total_win = total_win + ?, total_bet = total_bet + ? WHERE user_id = ?',
                        (win_amount, bet_info['amount'], user_id))
            winners.append((user['username'] or user['full_name'], win_amount))
            conn.execute('UPDATE bets SET win_amount=? WHERE game_id=? AND user_id=?',
                        (win_amount, game_state.current_game_id, user_id))
    
    conn.commit()
    conn.close()
    
    # Thông báo kết quả VIP
    result_emoji = "🔴" if result == 'tai' else "🔵"
    dice_display = f"🎲 {dice1} + 🎲 {dice2} + 🎲 {dice3} = **{total}**"
    
    winner_text = ""
    if winners:
        winner_text = "\n\n🏆 **TOP WINNER:**\n"
        for username, amount in winners[:5]:
            winner_text += f"💎 {username}: **+{format_money(amount)}**\n"
    
    vip_result = f"""
🎲 **KẾT QUẢ TÀI XỈU VIP** - Phiên #{game_state.current_game_id}

{dice_display}
🎯 Kết quả: {result_emoji} **{result.upper()}**

💰 **TỔNG CƯỢC:**
🔴 TÀI: {format_money(game_state.total_bet_tai)}
🔵 XỈU: {format_money(game_state.total_bet_xiu)}
{winner_text}

⏳ **Phiên mới bắt đầu sau 5s...**
    """
    
    try:
        context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=vip_result,
            parse_mode='Markdown'
        )
    except:
        pass
    
    # Game mới sau 5s
    context.job_queue.run_once(
        start_vip_game, 5,
        context={'chat_id': GROUP_CHAT_ID},
        name="vip_new_game"
    )

# ==================== MAIN ====================
def main():
    # Khởi động keep-alive
    keep_alive()
    
    # Khởi tạo database
    init_db()
    
    try:
        # Tạo bot
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # Thêm commands USER
        dp.add_handler(CommandHandler("start", vip_start))
        dp.add_handler(CommandHandler("xemdiem", vip_xemdiem))
        dp.add_handler(CommandHandler("tai", vip_tai))
        dp.add_handler(CommandHandler("xiu", vip_xiu))
        dp.add_handler(CommandHandler("lichsu", vip_lichsu))
        dp.add_handler(CommandHandler("top", vip_top))
        dp.add_handler(CommandHandler("nap", user_nap))
        dp.add_handler(CommandHandler("rut", user_rut))
        
        # Thêm commands ADMIN
        dp.add_handler(CommandHandler("naptien", admin_naptien))
        dp.add_handler(CommandHandler("ruttien", admin_ruttien))
        dp.add_handler(CommandHandler("taocode", admin_taocode))
        dp.add_handler(CommandHandler("tongsodu", admin_tongsodu))
        dp.add_handler(CommandHandler("checkuser", admin_checkuser))
        dp.add_handler(CommandHandler("chinhketqua", admin_chinhketqua))
        
        # Bắt đầu game loop
        job_queue = updater.job_queue
        if job_queue:
            job_queue.run_once(start_vip_game, 3, context={'chat_id': GROUP_CHAT_ID}, name="vip_initial")
        
        print("✅ Bot VIP đã khởi động thành công!")
        print("🔄 Đang lắng nghe tin nhắn...")
        
        # Chạy bot
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        print(f"❌ Lỗi khởi động: {e}")

if __name__ == '__main__':
    main()
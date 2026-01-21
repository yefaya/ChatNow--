from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import requests
import json
from datetime import datetime

# ================= 配置区 =================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'yf_chat_secret_2025'
ADMIN_PASSWORD = "yf123456"

# 🔴 强制使用 threading 模式，并允许跨域
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ================= AI 配置 =================
API_KEY = "sk-zxcjuyuwqwyvcejeffkcqakevlseejxiowwbqwaojufemjiy"
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
AI_MODEL = "deepseek-ai/DeepSeek-V3"

DB_FILE = 'chat.db'
online_users = {}

# ================= 数据库逻辑 =================
def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  sender TEXT, target TEXT, msg TEXT, time TEXT, 
                  avatar_color TEXT, room_type TEXT)''')
    conn.commit()
    conn.close()

def save_msg(sender, target, msg, time_str, color, room_type):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT INTO history (sender, target, msg, time, avatar_color, room_type) VALUES (?, ?, ?, ?, ?, ?)", 
                  (sender, target, msg, time_str, color, room_type))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Save Error: {e}")

def get_chat_history(username, target, room_type):
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        if room_type == 'group':
            c.execute("SELECT * FROM history WHERE room_type='group' ORDER BY id ASC")
        elif room_type == 'ai':
            c.execute("SELECT * FROM history WHERE room_type='ai' AND (sender=? OR target=?) ORDER BY id ASC", 
                      (username, username))
        elif room_type == 'private':
            c.execute("SELECT * FROM history WHERE room_type='private' AND ((sender=? AND target=?) OR (sender=? AND target=?)) ORDER BY id ASC", 
                      (username, target, target, username))
            
        rows = c.fetchall()
        conn.close()
        return [dict(ix) for ix in rows]
    except:
        return []

# ================= AI 逻辑 =================

def build_ai_context(username, room_type, current_prompt):
    # 群聊更简短，私聊更详细
    if room_type == 'group':
        sys_msg = "你是在群聊中的DeepSeek助手。回复必须简短精炼(50字内)、幽默犀利。支持Markdown。代码要用代码块。"
    else:
        sys_msg = "你是全能助手DeepSeek。支持Markdown格式。回复逻辑清晰。代码请使用代码块。"

    messages = [{"role": "system", "content": sys_msg}]
    
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        c = conn.cursor()
        limit = 6 
        if room_type == 'group':
            c.execute("SELECT sender, msg FROM history WHERE room_type='group' ORDER BY id DESC LIMIT ?", (limit,))
        else:
            c.execute("SELECT sender, msg FROM history WHERE room_type='ai' AND (sender=? OR target=?) ORDER BY id DESC LIMIT ?", (username, username, limit))
        
        history = c.fetchall()[::-1]
        conn.close()
        
        for sender, msg in history:
            role = "assistant" if sender == "AI Assistant" else "user"
            if msg != current_prompt: 
                content = f"[{sender}]: {msg}" if room_type == 'group' else msg
                messages.append({"role": role, "content": content})
    except: pass

    messages.append({"role": "user", "content": current_prompt})
    return messages

def call_ai_api(messages):
    try:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "max_tokens": 400,
            "temperature": 1.0 
        }
        res = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()['choices'][0]['message']['content']
        return f"⚠ API Error: {res.status_code}"
    except Exception as e:
        return "⚠ DeepSeek 掉线了，请稍后再试。"

def broadcast_user_list():
    users_list = list(set(online_users.values()))
    emit('update_user_list', {'users': users_list, 'count': len(users_list)}, broadcast=True)

# ================= Socket 事件 =================
@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in online_users:
        online_users.pop(request.sid)
        broadcast_user_list()

@socketio.on('login')
def handle_login(data):
    username = data['username']
    pwd = data.get('password', '')
    if username.lower() == 'admin' and pwd != ADMIN_PASSWORD:
        emit('login_error', {'msg': '❌ 管理员密码错误'})
        return
    online_users[request.sid] = username
    join_room(request.sid)
    emit('login_success', {'username': username})
    broadcast_user_list()

@socketio.on('switch_chat')
def handle_switch(data):
    msgs = get_chat_history(data['username'], data['target'], data['room_type'])
    emit('load_history', msgs)

@socketio.on('send_message')
def handle_msg(data):
    sender = data['sender']
    target = data['target']
    msg = data['msg']
    color = data['color']
    rtype = data['room_type']
    time_str = datetime.now().strftime("%H:%M:%S")

    save_msg(sender, target, msg, time_str, color, rtype)

    packet = {'sender': sender, 'target': target, 'msg': msg, 'time': time_str, 'avatar_color': color, 'room_type': rtype}

    if rtype == 'group':
        emit('new_message', packet, broadcast=True)
        
        # ✨ 群聊 AI 触发逻辑 ✨
        # lower() 确保了 @AI, @ai, @Ai 都可以触发
        clean_msg = msg.strip()
        if clean_msg.lower().startswith('@ai') or clean_msg.startswith('＠ai'):
            prompt = clean_msg[3:].strip()
            if prompt:
                # 🔴 关键修改1：只给触发者发送“思考中”的动画，不打扰其他人
                emit('ai_thinking', {'room_type': 'group', 'target': 'Group'}, room=request.sid)
                
                # 🔴 关键修改2：启动后台任务
                socketio.start_background_task(target=process_group_ai, prompt=prompt, trigger_user=sender)

    elif rtype == 'private':
        emit('new_message', packet, room=request.sid)
        target_sids = [sid for sid, name in online_users.items() if name == target]
        for tid in target_sids: emit('new_message', packet, room=tid)
        
    elif rtype == 'ai':
        emit('new_message', packet, room=request.sid)
        emit('ai_thinking', {'room_type': 'ai', 'target': sender}, room=request.sid)
        socketio.start_background_task(target=process_private_ai, sid=request.sid, prompt=msg, user=sender)

# --- 线程处理函数 ---

def process_private_ai(sid, prompt, user):
    # 🔴 关键修改3：使用 app_context 确保上下文，防止消息卡死
    with app.app_context():
        msgs = build_ai_context(user, 'ai', prompt)
        reply = call_ai_api(msgs)
        time_str = datetime.now().strftime("%H:%M:%S")
        
        save_msg("AI Assistant", user, reply, time_str, "#ff885e", "ai")
        
        socketio.emit('new_message', {
            'sender': "AI Assistant", 'target': user, 'msg': reply, 
            'time': time_str, 'avatar_color': "#ff885e", 'room_type': "ai"
        }, room=sid)

def process_group_ai(prompt, trigger_user):
    with app.app_context():
        msgs = build_ai_context(trigger_user, 'group', prompt)
        reply = call_ai_api(msgs)
        time_str = datetime.now().strftime("%H:%M:%S")
        
        save_msg("AI Assistant", "Group", reply, time_str, "#ff885e", "group")
        
        # 广播回复给所有人
        socketio.emit('new_message', {
            'sender': "AI Assistant", 'target': "Group", 
            'msg': f"@{trigger_user} {reply}", 
            'time': time_str, 'avatar_color': "#ff885e", 'room_type': "group"
        }, broadcast=True)

@socketio.on('reset_system')
def handle_reset(data):
    if data.get('username').lower() == 'admin':
        try:
            conn = sqlite3.connect(DB_FILE, check_same_thread=False)
            conn.cursor().execute("DELETE FROM history")
            conn.commit()
            conn.close()
            emit('system_notification', {'msg': '⚠ 系统已重置'}, broadcast=True)
        except: pass

if __name__ == '__main__':
    init_db()
    print("✅ ChatNow Pro AI 启动: http://0.0.0.0:9527")
    socketio.run(app, host='0.0.0.0', port=9527, debug=False, allow_unsafe_werkzeug=True)
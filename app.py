from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')
socketio = SocketIO(app, cors_allowed_origins="*")

# ========== 全局匹配数据 ==========
total_players = 200          # 默认总人数
max_buyers = 100             # 买方总名额
max_sellers = 100            # 卖方总名额
current_buyers = 0           # 已加入的买方人数
current_sellers = 0          # 已加入的卖方人数

waiting_buyers = []          # 等待匹配的买方列表 (存放 sid)
waiting_sellers = []         # 等待匹配的卖方列表

clients = {}                 # {sid: {"role": "buyer", "name": "张三", "info": "..."}}
pairs = {}                   # {sid: opponent_info}

# ========== 辅助函数 ==========
def try_match(sid):
    """尝试为某个用户进行匹配"""
    user = clients.get(sid)
    if not user:
        return

    if user['role'] == 'buyer':
        if waiting_sellers:
            seller_sid = waiting_sellers.pop(0)
            seller = clients[seller_sid]
            pairs[sid] = seller
            pairs[seller_sid] = user
            socketio.emit('match_success', {'opponent': seller}, room=sid)
            socketio.emit('match_success', {'opponent': user}, room=seller_sid)
            print(f"✅ 配对成功: 买家 {user['name']} 与 卖家 {seller['name']}")
        else:
            if sid not in waiting_buyers:
                waiting_buyers.append(sid)
                socketio.emit('waiting', {'message': '等待卖家加入...'}, room=sid)
    else:  # seller
        if waiting_buyers:
            buyer_sid = waiting_buyers.pop(0)
            buyer = clients[buyer_sid]
            pairs[sid] = buyer
            pairs[buyer_sid] = user
            socketio.emit('match_success', {'opponent': buyer}, room=sid)
            socketio.emit('match_success', {'opponent': user}, room=buyer_sid)
            print(f"✅ 配对成功: 卖家 {user['name']} 与 买家 {buyer['name']}")
        else:
            if sid not in waiting_sellers:
                waiting_sellers.append(sid)
                socketio.emit('waiting', {'message': '等待买家加入...'}, room=sid)

# ========== 路由 ==========
@app.route('/')
def index():
    """用户访问的主页面"""
    return app.send_static_file('index.html')

@app.route('/admin')
def admin_page():
    """管理员设置页面"""
    return app.send_static_file('admin.html')

# ========== Socket.IO 事件处理 ==========
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    print(f"🔗 客户端连接: {sid}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"❌ 客户端断开: {sid}")
    # 从等待队列中移除
    if sid in waiting_buyers:
        waiting_buyers.remove(sid)
    if sid in waiting_sellers:
        waiting_sellers.remove(sid)
    # 从clients中移除
    if sid in clients:
        user = clients.pop(sid)
        global current_buyers, current_sellers
        if user['role'] == 'buyer':
            current_buyers -= 1
        else:
            current_sellers -= 1

@socketio.on('register')
def handle_register(data):
    sid = request.sid
    role = data.get('role')
    name = data.get('name', '匿名')
    info = data.get('info', '')

    global current_buyers, current_sellers

    # 检查是否已达人数上限
    if role == 'buyer' and current_buyers >= max_buyers:
        emit('error', {'message': '买方人数已满，无法加入'})
        return False
    if role == 'seller' and current_sellers >= max_sellers:
        emit('error', {'message': '卖方人数已满，无法加入'})
        return False

    # 保存用户信息
    clients[sid] = {
        'role': role,
        'name': name,
        'info': info
    }
    if role == 'buyer':
        current_buyers += 1
    else:
        current_sellers += 1

    emit('registered', {'message': f'已登记为{role}', 'role': role})
    print(f"📝 用户登记: {name} ({role})")

    # 登记后自动尝试匹配
    try_match(sid)

@socketio.on('start_match')
def handle_start_match():
    sid = request.sid
    if sid not in clients:
        emit('error', {'message': '请先填写身份信息'})
        return
    try_match(sid)

@socketio.on('set_total')
def handle_set_total(data):
    global total_players, max_buyers, max_sellers
    try:
        total = int(data.get('total', 200))
        total_players = total
        max_buyers = total // 2
        max_sellers = total // 2
        print(f"⚙️ 总人数设置为 {total}，买卖双方各 {max_buyers} 人")
        emit('total_set', {'total': total_players, 'buyers_max': max_buyers, 'sellers_max': max_sellers}, broadcast=True)
    except:
        emit('error', {'message': '请输入有效数字'})

@socketio.on('get_status')
def handle_get_status():
    emit('status', {
        'total': total_players,
        'buyers_joined': current_buyers,
        'sellers_joined': current_sellers,
        'waiting_buyers': len(waiting_buyers),
        'waiting_sellers': len(waiting_sellers)
    })

# ========== 启动服务器 ==========
if __name__ == '__main__':
    # 设置静态文件夹为当前目录，以便提供 index.html 和 admin.html
    import os
    app._static_folder = os.path.abspath(".")
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

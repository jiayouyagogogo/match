from flask import Flask
from flask_socketio import SocketIO, emit
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

total_players = 200
max_buyers = 100
max_sellers = 100
current_buyers = 0
current_sellers = 0

waiting_buyers = []
waiting_sellers = []
clients = {}
pairs = {}

def try_match(sid):
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
        else:
            if sid not in waiting_buyers:
                waiting_buyers.append(sid)
                socketio.emit('waiting', {'message': '等待卖家加入...'}, room=sid)
    else:
        if waiting_buyers:
            buyer_sid = waiting_buyers.pop(0)
            buyer = clients[buyer_sid]
            pairs[sid] = buyer
            pairs[buyer_sid] = user
            socketio.emit('match_success', {'opponent': buyer}, room=sid)
            socketio.emit('match_success', {'opponent': user}, room=buyer_sid)
        else:
            if sid not in waiting_sellers:
                waiting_sellers.append(sid)
                socketio.emit('waiting', {'message': '等待买家加入...'}, room=sid)

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/admin')
def admin():
    return app.send_static_file('admin.html')

@socketio.on('connect')
def connect():
    print(f'Connected: {request.sid}')

@socketio.on('disconnect')
def disconnect():
    sid = request.sid
    if sid in waiting_buyers:
        waiting_buyers.remove(sid)
    if sid in waiting_sellers:
        waiting_sellers.remove(sid)
    if sid in clients:
        user = clients.pop(sid)
        global current_buyers, current_sellers
        if user['role'] == 'buyer':
            current_buyers -= 1
        else:
            current_sellers -= 1

@socketio.on('register')
def register(data):
    sid = request.sid
    role = data['role']
    name = data.get('name', '匿名')
    info = data.get('info', '')
    global current_buyers, current_sellers
    if role == 'buyer' and current_buyers >= max_buyers:
        emit('error', {'message': '买方人数已满'})
        return
    if role == 'seller' and current_sellers >= max_sellers:
        emit('error', {'message': '卖方人数已满'})
        return
    clients[sid] = {'role': role, 'name': name, 'info': info}
    if role == 'buyer':
        current_buyers += 1
    else:
        current_sellers += 1
    emit('registered', {'role': role})
    try_match(sid)

@socketio.on('start_match')
def start_match():
    try_match(request.sid)

@socketio.on('set_total')
def set_total(data):
    global total_players, max_buyers, max_sellers
    total = int(data['total'])
    total_players = total
    max_buyers = total // 2
    max_sellers = total // 2
    emit('total_set', {'total': total_players})

@socketio.on('get_status')
def get_status():
    emit('status', {
        'total': total_players,
        'buyers_joined': current_buyers,
        'sellers_joined': current_sellers,
        'waiting_buyers': len(waiting_buyers),
        'waiting_sellers': len(waiting_sellers)
    })

if __name__ == '__main__':
    app._static_folder = os.path.abspath(".")
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

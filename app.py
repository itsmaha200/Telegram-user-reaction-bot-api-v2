from flask import Flask, request, jsonify
from telethon import TelegramClient, events
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import os
import random
import string
import json
import asyncio
import threading
import time

app = Flask(__name__)

# ================= CONFIG =================
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')

# ================= DATABASE =================
DB_FILE = 'database.json'

def load_db():
    try:
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'users': {}, 'temp_sessions': {}}

def save_db(data):
    with open(DB_FILE, 'w') as f:
        json.dump(data, f)

# ================= HELPERS =================
def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

active_bots = {}

# ================= LOGIN =================
@app.route('/Start/login/<api_id>/<api_hash>/<phone>', methods=['GET'])
def custom_login(api_id, api_hash, phone):

    try:
        api_id = int(api_id)

        client = TelegramClient(f"sessions/{phone}", api_id, api_hash)
        client.connect()

        if not client.is_user_authorized():
            client.send_code_request(phone)

            code = generate_code()

            db = load_db()
            db['temp_sessions'][code] = {
                'phone': phone,
                'api_id': api_id,
                'api_hash': api_hash,
                'time': time.time()
            }
            save_db(db)

            return jsonify({
                "status": "code_sent",
                "code": code,
                "next": f"/Start/verify/{code}/OTP"
            })

        return jsonify({"error": "Already logged in"})

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= VERIFY =================
@app.route('/Start/verify/<code>/<otp>', methods=['GET'])
def custom_verify(code, otp):

    db = load_db()
    session = db['temp_sessions'].get(code)

    if not session:
        return jsonify({"error": "Invalid code"})

    try:
        phone = session['phone']

        client = TelegramClient(
            f"sessions/{phone}",
            session['api_id'],
            session['api_hash']
        )

        client.connect()
        client.sign_in(phone=phone, code=otp)

        me = client.get_me()
        auth_code = generate_code()

        db['users'][auth_code] = {
            'user_id': me.id,
            'phone': phone,
            'active': False,
            'group_id': None,
            'emoji': '😁'
        }

        del db['temp_sessions'][code]
        save_db(db)

        return jsonify({
            "status": "success",
            "auth": auth_code,
            "next": f"/Start/bot/{auth_code}/GROUP_ID/🔥"
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= START BOT =================
@app.route('/Start/bot/<auth>/<group_id>/<emoji>', methods=['GET'])
def custom_start(auth, group_id, emoji):

    db = load_db()
    user = db['users'].get(auth)

    if not user:
        return jsonify({"error": "Invalid auth"})

    try:
        group_id = int(group_id)

        # ✅ Stop previous bot if running
        if auth in active_bots:
            try:
                active_bots[auth]['client'].disconnect()
            except:
                pass

        client = TelegramClient(f"sessions/{user['phone']}", API_ID, API_HASH)
        client.connect()

        @client.on(events.NewMessage(chats=group_id))
        async def handler(event):
            try:
                reaction = ReactionEmoji(emoticon=emoji)
                await client(SendReactionRequest(
                    peer=await event.get_input_chat(),
                    msg_id=event.message.id,
                    reaction=[reaction]
                ))
                print("✅ Reaction Sent")

            except Exception as e:
                print("❌ Reaction Error:", str(e))

        loop = asyncio.new_event_loop()
        threading.Thread(target=run_bot, args=(loop, client), daemon=True).start()

        active_bots[auth] = {
            'client': client,
            'group_id': group_id,
            'emoji': emoji,
            'phone': user['phone']
        }

        # ✅ Update DB
        user['active'] = True
        user['group_id'] = group_id
        user['emoji'] = emoji
        db['users'][auth] = user
        save_db(db)

        return jsonify({"status": "started"})

    except Exception as e:
        return jsonify({"error": str(e)})

# ================= STOP BOT =================
@app.route('/Start/stop/<auth>', methods=['GET'])
def stop_bot(auth):

    if auth in active_bots:
        try:
            active_bots[auth]['client'].disconnect()
            del active_bots[auth]

            db = load_db()
            if auth in db['users']:
                db['users'][auth]['active'] = False
                save_db(db)

            return jsonify({"status": "stopped"})

        except Exception as e:
            return jsonify({"error": str(e)})

    return jsonify({"error": "Bot not running"})

# ================= STATUS =================
@app.route('/Start/status/<auth>', methods=['GET'])
def status(auth):

    db = load_db()
    user = db['users'].get(auth)

    if not user:
        return jsonify({"error": "Invalid auth"})

    return jsonify({
        "active": auth in active_bots,
        "group_id": user.get('group_id'),
        "emoji": user.get('emoji'),
        "phone": user.get('phone')
    })

# ================= LIST =================
@app.route('/Start/list', methods=['GET'])
def list_bots():

    bots = []

    for auth, data in active_bots.items():
        bots.append({
            "auth": auth,
            "group_id": data['group_id'],
            "emoji": data['emoji'],
            "phone": data['phone']
        })

    return jsonify({
        "total": len(bots),
        "bots": bots
    })

# ================= LOOP =================
def run_bot(loop, client):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(client.run_until_disconnected())

# ================= HOME =================
@app.route('/')
def home():
    return jsonify({"status": "running 🔥"})

# ================= MAIN =================
if __name__ == '__main__':

    os.makedirs('sessions', exist_ok=True)

    port = int(os.environ.get("PORT", 5000))

    print("🔥 SERVER STARTING")

    app.run(host='0.0.0.0', port=port)

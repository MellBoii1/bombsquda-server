from flask import (
    Flask, 
    request, 
    jsonify, 
    abort, 
    send_from_directory,
    render_template_string
)
import json
import os, sys
import time

app = Flask(__name__)

DATA_FILE = "leaderboard.json"
port = int(os.environ.get("PORT", 5000))
ONLINE_TIMEOUT = 10  # seconds without ping = offline
ADMIN_KEY = "just_lemme_fuckin_edit_stuff_already" 
RUNTIME_FILE = "runtime.json"
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def cleanup_offline_clients(runtime):
    now = time.time()
    online = runtime.get("online_clients", {})

    runtime["online_clients"] = {
        bs_id: info
        for bs_id, info in online.items()
        if now - info.get("last_seen", 0) <= ONLINE_TIMEOUT
    }

def clean_display_name(s: str) -> str:
    return "".join(c for c in s if not (0xE000 <= ord(c) <= 0xF8FF)).strip()

@app.errorhandler(404)
def page_not_found(error):
    return send_from_directory(".", "not_found.html"), 404

@app.route("/leaderboard")
def leaderboard():
    return send_from_directory(".", "leaderboard.html")

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/bot")
def bot():
    return send_from_directory(".", "bot.html")
    

def load_runtime():
    if not os.path.exists(RUNTIME_FILE):
        return {}

    with open(RUNTIME_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_runtime(data):
    with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

@app.route("/about")
def about():
    return send_from_directory(".", "about.html")

@app.route("/online", methods=["GET"])
def get_online_players():
    runtime = load_runtime()
    cleanup_offline_clients(runtime)
    save_runtime(runtime)

    return jsonify(runtime.get("online_clients", {}))
    
@app.route("/ping", methods=["POST"])
def ping():
    data = request.json
    bs_id = data["bs_id"]

    runtime = load_runtime()
    runtime.setdefault("online_clients", {})
    runtime["online_clients"][bs_id] = {
        "last_seen": time.time(),
        "account": data.get("account"),
        "device_id": data.get("device_id"),
        "bs_version": data.get("client_version"),
        "squda_version": data.get("squda_version"),
        "squda_updatedate": data.get("squda_updatedate"),
    }
    cleanup_offline_clients(runtime)
    save_runtime(runtime)

    return {"ok": True}

@app.route("/friends/request", methods=["POST"])
def send_friend_request():
    data = request.get_json(silent=True) or {}
    sender = clean_display_name(data.get("from", ""))
    target = clean_display_name(data.get("to", ""))

    if not sender or not target or sender == target:
        return jsonify({"error": "invalid"}), 400

    runtime = load_runtime()
    runtime.setdefault("friend_requests", {})
    runtime.setdefault("friends", {})

    # Already friends?
    if target in runtime["friends"].get(sender, []):
        return jsonify({"status": "already_friends"})

    runtime["friend_requests"].setdefault(target, [])
    if sender not in runtime["friend_requests"][target]:
        runtime["friend_requests"][target].append(sender)

    save_runtime(runtime)
    return jsonify({"status": "sent"})

@app.route("/friends/respond", methods=["POST"])
def respond_friend_request():
    data = request.get_json(silent=True) or {}
    user = clean_display_name(data.get("user", ""))
    sender = clean_display_name(data.get("from", ""))
    accept = bool(data.get("accept", False))

    runtime = load_runtime()
    requests = runtime.setdefault("friend_requests", {})
    friends = runtime.setdefault("friends", {})

    if sender not in requests.get(user, []):
        return jsonify({"error": "no_request"}), 400

    requests[user].remove(sender)
    if not requests[user]:
        del requests[user]

    if accept:
        friends.setdefault(user, []).append(sender)
        friends.setdefault(sender, []).append(user)

    save_runtime(runtime)
    return jsonify({"status": "ok"})

@app.route("/friends/list", methods=["POST"])
def get_friends():
    data = request.get_json(silent=True) or {}
    user = clean_display_name(data.get("user", ""))

    runtime = load_runtime()
    return jsonify({
        "friends": runtime.get("friends", {}).get(user, []),
        "requests": runtime.get("friend_requests", {}).get(user, [])
    })

@app.route("/get_commands", methods=["POST"])
def get_commands():
    data = request.get_json(silent=True) or {}
    bs_id = data.get("bs_id")

    if not bs_id:
        return jsonify([])

    runtime = load_runtime()
    cmds = runtime.get("commands", {}).pop(bs_id, [])
    cleanup_offline_clients(runtime)
    save_runtime(runtime)

    return jsonify(cmds)

@app.route("/send_command", methods=["POST"])
def send_command():
    data = request.json
    bs_id = data["bs_id"]

    runtime = load_runtime()
    runtime["commands"].setdefault(bs_id, []).append(data)
    save_runtime(runtime)

    return {"queued": True}

@app.route("/admin/leaderboard", methods=["GET", "POST"])
def admin_leaderboard():
    if request.args.get("key") != ADMIN_KEY:
        abort(403)

    data = load_data()

    if request.method == "POST":
        level = request.form["level"]
        player = request.form["player"]
        time = float(request.form["time"])

        if level not in data:
            data[level] = {}

        data[level][player] = time
        save_data(data)
    print('warning: a request was successfully sent to access the admin panel. Was it you?')
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Leaderboard Admin</title>
    <style>
        body { background:#0e1a12; color:#c7f7d4; font-family:Arial; padding:40px; }
        h1 { text-align:center; }
        .box { max-width:600px; margin:auto; background:#12261a; padding:20px; border-radius:12px; }
        input, button { padding:8px; margin:5px; }
        table { width:100%; margin-top:20px; }
        td, th { padding:6px; }
        .delete { color:#ff6666; cursor:pointer; }
    </style>
</head>
<body>
<div class="box">
<h1>Admin Panel</h1>

<form method="post">
    <input name="level" placeholder="Level key" required>
    <input name="player" placeholder="Player name" required>
    <input name="time" placeholder="Time (seconds)" required>
    <button>Add / Update</button>
</form>

<table>
<tr><th>Level</th><th>Player</th><th>Time</th><th></th></tr>
{% for level, players in data.items() %}
    {% for player, time in players.items() %}
    <tr>
        <td>{{level}}</td>
        <td>{{player}}</td>
        <td>{{"%.3f"|format(time)}}</td>
        <td>
            <a class="delete" href="/admin/delete?key={{key}}&level={{level}}&player={{player}}">Delete</a>
        </td>
    </tr>
    {% endfor %}
{% endfor %}
</table>
</div>
</body>
</html>
""", data=data, key=ADMIN_KEY)

@app.route("/admin/delete")
def admin_delete():
    if request.args.get("key") != ADMIN_KEY:
        abort(403)

    level = request.args["level"]
    player = request.args["player"]

    data = load_data()

    if level in data and player in data[level]:
        del data[level][player]
        if not data[level]:
            del data[level]
        save_data(data)
    print(f'warning: a request was successfully sent to delete {player}\'s progress. Was it you?')
    return "Deleted. <a href='/admin/leaderboard?key=" + ADMIN_KEY + "'>Back</a>"

@app.route("/submit", methods=["POST"])
def submit():
    payload = request.json

    level = payload["level"]
    player = payload["player"]
    time = payload["time"]

    data = load_data()

    if level not in data:
        data[level] = {}

    best = data[level].get(player)
    if best is None or time < best:
        data[level][player] = time

    save_data(data)
    print(f'{player} submitted time {time} for {level}')
    return jsonify({"status": "ok"})

@app.route("/get/<level>")
def get_level(level):
    data = load_data()
    return jsonify(data.get(level, {}))

@app.route("/get/all")
def get_all():
    if not os.path.exists(DATA_FILE):
        return {}

    with open(DATA_FILE, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)


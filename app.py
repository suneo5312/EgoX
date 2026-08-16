from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
import sys
import time
import threading
import subprocess
from datetime import datetime, timedelta
from Utilities.until import load_accounts, load_guest_accounts, load_usage_history, save_usage_history, save_guest_accounts
from Api.Account import get_garena_token, get_major_login
from Api.InGame import get_player_personal_show, get_player_stats, search_account_by_keyword, send_like
from Additional import GenerateAccounts


accounts = load_accounts()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(BASE_DIR, "LevelUpBot")
CONFIG_DIR = os.path.join(BASE_DIR, "Configuration")
BOT_CTRL_FILE = os.path.join(CONFIG_DIR, "BotControl.json")
BOT_CTRL_RESULT_FILE = os.path.join(CONFIG_DIR, "BotControlResult.json")
BOT_STATUS_FILE = os.path.join(CONFIG_DIR, "BotStatus.json")
BOT_PID_FILE = os.path.join(BOT_DIR, "bot.pid")


def normalize_server(name):
    srv = (name or "IND").upper().strip()
    if srv in accounts:
        return srv
    for k in accounts:
        if k.startswith(srv):
            return k
    return None


def bank_key(bank, name):
    srv = (name or "IND").upper().strip()
    if srv in bank:
        return srv
    for k in bank:
        if k.startswith(srv):
            return k
    return None


app = Flask(__name__)
# Enable CORS for all origins on all routes
CORS(app)




@app.route('/', methods=['GET'])
def root():
    display_servers = sorted({k.rstrip("0123456789") for k in accounts} | {k for k in load_guest_accounts()})
    return render_template('index.html', servers=display_servers)


@app.route('/player', methods=['GET'])
def player_page():
    display_servers = sorted({k.rstrip("0123456789") for k in accounts} | {k for k in load_guest_accounts()})
    return render_template('player.html', servers=display_servers)


@app.route('/likes', methods=['GET'])
def likes_page():
    display_servers = sorted({k.rstrip("0123456789") for k in accounts} | {k for k in load_guest_accounts()})
    return render_template('likes.html', servers=display_servers)


@app.route('/guests', methods=['GET'])
def guests_page():
    display_servers = sorted({k.rstrip("0123456789") for k in accounts} | {k for k in load_guest_accounts()})
    return render_template('guests.html', servers=display_servers)


@app.route('/bot', methods=['GET'])
def bot_page():
    display_servers = sorted({k.rstrip("0123456789") for k in accounts} | {k for k in load_guest_accounts()})
    return render_template('bot.html', servers=display_servers)


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/api/player_info', methods=['GET'])
def api_player_info():
    try:
        server = (request.args.get('server') or 'IND').upper()
        uid = request.args.get('uid')
        gamemode = (request.args.get('gamemode') or 'br').lower()
        matchmode = (request.args.get('matchmode') or 'CAREER').upper()

        if not uid or not uid.isdigit():
            return jsonify({"success": False, "error": "UID parameter is required and must be numeric"}), 400
        auth_key = normalize_server(server)
        if not auth_key:
            return jsonify({"success": False, "error": f"Server '{server}' not found. Available: {sorted(set(k.rstrip('0123456789') for k in accounts))}"}), 400
        if gamemode not in ['br', 'cs']:
            return jsonify({"success": False, "error": "gamemode must be 'br' or 'cs'"}), 400
        if matchmode not in ['CAREER', 'NORMAL', 'RANKED']:
            return jsonify({"success": False, "error": "matchmode must be CAREER, NORMAL or RANKED"}), 400

        auth_response = get_garena_token(accounts[auth_key]['uid'], accounts[auth_key]['password'])
        if not auth_response or 'access_token' not in auth_response:
            return jsonify({"success": False, "error": "Garena authentication failed"}), 401
        login_response = get_major_login(auth_response["access_token"], auth_response["open_id"])
        if not login_response or 'token' not in login_response:
            return jsonify({"success": False, "error": "Major login failed"}), 401

        basicinfo = get_player_personal_show(login_response["serverUrl"], login_response["token"], int(uid))
        try:
            stats = get_player_stats(login_response["token"], login_response["serverUrl"], gamemode, int(uid), matchmode)
        except Exception:
            stats = None

        return jsonify({
            "success": True,
            "server": server,
            "uid": uid,
            "gamemode": gamemode,
            "matchmode": matchmode,
            "basicinfo": basicinfo or {},
            "stats": stats or {},
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Internal error: {str(e)}"}), 500


@app.route('/api/guests', methods=['GET'])
def api_guests():
    try:
        bank = load_guest_accounts()
        usage = load_usage_history()
        out = {}
        for srv, guests in bank.items():
            gl = guests if isinstance(guests, list) else [guests]
            arr = []
            for g in gl:
                liked_count = sum(1 for t in usage.values() for day in t.values() if str(g.get("uid")) in day)
                arr.append({"uid": g.get("uid"), "password": g.get("password", ""), "likes_sent": liked_count})
            out[srv] = arr
        return jsonify({"success": True, "guests": out}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load guest bank: {str(e)}"}), 500


@app.route('/api/guests/add', methods=['POST'])
def api_guests_add():
    try:
        data = request.get_json(silent=True) or {}
        server = str(data.get('server') or 'IND').upper()
        bank = load_guest_accounts()
        key = bank_key(bank, server)
        gl = bank.get(key, [])
        if not isinstance(gl, list):
            gl = []

        def extract(obj):
            found = []
            if isinstance(obj, dict):
                uid = obj.get('uid') or obj.get('account_id') or obj.get('external_uid')
                pw = obj.get('password') or obj.get('passwd') or obj.get('password_hash')
                if uid is not None and pw is not None:
                    found.append({"uid": str(uid), "password": str(pw)})
                for v in obj.values():
                    found.extend(extract(v))
            elif isinstance(obj, list):
                for v in obj:
                    found.extend(extract(v))
            return found

        entries = []
        if data.get('uid') and data.get('password'):
            entries.append({"uid": str(data['uid']).strip(), "password": str(data['password']).strip()})
        if data.get('json_text'):
            try:
                parsed = json.loads(data['json_text'])
            except Exception as e:
                return jsonify({"success": False, "error": f"Invalid JSON: {str(e)}"}), 400
            entries.extend(extract(parsed))

        if not entries:
            return jsonify({"success": False, "error": "No guest entries found. Provide uid+password or JSON with uid/password fields."}), 400

        existing = {str(g.get('uid')) for g in gl}
        added = 0
        for e in entries:
            if not e['uid'].isdigit() or not e['password']:
                continue
            if e['uid'] in existing:
                continue
            gl.append(e)
            existing.add(e['uid'])
            added += 1

        bank[key] = gl
        save_guest_accounts(bank)
        return jsonify({"success": True, "added": added, "server": key or server, "total": len(gl)}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to add guests: {str(e)}"}), 500


@app.route('/api/guests/remove', methods=['POST'])
def api_guests_remove():
    try:
        data = request.get_json(silent=True) or {}
        server = str(data.get('server') or 'IND').upper()
        uid = str(data.get('uid') or '')
        bank = load_guest_accounts()
        key = bank_key(bank, server)
        gl = bank.get(key)
        if not isinstance(gl, list):
            return jsonify({"success": False, "error": f"No guest accounts for server: {server}"}), 404
        before = len(gl)
        bank[key] = [g for g in gl if str(g.get('uid')) != uid]
        if len(bank[key]) == before:
            return jsonify({"success": False, "error": f"Guest {uid} not found"}), 404
        save_guest_accounts(bank)
        return jsonify({"success": True, "removed": uid, "server": key, "total": len(bank[key])}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to remove guest: {str(e)}"}), 500


@app.route('/api/guests/generate', methods=['POST'])
def api_guests_generate():
    try:
        data = request.get_json(silent=True) or {}
        server = str(data.get('server') or 'IND').upper().strip().rstrip("0123456789") or "IND"
        try:
            count = min(max(int(data.get('count') or 3), 1), 20)
        except (TypeError, ValueError):
            count = 3
        result = {}

        def run():
            try:
                made, _ = GenerateAccounts.generate_guests(server, count)
                result['made'] = made
                result['ok'] = True
            except Exception as e:
                result['ok'] = False
                result['error'] = str(e)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=420)
        if not result.get('ok'):
            return jsonify({"success": False, "error": result.get('error', 'generation timed out')}), 500
        made = result.get('made', [])
        return jsonify({
            "success": True,
            "server": server,
            "count": len(made),
            "created": made,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to generate guests: {str(e)}"}), 500


def bot_process_alive():
    try:
        with open(BOT_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        try:
            with open(f"/proc/{pid}/stat") as f:
                state = f.read().split(") ")[-1].split()[0]
            if state == "Z":
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False


def _read_json_file(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


@app.route('/api/likes/today', methods=['GET'])
def api_likes_today():
    try:
        usage = load_usage_history()
        today = datetime.now().strftime("%Y-%m-%d")
        targets = {t: len(usage.get(t, {}).get(today, [])) for t in usage if usage.get(t, {}).get(today)}
        return jsonify({
            "success": True,
            "date": today,
            "targets_today": len(targets),
            "likes_today": sum(targets.values()),
            "per_target": targets,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/bot/status', methods=['GET'])
def api_bot_status():
    status = _read_json_file(BOT_STATUS_FILE) or {}
    status['process_alive'] = bot_process_alive()
    status['running'] = bool(status.get('running') and status['process_alive'])
    try:
        if os.path.exists(os.path.join(BOT_DIR, "bot.log")):
            with open(os.path.join(BOT_DIR, "bot.log"), "rb") as f:
                f.seek(max(0, os.path.getsize(os.path.join(BOT_DIR, "bot.log")) - 6000))
                status['log_tail'] = f.read().decode("utf-8", errors="replace")[-3000:]
    except Exception:
        pass
    return jsonify(status), 200


@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    try:
        data = request.get_json(silent=True) or {}
        uid = str(data.get('uid') or '').strip()
        password = str(data.get('password') or '').strip()
        if not uid or not password:
            return jsonify({"success": False, "error": "uid and password are required"}), 400
        if bot_process_alive():
            return jsonify({"success": False, "error": "Bot is already running — stop it first"}), 409
        env = dict(os.environ)
        env['GUEST_UID'] = uid
        env['GUEST_PASSWORD'] = password
        log_path = os.path.join(BOT_DIR, "bot.log")
        with open(log_path, "a") as logf:
            proc = subprocess.Popen(
                [sys.executable, "-u", "app.py"],
                cwd=BOT_DIR, env=env, stdout=logf, stderr=logf,
                stdin=subprocess.DEVNULL, start_new_session=True,
            )
        with open(BOT_PID_FILE, "w") as f:
            f.write(str(proc.pid))
        return jsonify({"success": True, "pid": proc.pid, "uid": uid}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to start bot: {str(e)}"}), 500


@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    graceful = False
    killed = False
    try:
        cmd = {"id": f"stop-{int(time.time() * 1000)}", "action": "stop_bot",
               "params": {}, "pending": True, "at": time.time()}
        with open(BOT_CTRL_FILE, "w") as f:
            json.dump(cmd, f, indent=2)
        graceful = True
    except Exception:
        pass
    try:
        with open(BOT_PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        killed = True
    except Exception:
        pass
    try:
        os.remove(BOT_PID_FILE)
    except Exception:
        pass
    return jsonify({"success": True, "graceful": graceful, "killed": killed}), 200


@app.route('/api/bot/command', methods=['POST'])
def api_bot_command():
    try:
        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '').strip()
        params = data.get('params') or {}
        if not action:
            return jsonify({"success": False, "error": "action is required"}), 400
        if not bot_process_alive():
            return jsonify({"success": False, "error": "Bot is not running"}), 409
        cid = f"cmd-{int(time.time() * 1000)}"
        cmd = {"id": cid, "action": action, "params": params, "pending": True, "at": time.time()}
        with open(BOT_CTRL_FILE, "w") as f:
            json.dump(cmd, f, indent=2)
        for _ in range(80):
            time.sleep(0.5)
            res = _read_json_file(BOT_CTRL_RESULT_FILE)
            if res and res.get('id') == cid:
                return jsonify({
                    "success": res.get('status') == 'done',
                    "action": action,
                    "result": res.get('result', ''),
                }), 200
        return jsonify({"success": False, "error": "Timed out waiting for bot response", "action": action}), 504
    except Exception as e:
        return jsonify({"success": False, "error": f"Bot command failed: {str(e)}"}), 500


@app.route('/get_search_account_by_keyword', methods=['GET'])
def get_search_account_by_keyword():
    try:
        # Get request parameters
        region = request.args.get('server', 'IND').upper()
        search_term = request.args.get('keyword')
        
        # Validate keyword parameter
        if not search_term:
            return json.dumps({"error": "Keyword parameter is required"}, indent=2), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Enforce minimum keyword length
        if len(search_term.strip()) < 3:
            return json.dumps({"error": "Keyword must be at least 3 characters long"}, indent=2), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Validate server exists in accounts
        auth_key = normalize_server(region)
        if not auth_key:
            return json.dumps({"error": f"Invalid server: {region}"}, indent=2), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Authenticate with Garena
        auth_response = get_garena_token(accounts[auth_key]['uid'], accounts[auth_key]['password'])
        if not auth_response or 'access_token' not in auth_response:
            return json.dumps({"error": "Authentication failed"}, indent=2), 401, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Get major login credentials
        login_response = get_major_login(auth_response["access_token"], auth_response["open_id"])
        if not login_response or 'token' not in login_response:
            return json.dumps({"error": "Major login failed"}, indent=2), 401, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Search for accounts
        search_results = search_account_by_keyword(login_response["serverUrl"], login_response["token"], search_term)
        
        # Return formatted response
        formatted_response = json.dumps(search_results, indent=2, ensure_ascii=False)
        return formatted_response, 200, {'Content-Type': 'application/json; charset=utf-8'}
        
    except KeyError as e:
        return json.dumps({"error": f"Missing configuration: {str(e)}"}, indent=2), 500, {'Content-Type': 'application/json; charset=utf-8'}
    except Exception as e:
        return json.dumps({"error": f"Internal server error: {str(e)}"}, indent=2), 500, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/get_player_stats', methods=['GET'])
def get_player_stat():
    try:
        # Get and validate parameters
        server = request.args.get('server', 'IND').upper()
        uid = request.args.get('uid')
        gamemode = request.args.get('gamemode', 'br').lower()
        matchmode = request.args.get('matchmode', 'CAREER').upper()

        # Validate required parameters
        if not uid:
            return jsonify({
                "success": False,
                "error": "Missing required parameter",
                "message": "UID parameter is required"
            }), 400

        if not uid.isdigit():
            return jsonify({
                "success": False,
                "error": "Invalid UID",
                "message": "UID must be a numeric value"
            }), 400

        # Validate server
        auth_key = normalize_server(server)
        if not auth_key:
            return jsonify({
                "success": False,
                "error": "Invalid server",
                "message": f"Server '{server}' not found. Available servers: {sorted(set(k.rstrip('0123456789') for k in accounts))}"
            }), 400

        # Validate gamemode
        if gamemode not in ['br', 'cs']:
            return jsonify({
                "success": False,
                "error": "Invalid gamemode",
                "message": "Gamemode must be 'br' or 'cs'"
            }), 400

        # Validate matchmode
        if matchmode not in ['CAREER', 'NORMAL', 'RANKED']:
            return jsonify({
                "success": False,
                "error": "Invalid matchmode",
                "message": "Matchmode must be 'CAREER', 'NORMAL', or 'RANKED'"
            }), 400

        # Step 1: Get Garena token
        try:
            garena_token_result = get_garena_token(accounts[auth_key]['uid'], accounts[auth_key]['password'])
            
            if not garena_token_result or 'access_token' not in garena_token_result:
                return jsonify({
                    "success": False,
                    "error": "Garena authentication failed",
                    "message": "Failed to obtain Garena access token"
                }), 401
                
        except Exception as e:
            return jsonify({
                "success": False,
                "error": "Garena authentication error",
                "message": f"Failed to authenticate with Garena: {str(e)}"
            }), 502

        # Step 2: Get Major login
        try:
            major_login_result = get_major_login(garena_token_result["access_token"], garena_token_result["open_id"])
            
            if not major_login_result or 'token' not in major_login_result:
                return jsonify({
                    "success": False,
                    "error": "Major login failed",
                    "message": "Failed to obtain Major login token"
                }), 401
                
        except Exception as e:
            return jsonify({
                "success": False,
                "error": "Major login error",
                "message": f"Failed to login to Major: {str(e)}"
            }), 502

        # Step 3: Get player stats
        try:
            player_stats = get_player_stats(
                major_login_result["token"], 
                major_login_result["serverUrl"], 
                gamemode, 
                uid, 
                matchmode
            )
            
            if not player_stats:
                return jsonify({
                    "success": False,
                    "error": "No stats data",
                    "message": "No player statistics found for the given parameters"
                }), 404

            # Return formatted JSON response
            return jsonify({
                "success": True,
                "data": player_stats,
                "metadata": {
                    "server": server,
                    "uid": uid,
                    "gamemode": gamemode,
                    "matchmode": matchmode
                }
            }), 200
            
        except ValueError as e:
            return jsonify({
                "success": False,
                "error": "Invalid request parameters",
                "message": str(e)
            }), 400
        except ConnectionError as e:
            return jsonify({
                "success": False,
                "error": "Connection error",
                "message": str(e)
            }), 503
        except ProtobufError as e:
            return jsonify({
                "success": False,
                "error": "Data processing error",
                "message": str(e)
            }), 500
        except APIError as e:
            return jsonify({
                "success": False,
                "error": "External API error",
                "message": str(e)
            }), 502
        except Exception as e:
            return jsonify({
                "success": False,
                "error": "Stats retrieval error",
                "message": f"Failed to retrieve player stats: {str(e)}"
            }), 500

    except Exception as e:
        # Catch any unexpected errors
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": "An unexpected error occurred while processing your request"
        }), 500

@app.route('/get_player_personal_show', methods=['GET'])
def get_account_info():
    try:
        # Get parameters with defaults
        server = request.args.get('server', 'IND').upper()
        uid = request.args.get('uid')
        need_gallery_info = request.args.get('need_gallery_info', False)
        need_blacklist = request.args.get('need_blacklist', False)
        need_spark_info = request.args.get('need_spark_info', False)
        call_sign_src = request.args.get('call_sign_src', 7)
        
        # Validate UID parameter - must be integer
        if not uid:
            response = {
                "status": "error",
                "error": "Missing UID",
                "message": "Empty 'uid' parameter. Please provide a valid 'uid'.",
                "code": "MISSING_UID"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Check if UID is a valid integer
        try:
            uid_int = int(uid)
            # Additional validation for UID range if needed
            if uid_int <= 0:
                response = {
                    "status": "error",
                    "error": "Invalid UID",
                    "message": "UID must be a positive integer.",
                    "code": "INVALID_UID_RANGE"
                }
                return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        except (ValueError, TypeError):
            response = {
                "status": "error",
                "error": "Invalid UID",
                "message": "UID must be a valid integer.",
                "code": "INVALID_UID_FORMAT"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Validate server parameter
        auth_key = normalize_server(server)
        if not auth_key:
            response = {
                "status": "error",
                "error": "Invalid Server",
                "message": f"Server '{server}' not found. Available servers: {sorted(set(k.rstrip('0123456789') for k in accounts))}",
                "available_servers": sorted(set(k.rstrip('0123456789') for k in accounts)),
                "code": "SERVER_NOT_FOUND"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Validate need_gallery_info parameter
        try:
            if isinstance(need_gallery_info, str):
                if need_gallery_info.lower() in ['true', '1', 'yes']:
                    need_gallery_info = True
                elif need_gallery_info.lower() in ['false', '0', 'no']:
                    need_gallery_info = False
                else:
                    raise ValueError("Invalid boolean value")
            need_gallery_info = bool(need_gallery_info)
        except (ValueError, TypeError):
            response = {
                "status": "error",
                "error": "Invalid Parameter",
                "message": "need_gallery_info must be a boolean value (true/false, 1/0).",
                "code": "INVALID_GALLERY_PARAM"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        
        # Validate need_blacklist parameter
        try:
            if isinstance(need_blacklist, str):
                if need_blacklist.lower() in ['true', '1', 'yes']:
                    need_blacklist = True
                elif need_blacklist.lower() in ['false', '0', 'no']:
                    need_blacklist = False
                else:
                    raise ValueError("Invalid boolean value")
            need_blacklist = bool(need_blacklist)
        except (ValueError, TypeError):
            response = {
                "status": "error",
                "error": "Invalid Parameter",
                "message": "need_blacklist must be a boolean value (true/false, 1/0).",
                "code": "INVALID_GALLERY_PARAM"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        
        # Validate need_spark_info parameter
        try:
            if isinstance(need_spark_info, str):
                if need_spark_info.lower() in ['true', '1', 'yes']:
                    need_spark_info = True
                elif need_spark_info.lower() in ['false', '0', 'no']:
                    need_spark_info = False
                else:
                    raise ValueError("Invalid boolean value")
            need_spark_info = bool(need_spark_info)
        except (ValueError, TypeError):
            response = {
                "status": "error",
                "error": "Invalid Parameter",
                "message": "need_spark_info must be a boolean value (true/false, 1/0).",
                "code": "INVALID_GALLERY_PARAM"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        
        
        
        
        # Validate call_sign_src parameter
        try:
            call_sign_src_int = int(call_sign_src)
            if call_sign_src_int < 0:
                response = {
                    "status": "error",
                    "error": "Invalid Parameter",
                    "message": "call_sign_src must be a non-negative integer.",
                    "code": "INVALID_CALL_SIGN_SRC"
                }
                return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        except (ValueError, TypeError):
            response = {
                "status": "error",
                "error": "Invalid Parameter",
                "message": "call_sign_src must be a valid integer.",
                "code": "INVALID_CALL_SIGN_FORMAT"
            }
            return jsonify(response), 400, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Check if server account credentials exist
        if 'uid' not in accounts[auth_key] or 'password' not in accounts[auth_key]:
            response = {
                "status": "error",
                "error": "Server Configuration Error",
                "message": f"Server '{server}' is missing required credentials.",
                "code": "SERVER_CONFIG_ERROR"
            }
            return jsonify(response), 500, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Step 1: Get Garena token
        garena_token_result = get_garena_token(accounts[auth_key]['uid'], accounts[auth_key]['password'])
        if not garena_token_result or 'access_token' not in garena_token_result or 'open_id' not in garena_token_result:
            response = {
                "status": "error",
                "error": "Authentication Failed",
                "message": "Failed to obtain Garena token. Invalid credentials or service unavailable.",
                "code": "GARENA_AUTH_FAILED"
            }
            return jsonify(response), 401, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Step 2: Get major login
        major_login_result = get_major_login(garena_token_result["access_token"], garena_token_result["open_id"])
        if not major_login_result or 'serverUrl' not in major_login_result or 'token' not in major_login_result:
            response = {
                "status": "error",
                "error": "Login Failed",
                "message": "Failed to perform major login. Service unavailable.",
                "code": "MAJOR_LOGIN_FAILED"
            }
            return jsonify(response), 401, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Step 3: Get player personal show data
        player_personal_show_result = get_player_personal_show(
            major_login_result["serverUrl"], 
            major_login_result["token"], 
            uid_int, 
            need_gallery_info, 
            call_sign_src_int,
            need_blacklist, 
            need_spark_info
        )
        
        
        
        if not player_personal_show_result:
            response = {
                "status": "error",
                "error": "Data Not Found",
                "message": f"No player data found for UID: {uid_int}",
                "code": "PLAYER_DATA_NOT_FOUND"
            }
            return jsonify(response), 404, {'Content-Type': 'application/json; charset=utf-8'}
        
        # Success response
        formatted_json = json.dumps(player_personal_show_result, indent=2, ensure_ascii=False)
        return formatted_json, 200, {'Content-Type': 'application/json; charset=utf-8'}
    
    except Exception as e:
        # Log the unexpected error for debugging
        print(f"Unexpected error in get_player_personal_show: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        response = {
            "status": "error",
            "error": "Internal Server Error",
            "message": "An unexpected error occurred while processing your request.",
            "code": "INTERNAL_SERVER_ERROR"
        }
        return jsonify(response), 500, {'Content-Type': 'application/json; charset=utf-8'}



def fetch_liked_count(server, uid_int):
    """Fetch the target's current 'liked' count via GetPlayerPersonalShow."""
    try:
        auth_key = normalize_server(server)
        if not auth_key:
            return None
        auth_response = get_garena_token(accounts[auth_key]['uid'], accounts[auth_key]['password'])
        if not auth_response or 'access_token' not in auth_response:
            return None
        login_response = get_major_login(auth_response["access_token"], auth_response["open_id"])
        if not login_response or 'token' not in login_response:
            return None
        profile = get_player_personal_show(login_response["serverUrl"], login_response["token"], uid_int)
        if not profile:
            return None
        return profile.get("basicinfo", {}).get("liked")
    except Exception:
        return None


@app.route('/send_like', methods=['GET', 'POST'])
def send_like_endpoint():
    try:
        server = (request.args.get('server') or request.form.get('server') or 'IND').upper()
        uid = request.args.get('uid') or request.form.get('uid')
        count = int(request.args.get('count') or request.form.get('count') or 1)

        if not uid:
            return jsonify({"status": "error", "error": "Missing UID", "code": "MISSING_UID"}), 400
        try:
            uid_int = int(uid)
        except ValueError:
            return jsonify({"status": "error", "error": "Invalid UID", "code": "INVALID_UID"}), 400
        if count < 1 or count > 100:
            return jsonify({"status": "error", "error": "Count must be between 1 and 100", "code": "INVALID_COUNT"}), 400

        from Utilities.until import load_guest_accounts, load_usage_history, save_usage_history
        from Configuration.APIConfiguration import DEBUG
        import Configuration.APIConfiguration as _cfg
        _cfg.DEBUG = False

        guest_bank = load_guest_accounts()
        key = bank_key(guest_bank, server)
        if not key:
            return jsonify({"status": "error", "error": f"No guest accounts for server: {server}", "code": "NO_GUESTS"}), 400

        guests = guest_bank[key]
        if not isinstance(guests, list):
            guests = [guests]

        usage = load_usage_history()
        target_key = str(uid_int)
        today = datetime.now().strftime("%Y-%m-%d")
        used_today = set(usage.get(target_key, {}).get(today, []))

        available = [g for g in guests if str(g["uid"]) not in used_today]
        if not available:
            return jsonify({"status": "error", "error": "All guest accounts already liked this target today", "code": "ALL_USED"}), 429

        to_send = available[:count]
        sent = 0
        failures = []
        for g in to_send:
            try:
                auth_response = get_garena_token(g["uid"], g["password"])
                if not auth_response or 'access_token' not in auth_response:
                    failures.append(f"auth failed for {g['uid']}")
                    continue
                login_response = get_major_login(auth_response["access_token"], auth_response["open_id"])
                if not login_response or 'token' not in login_response:
                    failures.append(f"login failed for {g['uid']}")
                    continue
                send_like(login_response["serverUrl"], login_response["token"], uid_int, server)
                used_today.add(str(g["uid"]))
                sent += 1
            except Exception as e:
                failures.append(f"{g['uid']}: {str(e)[:80]}")
                break

        entry = usage.setdefault(target_key, {})
        entry[today] = sorted(used_today)
        usage[target_key] = entry
        save_usage_history(usage)

        response = {
            "status": "success" if sent > 0 else "error",
            "uid": uid_int,
            "server": server,
            "likes_sent": sent,
            "requested": count,
            "total_likes_on_target_today": len(used_today),
            "guests_remaining_today": max(0, len(guests) - len(used_today)),
        }
        liked_before = fetch_liked_count(server, uid_int)
        if sent > 0:
            time.sleep(4)
        liked_after = fetch_liked_count(server, uid_int)
        if liked_before is not None or liked_after is not None:
            response["liked_before"] = liked_before
            response["liked_after"] = liked_after
            if liked_before is not None and liked_after is not None:
                response["liked_increase"] = liked_after - liked_before
        if sent == 0 and failures:
            bot_result = send_like_via_bot_token(uid_int, server)
            if bot_result.get("ok"):
                response["status"] = "success"
                response["likes_sent"] = 1
                response["bot_fallback"] = True
            else:
                response["warnings"] = failures + [f"bot fallback: {bot_result.get('error', 'failed')}"]
        elif failures:
            response["warnings"] = failures
        return jsonify(response), 200

    except Exception as e:
        return jsonify({"status": "error", "error": "Internal Server Error", "code": "INTERNAL_SERVER_ERROR"}), 500


def send_like_via_bot_token(target_uid, server):
    """Fallback: send 1 like using the LevelUpBot's saved JWT (LikeProfile)."""
    try:
        import os
        from pathlib import Path
        token_path = Path(__file__).parent / "LevelUpBot" / "token.json"
        if not token_path.exists():
            return {"ok": False, "error": "no bot token.json"}
        with open(token_path) as f:
            tok = json.load(f)
        jwt_token = tok.get("token")
        if not jwt_token:
            return {"ok": False, "error": "empty bot token"}
        region = str(tok.get("region") or server or "IND").upper()
        domain = {
            "IND": "client.ind.freefiremobile.com",
            "BD": "client.bd.freefiremobile.com",
            "TH": "client.th.freefiremobile.com",
            "ID": "client.id.freefiremobile.com",
            "VN": "client.vn.freefiremobile.com",
            "SG": "client.sg.freefiremobile.com",
            "MY": "client.my.freefiremobile.com",
            "BR": "client.br.freefiremobile.com",
            "US": "client.us.freefiremobile.com",
            "RU": "client.ru.freefiremobile.com",
            "ME": "client.me.freefiremobile.com",
            "PK": "client.pk.freefiremobile.com",
        }.get(region, "client.ind.freefiremobile.com")
        server_url = f"https://{domain}"
        from Api.InGame import send_like
        send_like(server_url, jwt_token, int(target_uid), region)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
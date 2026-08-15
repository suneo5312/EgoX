import os
import threading

from app import app


def start_discord_bot():
    try:
        from DiscordBot import run_bot
        token = os.environ.get("FF_BOT_TOKEN")
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Configuration", "DiscordConfig.json")
        if not token and not os.path.exists(cfg):
            print("[server] FF_BOT_TOKEN not set — Discord bot disabled")
            return
        print("[server] Starting Discord bot thread...")
        run_bot()
    except SystemExit as e:
        print(f"[server] Discord bot not started: {e}")
    except Exception as e:
        print(f"[server] Discord bot error: {e}")


_bot_started = False


def start_bot_once():
    global _bot_started
    if _bot_started:
        return
    _bot_started = True
    t = threading.Thread(target=start_discord_bot, daemon=True)
    t.start()


start_bot_once()


def main():
    port = int(os.environ.get("PORT", 5000))
    print(f"[server] Flask API listening on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
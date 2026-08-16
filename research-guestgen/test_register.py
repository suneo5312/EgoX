import hashlib, hmac, random, requests, sys
from urllib.parse import urlencode

SECRET = b"2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
CID = "100067"
URLS = [
    "https://ffmconnect.live.gop.garenanow.com/oauth/guest/register",
    "https://100067.connect.garena.com/oauth/guest/register",
]

def try_register(url: str) -> tuple[int, str]:
    pwd = str(random.randint(1000000000, 9999999999))
    ph = hashlib.sha256(pwd.encode()).hexdigest().upper()
    body = urlencode({"password": ph, "client_type": "2", "source": "2", "app_id": CID})
    sig = hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent": "GarenaMSDK/4.0.19P9(A063 ;Android 13;en;IN;)",
        "Authorization": f"Signature {sig}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    try:
        r = requests.post(url, data=body, headers=headers, timeout=12)
        return r.status_code, r.text[:200]
    except Exception as e:
        return 0, str(e)[:200]

if __name__ == "__main__":
    for u in URLS:
        code, text = try_register(u)
        print(f"{u}\n  -> {code} {text}\n")
        if code == 200 and "uid" in text:
            print("REGISTER WORKS!")
            sys.exit(0)
    print("register still dead")
    sys.exit(1)

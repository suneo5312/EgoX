import hashlib, hmac, random, requests, json
from urllib.parse import urlencode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

SECRET = b"2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
CID = "100067"
UA_MSDK = "GarenaMSDK/4.0.19P9(A063 ;Android 13;en;IN;)"
REGISTER_HOSTS = [
    "https://connect.garena.com/oauth/guest/register",
    "https://100067.connect.garena.com/oauth/guest/register",
    "https://ffmconnect.live.gop.garenanow.com/oauth/guest/register",
]
TOKEN_HOSTS = [
    "https://connect.garena.com/oauth/guest/token/grant",
    "https://100067.connect.garena.com/oauth/guest/token/grant",
    "https://ffmconnect.live.gop.garenanow.com/oauth/guest/token/grant",
]
MAJOR_REGISTER = "https://loginbp.ggblueshark.com/MajorRegister"
MAJOR_LOGIN = "https://loginbp.ggblueshark.com/MajorLogin"

def xor_openid(x: str) -> bytes:
    k = [0,0,0,2,0,1,7,0,0,0,0,0,2,0,1,7,0,0,0,0,0,2,0,1,7,0,0,0,0,0,2,0]
    return bytes(b ^ k[i % len(k)] ^ 48 for i, b in enumerate(x.encode()))

def aes(h: bytes) -> bytes:
    c = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
    return c.encrypt(pad(h, 16))

def ev(n):
    r = bytearray()
    while n:
        b = n & 0x7F
        n >>= 7
        r.append(b | (0x80 if n else 0))
    return bytes(r)

def ef(f, v):
    if isinstance(v, int): return ev((f << 3) | 0) + ev(v)
    b = v.encode() if isinstance(v, str) else v
    return ev((f << 3) | 2) + ev(len(b)) + b

def ep(d):
    p = bytearray()
    for k in sorted(d): p.extend(ef(k, d[k]))
    return bytes(p)

def sign(body: str) -> str:
    return hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()

def main():
    pwd = str(random.randint(1000000000, 9999999999))
    ph = hashlib.sha256(pwd.encode()).hexdigest().upper()
    bd = urlencode({"password": ph, "client_type": "2", "source": "2", "app_id": CID})

    uid = None
    for h in REGISTER_HOSTS:
        try:
            r = requests.post(h, data=bd, timeout=10, headers={
                "User-Agent": UA_MSDK, "Authorization": f"Signature {sign(bd)}",
                "Content-Type": "application/x-www-form-urlencoded"})
            j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            print(f"[REG] {h} -> {r.status_code} {r.text[:80]}")
            if r.status_code == 200 and j.get("uid"):
                uid = j["uid"]; break
        except Exception as e:
            print(f"[REG] {h} -> EXC {str(e)[:60]}")
    if not uid:
        print("NO UID — register failed everywhere"); return

    at = oid = None
    td = {"uid": str(uid), "password": ph, "response_type": "token",
          "client_type": "2", "client_secret": SECRET.decode(), "client_id": CID}
    for h in TOKEN_HOSTS:
        try:
            r = requests.post(h, data=td, timeout=10, headers={"User-Agent": UA_MSDK})
            print(f"[TOK] {h} -> {r.status_code} {r.text[:80]}")
            if r.status_code == 200:
                j = r.json()
                at = j.get("access_token"); oid = j.get("open_id") or j.get("openId")
                if at and oid: break
        except Exception as e:
            print(f"[TOK] {h} -> EXC {str(e)[:60]}")
    if not at or not oid:
        print("NO TOKEN — grant failed"); return

    nick = f"0xMe{''.join('⁰¹²³⁴⁵⁶⁷⁸⁹'[int(d)] for d in str(random.randint(1, 9999)))}"
    pf = {1: nick, 2: at, 3: oid, 5: 102000007, 6: 4, 7: 1, 13: 1, 14: xor_openid(oid), 15: "IND", 16: 1}
    ed = aes(ep(pf))
    hs = {"Authorization": f"Bearer {at}", "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1",
          "ReleaseVersion": "OB54", "Content-Type": "application/octet-stream",
          "Content-Length": str(len(ed)), "User-Agent": UA_MSDK,
          "Host": "loginbp.ggblueshark.com", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"}
    try:
        r = requests.post(MAJOR_REGISTER, data=ed, headers=hs, timeout=10)
        print(f"[MAJORREG] {MAJOR_REGISTER} -> {r.status_code} {r.text[:120]}")
    except Exception as e:
        print(f"[MAJORREG] EXC {str(e)[:60]}")

    try:
        r = requests.post(MAJOR_LOGIN, data=ed, headers=hs, timeout=10)
        print(f"[MAJORLOGIN] {MAJOR_LOGIN} -> {r.status_code} {r.text[:120]}")
    except Exception as e:
        print(f"[MAJORLOGIN] EXC {str(e)[:60]}")

    print(f"\nNEW GUEST: uid={uid} password={ph} (raw pwd={pwd})")

if __name__ == "__main__":
    main()

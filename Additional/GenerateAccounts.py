import requests, random, hashlib, hmac, json, sys, os
from urllib.parse import urlencode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

SECRET = b'2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3'
CID = "100067"
UA = "GarenaMSDK/4.0.19P9(A063 ;Android 13;en;IN;)"

def e(x):
    k = [0,0,0,2,0,1,7,0,0,0,0,0,2,0,1,7,0,0,0,0,0,2,0,1,7,0,0,0,0,0,2,0]
    return bytes(b ^ k[i % len(k)] ^ 48 for i, b in enumerate(x.encode()))

def aes(h):
    c = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
    return c.encrypt(pad(bytes.fromhex(h), 16)).hex()

def ev(n):
    r = bytearray()
    while n:
        b = n & 0x7F
        n >>= 7
        r.append(b | (0x80 if n else 0))
    return bytes(r)

def ef(f, v):
    if type(v) == int:
        return ev((f << 3) | 0) + ev(v)
    b = v.encode() if type(v) == str else v
    return ev((f << 3) | 2) + ev(len(b)) + b

def ep(d):
    p = bytearray()
    for k in sorted(d):
        p.extend(ef(k, d[k]))
    return p

def sign(body):
    return hmac.new(SECRET, body.encode(), hashlib.sha256).hexdigest()

def register(region):
    pwd = str(random.randint(1000000000, 9999999999))
    ph = hashlib.sha256(pwd.encode()).hexdigest().upper()
    session = requests.Session()

    bd = urlencode({'password': ph, 'client_type': '2', 'source': '2', 'app_id': CID})
    hd = {'User-Agent': UA, 'Authorization': f"Signature {sign(bd)}",
          'Content-Type': 'application/x-www-form-urlencoded'}

    # Guest Register - only connect.garena.com answers this in OB54
    r1 = session.post('https://connect.garena.com/oauth/guest/register', data=bd, headers=hd, timeout=12)
    if r1.status_code != 200:
        session.close()
        return None, None, None

    uid = r1.json().get("uid")
    if not uid:
        session.close()
        return None, None, None

    # Token Grant
    td = {'uid': str(uid), 'password': ph, 'response_type': "token", 'client_type': "2",
          'client_secret': SECRET.decode(), 'client_id': CID}
    r2 = session.post("https://connect.garena.com/oauth/guest/token/grant", data=td,
                      headers={'User-Agent': UA}, timeout=12)
    if r2.status_code != 200:
        session.close()
        return None, None, None

    j = r2.json()
    at = j.get("access_token")
    oid = j.get("open_id") or j.get("openId") or j.get("openid")
    if not at or not oid:
        session.close()
        return None, None, None

    # Major Register (profile creation) - works again on ggblueshark OB54
    pf = {1: f"0xMe{''.join('⁰¹²³⁴⁵⁶⁷⁸⁹'[int(d)] for d in str(random.randint(1, 9999)))}",
          2: at, 3: oid, 5: 102000007, 6: 4, 7: 1, 13: 1, 14: e(oid), 15: "IND", 16: 1}
    ed = bytes.fromhex(aes(ep(pf).hex()))

    hs = {"Authorization": f"Bearer {at}", "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1",
          "ReleaseVersion": "OB54", "Content-Type": "application/octet-stream",
          "Content-Length": str(len(ed)), "User-Agent": UA,
          "Host": "loginbp.ggblueshark.com", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"}
    r3 = session.post('https://loginbp.ggblueshark.com/MajorRegister', data=ed, headers=hs, timeout=12)
    session.close()

    if r3.status_code == 200:
        return uid, ph, pwd
    return None, None, None


def main():
    regions = ['IND']
    per_region = 5
    if len(sys.argv) > 1:
        per_region = max(1, int(sys.argv[1]))

    bank_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "Configuration", "GuestAccounts.json")
    try:
        with open(bank_path) as f:
            bank = json.load(f)
    except Exception:
        bank = {}
    if not isinstance(bank, dict):
        bank = {}

    for r in regions:
        gl = bank.get(r, [])
        if not isinstance(gl, list):
            gl = []
        existing = {str(g.get("uid")) for g in gl}
        created = 0
        for _ in range(per_region * 3):
            if created >= per_region:
                break
            uid, ph, _ = register(r)
            if uid and str(uid) not in existing:
                gl.append({"uid": str(uid), "password": ph})
                existing.add(str(uid))
                created += 1
                print(f"[{r}] created guest {uid}")
            else:
                print(f"[{r}] register attempt failed or duplicate, retrying...")
        bank[r] = gl

    with open(bank_path, "w") as f:
        json.dump(bank, f, indent=4)
    print(f"Saved {len(bank.get('IND', []))} IND guests to GuestAccounts.json")


if __name__ == "__main__":
    main()
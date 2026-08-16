import hashlib, hmac, random, requests, sys
from urllib.parse import urlencode
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
sys.path.insert(0, "/workspaces/EgoX/LevelUpBot")
from Pb2.MajoRLoGinrEq_pb2 import MajorLogin

SECRET = b"2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"
CID = "100067"
UA = "GarenaMSDK/4.0.19P9(A063 ;Android 13;en;IN;)"

def register_guest():
    pwd = str(random.randint(1000000000, 9999999999))
    ph = hashlib.sha256(pwd.encode()).hexdigest().upper()
    bd = urlencode({"password": ph, "client_type": "2", "source": "2", "app_id": CID})
    sig = hmac.new(SECRET, bd.encode(), hashlib.sha256).hexdigest()
    r = requests.post("https://connect.garena.com/oauth/guest/register", data=bd, timeout=10,
                      headers={"User-Agent": UA, "Authorization": f"Signature {sig}",
                               "Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200, f"register: {r.status_code} {r.text[:120]}"
    uid = r.json()["uid"]
    td = {"uid": str(uid), "password": ph, "response_type": "token", "client_type": "2",
          "client_secret": SECRET.decode(), "client_id": CID}
    r = requests.post("https://connect.garena.com/oauth/guest/token/grant", data=td, timeout=10,
                      headers={"User-Agent": UA})
    assert r.status_code == 200, f"grant: {r.status_code} {r.text[:120]}"
    j = r.json()
    at, oid = j["access_token"], j["open_id"]
    return uid, ph, at, oid

def build_full_payload(open_id, access_token, nickname):
    m = MajorLogin()
    m.event_time = "2026-07-09 12:44:05"
    m.game_name = "free fire"
    m.platform_id = 1
    m.client_version = "1.126.9"
    m.system_software = "Android OS 13 / API-33 (TP1A.220905.001/R.206769c-2)"
    m.system_hardware = "Handheld"
    m.telecom_operator = "45403"
    m.network_type = "WIFI"
    m.screen_width = 1280
    m.screen_height = 720
    m.screen_dpi = "320"
    m.processor_details = "ARM64 FP ASIMD AES | 2352 | 8"
    m.memory = 128
    m.gpu_renderer = "Mali-G610"
    m.gpu_version = "OpenGL ES 3.2 v1.g18p0-01eac0.2d5e200a1514bdef1a4909db66e37e28"
    m.unique_device_id = "Google|7a9732a4-2549-4edc-840e-d61263d128f5"
    m.client_ip = "162.128.224.168"
    m.language = "en"
    m.open_id = open_id
    m.open_id_type = "4"
    m.device_type = "Handheld"
    m.device_model = "OPPO CPH2217"
    m.region = "IND"
    m.access_token = access_token
    m.platform_sdk_id = 1
    m.network_operator_a = "45403"
    m.network_type_a = "WIFI"
    m.client_using_version = "1ac4b80ecf0478a44203bf8fac6120f5"
    m.external_storage_total = 20660
    m.external_storage_available = 17445
    m.internal_storage_total = 2663
    m.internal_storage_available = 1500
    m.game_disk_storage_available = 17573
    m.game_disk_storage_total = 20660
    m.external_sdcard_avail_storage = 17573
    m.external_sdcard_total_storage = 20660
    m.login_by = 3
    m.library_path = "/data/app/~~xHaSHUdUBlxvhJaRWh018A==/com.dts.freefireth-4OBn7-sLMoPuswIfmgixhA==/lib/arm64"
    m.reg_avatar = 1
    m.library_token = "4c322aeb56444feaa151d1ea91a8f7f2|/data/app/~~xHaSHUdUBlxvhJaRWh018A==/com.dts.freefireth-4OBn7-sLMoPuswIfmgixhA==/base.apk"
    m.channel_type = 6
    m.cpu_type = 2
    m.cpu_architecture = "64"
    m.client_version_code = "2019120816"
    m.unknown_int85 = 3
    m.graphics_api = "OpenGLES2"
    m.supported_astc_bitset = 16383
    m.login_open_id_type = 4
    m.analytics_detail = b"FwQVTgUPX1UaUllDDwcWCRBpWA0FUgsvA1snWlBaO1kFYg=="
    m.loading_time = 25777
    m.release_channel = "3rd_party"
    m.extra_info = "KqsHTz+zAigQ0BOzKhQHN8ae/IefLXcroDjaj4QY+OF71nTuiQh+myDUqCZFPJQ5gyC9LfEeKoon9d461764VIGguRHcIyKfExGAh4bvxFZRgp2X"
    m.extra_json = '{"cur_rate":null,"support_etc2":false}'
    m.android_engine_init_flag = 110009
    m.if_push = 1
    m.is_vpn = 1
    m.origin_platform_type = "4"
    m.primary_platform_type = "4"
    m.unknown_bytes102 = b"E1JMTwcJXjA2"
    raw = m.SerializeToString()
    nb = nickname.encode()
    def vi(n):
        out = bytearray()
        while n > 0x7f:
            out.append((n & 0x7f) | 0x80)
            n >>= 7
        out.append(n)
        return bytes(out)
    raw += vi((34 << 3) | 2) + vi(len(nb)) + nb
    c = AES.new(b"Yg&tc%DEuh6%Zc^8", AES.MODE_CBC, b"6oyZDr22E3ychjM%")
    return c.encrypt(pad(raw, 16))

def main():
    uid, ph, at, oid = register_guest()
    print(f"[OK] registered garena guest uid={uid}")
    nick = f"0xMe{random.randint(1000,9999)}"
    payload = build_full_payload(oid, at, nick)
    headers = {"Authorization": f"Bearer {at}", "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1",
               "ReleaseVersion": "OB54", "Content-Type": "application/octet-stream",
               "Content-Length": str(len(payload)), "User-Agent": UA,
               "Host": "loginbp.ggblueshark.com", "Connection": "Keep-Alive", "Accept-Encoding": "gzip"}
    for name, url in [("MajorRegister", "https://loginbp.ggblueshark.com/MajorRegister"),
                      ("MajorLogin", "https://loginbp.ggblueshark.com/MajorLogin")]:
        r = requests.post(url, data=payload, headers=headers, timeout=15)
        print(f"[{name}] {r.status_code} {r.text[:150]}")
        if r.status_code == 200:
            print(f"*** {name} SUCCESS ***")
    print(f"GUEST: uid={uid} password={ph} raw={nick}")

if __name__ == "__main__":
    main()

# Guest ID Generation Research (post-OB54)

> STATUS: RESEARCH ONLY — NOT PUSHED. Do not push this folder to GitHub until a working method is confirmed.

## TL;DR (verified live 2026-08-15)

1. **`oauth/guest/register` still WORKS** — but only on `https://connect.garena.com` (base host).
   The newer hosts (`100067.connect.garena.com`, `ffmconnect.live.gop.garenanow.com`) return
   `404 {"code":1005,"error":"error_not_found"}`.
2. **`MajorRegister` (profile creation) is globally FORBIDDEN for guests in OB54**:
   `400 BR_GUEST_REGISTER_FORBIDDEN` — even with:
   - the exact in-game payload (decrypted from a real capture, see below),
   - tokens from fresh guests AND from an existing in-game-created guest (6603148404),
   - every region (IND/SG/PK/BR/ID/TH), both loginbp hosts (ggblueshark/ggpolarbear),
     both OB53 and OB54 ReleaseVersion, MSDK + Dalvik UAs, with/without Expect header.
3. **No auto-creation on first MajorLogin** → `404 account_not_found` for fresh guests.
4. **No register endpoint on the game servers** (`client.ind.freefiremobile.com` etc. → 503 no route).
5. No public repo has verified working HTTP guest registration in OB54:
   - `rifancorteza/ffapis` test suite (May 2026) passes 6/6 — register NOT included.
   - `spinzaf/freefire-api` (Feb 2026, OB53) mass-registers 110/region — predates OB54 block.
   - `kaifcodec/freefire-like-and-guest-api` — device-based (Frida), never HTTP register.

**Conclusion: in OB54, guest profiles can only be created on-device (in-game).**
HTTP-only guest generation is dead until Garena re-enables it. The working device paths:
- Frida capture (kaifcodec tooling, see `kaifcodec-frida/`) — hooks the in-game register.
- FFTool.apk extract / pm-clear (existing EgoX procedure).

## Working endpoints (for future re-testing)

### 1. Create Garena guest identity — WORKS
```
POST https://connect.garena.com/oauth/guest/register
User-Agent: GarenaMSDK/4.0.19P9(A063 ;Android 13;en;IN;)
Content-Type: application/x-www-form-urlencoded
Authorization: Signature <hmac_sha256_hex(SECRET, "password=..&client_type=2&source=2&app_id=100067")>
body: password=<sha256_hex_upper(10-digit random)>&client_type=2&source=2&app_id=100067
SECRET = 2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3
→ 200 {"uid": 6635xxxxxx}
```

### 2. Token grant — WORKS (all 3 hosts)
```
POST {host}/oauth/guest/token/grant
body: uid=..&password=..&response_type=token&client_type=2&client_secret=..&client_id=100067
→ 200 {uid, open_id, access_token, main_account_id, expiry...}
```

### 3. MajorRegister — FORBIDDEN for guests (OB54)
```
POST https://loginbp.ggblueshark.com/MajorRegister   (and ggpolarbear.com)
→ 400 BR_GUEST_REGISTER_FORBIDDEN
```

## The real in-game register message (decrypted from kaifcodec capture)

`dev/not_imp/rawhex.hex` in `kaifcodec-frida/` is a genuine captured request (AES-CBC
encrypted with MAIN_KEY/MAIN_IV). Decrypted protobuf:

```
field 1 : nickname        = "Fun0?6v8"     (string)
field 2 : access_token    = 64 hex chars   (string)
field 3 : open_id         = 32 hex chars   (string)
field 5 : avatar_id       = 102000007      (varint)
field 6 : platform_type   = 4              (varint, guest)
field 7 : platform_sdk_id = 1              (varint)
field 13: using_version   = 1              (varint, NORMAL)
field 14: register_info   = 32 bytes       (XOR-obfuscated open_id: b ^ k[i%32] ^ 48)
field 15: language        = "en"           (string — NOT region!)
field 16: unknown         = 2              (varint)
field 17: unknown         = 1              (varint)
```

The old OB50-era recipe used `15="IND" (region), 16=1` and no field 17 — wrong in the
current schema, but the correct payload still gets FORBIDDEN, so the block is not payload-driven.

## Files in this folder

| File | Purpose |
|---|---|
| `README.md` | this doc |
| `test_register.py` | one-shot re-test of oauth/guest/register on both hosts |
| `full_flow_test.py` | full register→grant→MajorRegister→MajorLogin (minimal payload) |
| `full_flow_v2.py` | full flow with complete device-info payloads |
| `ffapis/` | clone of rifancorteza/ffapis (TS reference) |
| `kaifcodec-frida/` | clone of kaifcodec/freefire-like-and-guest-api (Frida device capture + real capture hex) |
| `spinzaf/` | npm @spinzaf/freefire-api package (OB53 mass-register reference) |

## Re-test checklist (per OB update)

1. `python test_register.py` — if 200 on connect.garena.com, HTTP path alive again.
2. Try MajorRegister with the exact decrypted payload above + fresh token.
3. Watch for new repos: search "free fire guest register OB5x" / "MajorRegister 2026".

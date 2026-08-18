#!/usr/bin/env python3
"""EgoX Leveler — plays Free Fire to farm match EXP until a target level
(default 8). Two modes:

  --team-code CODE   Proven XP farm: joins the player's squad via team code,
                     presses ready, starts the match, stays in it, then leaves
                     and repeats. This is the flow the server actually accepts.

  --mode br|cs       Solo matchmaking (BR or Clash Squad) from the bot's own
                     squad. The server currently ignores solo matchmaking
                     packets, so this mode is kept for when the correct packet
                     is captured — it never spams and cannot harm the account.

Standalone program, separate from the main LevelUpBot. Reuses only the
login/packet primitives from the shared LevelUpBot library modules.

Usage:
    python3 solo_leveler.py --team-code 123456 --target-level 8
    python3 solo_leveler.py --uid <garena_uid> --password <sha256> --mode br
"""

import argparse
import asyncio
import json
import os
import random
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xDL import (
    GeneRaTePk,
    CrEaTe_ProTo,
    EnC_PacKeT,
    DeCode_PackEt,
    Emote_k,
    OpEnSq,
    GeT_Status,
)
from app import (
    GeNeRaTeAccEss,
    EncRypTMajoRLoGin,
    MajorLogin,
    GetLoginData,
    DecRypTMajoRLoGin,
    DecRypTLoGinDaTa,
    xAuThSTarTuP,
    Look_Changer,
    SEndMsG,
)
from Api.InGame import get_player_personal_show

DEFAULT_UID = "6699482175"
DEFAULT_PASSWORD = "A6CA1227517C66D058039C1FEB75691ADAE7431B5D84057A9D5817A0EFEF0479"

EMOTE_IDS = [909050008, 909035003, 909050008, 909035003]
BUNDLE_IDS = [
    914000002, 914000003, 914038001, 914039001, 914042001,
    914044001, 914047001, 914047002, 914048001, 914050001, 914051001,
]
CHAT_LINES = ["gg", "lets go", "fast", "ez", "wp", "gl hf", "nice", "br only", "anyone?", "no lag pls"]
BR_MODE_ID = 0
CS_MODE_ID = 15
MATCH_LOOKOUT = 150
BR_MATCH_STAY = (600, 1000)
CS_MATCH_STAY = (420, 700)
TEAM_MATCH_STAY = (600, 900)
TEAM_JOIN_TIMEOUT = 90
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solo_leveler.log")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def rnd(lo, hi):
    return random.uniform(lo, hi)


class SoloLeveler:
    def __init__(self, uid, password, mode, mode_id, target_level, max_matches, region_hint, team_code):
        self.uid = uid
        self.password = password
        self.mode = mode
        self.mode_id = mode_id
        self.target_level = target_level
        self.max_matches = max_matches
        self.region_hint = region_hint
        self.team_code = team_code

        self.account_uid = None
        self.token = None
        self.server_url = None
        self.region = None
        self.key = None
        self.iv = None
        self.online_ip = None
        self.online_port = None
        self.auth_frame = None

        self.level = None
        self.exp = None
        self.matches_played = 0
        self.running = True
        self.in_match = False
        self.online_writer = None
        self.connected = False
        self.match_started = asyncio.Event()
        self.match_info = None
        self.battle_task = None
        self.join_confirmed = asyncio.Event()
        self.squad_codes = []
        self.squad_owner = None
        self.last_squad_code = None
        self.conn_gen = 0
        self.invite_event = asyncio.Event()
        self.invite = None
        self.debug_pkts = False

    async def login(self):
        log(f"🔑 Logging in account {self.uid} ...")
        open_id, access_token = await GeNeRaTeAccEss(self.uid, self.password)
        if not open_id:
            log("❌ Garena token grant failed")
            return False
        payload = await EncRypTMajoRLoGin(open_id, access_token)
        resp = await MajorLogin(payload)
        if not resp:
            log("❌ MajorLogin failed")
            return False
        proto = await DecRypTMajoRLoGin(resp)
        if not proto.account_uid:
            log("❌ MajorLogin returned no account_uid")
            return False
        self.account_uid = int(proto.account_uid)
        self.region = (self.region_hint or proto.region or "IND").upper()
        self.token = proto.token
        self.server_url = proto.url
        self.key = proto.key
        self.iv = proto.iv

        login_data = await GetLoginData(self.server_url, payload, self.token)
        if not login_data:
            log("❌ GetLoginData failed")
            return False
        ports = await DecRypTLoGinDaTa(login_data)
        self.online_ip, self.online_port = ports.Online_IP_Port.split(":")
        self.auth_frame = await xAuThSTarTuP(self.account_uid, self.token, int(proto.timestamp), self.key, self.iv)
        log(f"✅ Logged in as {self.account_uid} ({self.region}) · online {self.online_ip}:{self.online_port}")
        return True

    async def read_level(self):
        try:
            info = await asyncio.to_thread(
                get_player_personal_show, self.server_url, self.token, self.account_uid
            )
            basic = info.get("basicinfo") or {}
            self.level = basic.get("level", self.level)
            self.exp = basic.get("exp", self.exp)
            return True
        except Exception as e:
            log(f"⚠️ level poll failed: {str(e)[:80]}")
            return False

    async def connect_online(self):
        for attempt in range(3):
            try:
                reader, writer = await asyncio.open_connection(self.online_ip, int(self.online_port))
                self.online_writer = writer
                self.connected = True
                log(f"🟢 ONLINE connected ({self.online_ip}:{self.online_port})")
                return reader
            except Exception as e:
                log(f"⚠️ online connect attempt {attempt + 1} failed: {str(e)[:80]}")
                await asyncio.sleep(2)
        return None

    async def run_online(self):
        backoff = 2
        while self.running:
            self.connected = False
            self.online_writer = None
            t0 = time.time()
            reader = await self.connect_online()
            if not reader:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            try:
                self.online_writer.write(bytes.fromhex(self.auth_frame))
                await self.online_writer.drain()
            except Exception:
                pass
            reader_task = asyncio.create_task(self.read_online(reader))
            self.conn_gen += 1
            try:
                await reader_task
            except asyncio.CancelledError:
                break
            uptime = time.time() - t0
            if uptime < 10:
                backoff = min(backoff * 2, 60)
            else:
                backoff = 2
            log(f"🔌 ONLINE connection lost after {int(uptime)}s — reconnecting in {backoff}s ...")
            await asyncio.sleep(backoff)

    async def keepalive_loop(self):
        while self.running:
            await asyncio.sleep(rnd(10, 16))
            if self.connected and not self.in_match:
                await self.send(await GeT_Status(self.account_uid, self.key, self.iv))

    async def send(self, packet):
        if not self.connected or not self.online_writer:
            return False
        try:
            self.online_writer.write(packet)
            await self.online_writer.drain()
            return True
        except Exception as e:
            log(f"⚠️ send failed: {str(e)[:60]}")
            self.connected = False
            return False

    async def wait_online(self, timeout=30):
        deadline = time.time() + timeout
        while self.running and time.time() < deadline:
            if self.connected:
                return True
            await asyncio.sleep(1)
        return self.connected

    async def squad_packet(self, fields):
        if self.region == "IND":
            ptype = "0514"
        elif self.region == "BD":
            ptype = "0519"
        else:
            ptype = "0515"
        return await GeneRaTePk((await CrEaTe_ProTo(fields)).hex(), ptype, self.key, self.iv)

    async def leave_squad(self):
        return await self.squad_packet({1: 7, 2: {1: self.account_uid}})

    async def open_own_squad(self):
        return await OpEnSq(self.key, self.iv, self.region)

    async def join_teamcode_packet(self):
        return await self.join_code_packet(str(self.team_code))

    async def join_code_packet(self, code):
        return await self.squad_packet({
            1: 4,
            2: {
                4: bytes.fromhex("01090a0b121920"),
                5: str(code),
                6: 6,
                8: 1,
                9: {2: 800, 6: 11, 8: "1.111.1", 9: 5, 10: 1},
            },
        })

    async def join_code_packet_0515(self, code):
        return await GeneRaTePk((await CrEaTe_ProTo({
            1: 4,
            2: {
                4: bytes.fromhex("01090a0b121920"),
                5: str(code),
                6: 6,
                8: 1,
                9: {2: 800, 6: 11, 8: "1.111.1", 9: 5, 10: 1},
            },
        })).hex(), "0515", self.key, self.iv)

    async def join_invite_style_packet(self, code):
        return await self.squad_packet({
            1: 4,
            2: {
                1: int(self.squad_owner or self.account_uid),
                3: int(self.squad_owner or self.account_uid),
                8: 1,
                9: {2: 161, 4: "y[WW", 6: 11, 8: "1.114.18", 9: 3, 10: 1},
                10: str(code),
            },
        })

    async def ready_squad_packet(self):
        return await self.squad_packet({
            1: 5,
            2: {1: int(self.squad_owner or self.account_uid), 2: 1, 3: int(self.account_uid), 4: ""},
        })

    async def start_squad_packet(self):
        return await self.squad_packet({1: 9, 2: {1: int(self.squad_owner or self.account_uid)}})

    async def matchmaking_requests(self):
        base = {1: self.account_uid}
        variants = [
            {1: 9, 2: dict(base)},
            {1: 9, 2: {**base, 2: self.mode_id}},
            {1: 9, 2: {**base, 2: self.mode_id, 3: self.region}},
            {1: 9, 2: {**base, 2: self.mode_id, 3: 0, 4: "en", 6: 1}},
        ]
        packets = []
        for v in variants:
            packets.append(await self.squad_packet(v))
        return packets

    async def read_online(self, reader):
        while self.running:
            try:
                data = await reader.read(9999)
                if not data:
                    log("🔌 ONLINE connection closed by server")
                    break
                await self.handle_packet(data.hex())
            except asyncio.CancelledError:
                break
            except Exception as e:
                log(f"⚠️ online read error: {str(e)[:60]}")
                break

    async def handle_packet(self, hex_data):
        if len(hex_data) <= 30:
            return
        try:
            pkt = await DeCode_PackEt(hex_data[10:])
            j = json.loads(pkt)
        except Exception:
            return
        p5 = j.get("5", {})
        if not isinstance(p5, dict):
            return
        d5 = p5.get("data")
        if not isinstance(d5, dict):
            return
        if self.debug_pkts:
            try:
                t = j.get("4", {}).get("data") if isinstance(j.get("4"), dict) else j.get("4")
                log(f"🔎 pkt type={t} f5keys={list(d5.keys())}")
                if t in (3, 17, 2) or "8" in d5:
                    log(f"🔎 full d5: {json.dumps(d5)}")
            except Exception:
                pass
        f2 = d5.get("2", {}).get("data")
        f4 = d5.get("4", {}).get("data")
        if isinstance(f2, str) and ":" in f2 and isinstance(f4, str) and f4.startswith("eyJ"):
            self.match_info = {
                "ip": f2.rsplit(":", 1)[0],
                "port": f2.rsplit(":", 1)[1],
                "match_key": d5.get("3", {}).get("data"),
                "token": f4,
                "room": d5.get("1", {}).get("data", 0),
            }
            log(f"🎮 MATCH START DETECTED -> {f2}")
            self.match_started.set()
        owner = d5.get("1", {}).get("data") if isinstance(d5.get("1"), dict) else None
        chat_code = d5.get("17", {}).get("data") if isinstance(d5.get("17"), dict) else None
        squad_code = d5.get("31", {}).get("data") if isinstance(d5.get("31"), dict) else None
        if owner is not None and chat_code is not None and squad_code is not None:
            if self.squad_owner != int(owner):
                log(f"✅ Squad data received (owner {owner}, code {squad_code})")
            self.squad_owner = int(owner)
            self.last_squad_code = str(squad_code)
            self.join_confirmed.set()
            for f in ("14", "31", "33"):
                v = d5.get(f, {}).get("data") if isinstance(d5.get(f), dict) else None
                if v and str(v) not in self.squad_codes:
                    self.squad_codes.append(str(v))
        inviter = owner if isinstance(owner, int) else None
        if inviter is not None and inviter != self.account_uid and not self.join_confirmed.is_set():
            f2n = d5.get("2")
            if isinstance(f2n, dict) and isinstance(f2n.get("data"), dict):
                nested = f2n.get("data")
                if isinstance(nested.get("1"), dict):
                    raw_code = d5.get("8")
                    code = raw_code.get("data") if isinstance(raw_code, dict) else raw_code
                    if code:
                        self.invite = (inviter, str(code))
                        log(f"📩 INVITE received from {inviter} (code {code})")
                        self.invite_event.set()

    async def human_lobby_antics(self):
        if random.random() < 0.55:
            await self.send(await Emote_k(self.account_uid, random.choice(EMOTE_IDS), self.key, self.iv, self.region))
            await asyncio.sleep(rnd(1.5, 4))
        if random.random() < 0.25:
            await self.send(await Look_Changer(random.choice(BUNDLE_IDS), self.key, self.iv, self.region))
            await asyncio.sleep(rnd(1, 3))
        if random.random() < 0.4:
            try:
                msg = await SEndMsG(0, random.choice(CHAT_LINES), self.account_uid, self.account_uid, self.key, self.iv)
                await self.send(msg)
                await asyncio.sleep(rnd(0.8, 2.5))
            except Exception:
                pass

    async def matchmaking_cycle(self):
        self.in_match = False
        self.match_info = None
        await self.wait_online()
        await asyncio.sleep(rnd(3, 7))
        await self.send(await self.leave_squad())
        await asyncio.sleep(rnd(1.5, 3.5))
        await self.send(await self.open_own_squad())
        log("🎯 Own squad opened — searching solo match ...")
        await asyncio.sleep(rnd(2, 5))
        await self.human_lobby_antics()

        start_packets = await self.matchmaking_requests()
        for i, pkt in enumerate(start_packets):
            self.match_started.clear()
            await self.send(pkt)
            log(f"🔍 solo {self.mode.upper()} request v{i + 1} sent — waiting up to {MATCH_LOOKOUT}s ...")
            try:
                await asyncio.wait_for(self.match_started.wait(), timeout=MATCH_LOOKOUT)
                log("🎮 Match found!")
                return True
            except asyncio.TimeoutError:
                await self.human_lobby_antics()
        log("⏳ No match in this cycle (server may ignore solo start) — requeueing ...")
        return False

    async def teamcode_cycle(self):
        self.join_confirmed.clear()
        self.squad_owner = None
        join_packet = await self.join_teamcode_packet()
        await self.send(join_packet)
        log(f"🎯 Joining team {self.team_code} ...")
        wait = 0
        while not self.join_confirmed.is_set() and self.running:
            await asyncio.sleep(2)
            wait += 2
            if wait % 8 == 0:
                await self.send(join_packet)
            if wait >= TEAM_JOIN_TIMEOUT:
                log(f"⚠️ Join not confirmed after {wait}s (match in progress?) — retrying next cycle")
                return
        if not self.join_confirmed.is_set():
            return
        log(f"✅ Joined team {self.team_code} (owner {self.squad_owner}) — ready & starting ...")
        await asyncio.sleep(rnd(2, 4))

        ready_packet = await self.ready_squad_packet()
        start_packet = await self.start_squad_packet()
        for _ in range(40):
            if not self.connected or not self.running:
                return
            await self.send(ready_packet)
            await asyncio.sleep(rnd(0.4, 0.8))
            await self.send(start_packet)
            await asyncio.sleep(rnd(0.5, 1.0))

        stay = rnd(*TEAM_MATCH_STAY)
        log(f"⏱️ Match started — staying in match ~{int(stay)}s (EXP is counted while connected) ...")
        waited = 0
        while waited < stay and self.running and self.connected:
            await asyncio.sleep(30)
            waited += 30
        await self.send(await self.leave_squad())
        self.join_confirmed.clear()
        self.matches_played += 1
        await self.read_level()
        log(f"🚪 Left team — cycle done ({self.matches_played} cycles · level {self.level} · exp {self.exp})")
        await asyncio.sleep(rnd(4, 8))

    async def battle_session(self):
        info = self.match_info
        self.in_match = True
        self.matches_played += 1
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        loop = asyncio.get_event_loop()
        match_ip, match_port = info["ip"], int(info["port"])

        async def frame_token(hex_token, enc_key, enc_iv):
            uid_hex = hex(self.account_uid)[2:]
            headers = {"9": "0000000", "8": "00000000", "10": "000000", "7": "000000000"}.get(str(len(uid_hex)), "0000000")
            ts = hex(int(time.time()))[2:]
            enc_ts = await EnC_PacKeT(ts, enc_key, enc_iv)
            payload = await EnC_PacKeT(hex_token, enc_key, enc_iv)
            header = f"0115{headers}{uid_hex}{enc_ts}00000{hex(len(payload) // 2)[2:]}"
            if len(header) % 2:
                header = header[:4] + "0" + header[4:]
            return bytes.fromhex(header + payload)

        def pb_wrap(token):
            tb = token.encode()
            n = len(tb)
            v = b""
            while True:
                b7 = n & 0x7F
                n >>= 7
                if n:
                    v += bytes([b7 | 0x80])
                else:
                    v += bytes([b7])
                    break
            return b"\x0a" + v + tb

        def kcp(cmd, payload=b"", conv=0):
            hdr = struct.pack("<IBBHIIII", conv, cmd, 0, 512, 0, 0, 0, len(payload))
            return hdr + payload

        room_id = info.get("room") if isinstance(info.get("room"), int) else 0
        match_key = info.get("match_key")
        variants = [
            ("raw JWT", info["token"].encode("utf-8")),
            ("4B len + JWT", len(info["token"]).to_bytes(4, "big") + info["token"].encode("utf-8")),
            ("frame login key/iv", await frame_token(info["token"].encode().hex(), self.key, self.iv)),
            ("frame match_key+login iv", await frame_token(info["token"].encode().hex(), bytes.fromhex(match_key), self.iv)),
            ("frame match_key+match_key", await frame_token(info["token"].encode().hex(), bytes.fromhex(match_key), bytes.fromhex(match_key))),
            ("enc raw match_key+loginiv", bytes.fromhex(await EnC_PacKeT(info["token"].encode().hex(), bytes.fromhex(match_key), self.iv))),
            ("enc raw match_key+match_key", bytes.fromhex(await EnC_PacKeT(info["token"].encode().hex(), bytes.fromhex(match_key), bytes.fromhex(match_key)))),
            ("ch05+len+enc match_key+match_key", b"\x05" + (len(info["token"]) + 16).to_bytes(4, "big") + bytes.fromhex(await EnC_PacKeT(info["token"].encode().hex(), bytes.fromhex(match_key), bytes.fromhex(match_key)))),
            ("pb{1:JWT} raw", pb_wrap(info["token"])),
            ("frame pb{1:JWT} match_key+match_key", await frame_token(pb_wrap(info["token"]).hex(), bytes.fromhex(match_key), bytes.fromhex(match_key))),
            ("frame pb{1:JWT} match_key+loginiv", await frame_token(pb_wrap(info["token"]).hex(), bytes.fromhex(match_key), self.iv)),
            ("frame pb{1:JWT} login key/iv", await frame_token(pb_wrap(info["token"]).hex(), self.key, self.iv)),
            ("enc pb{1:JWT} match_key+match_key", bytes.fromhex(await EnC_PacKeT(pb_wrap(info["token"]).hex(), bytes.fromhex(match_key), bytes.fromhex(match_key)))),
            ("KCP ASK", kcp(0x81)),
            ("KCP ASK conv=room", kcp(0x81, conv=room_id & 0xFFFFFFFF)),
            ("KCP PUSH JWT", kcp(0x83, info["token"].encode())),
            ("KCP PUSH JWT conv=room", kcp(0x83, info["token"].encode(), room_id & 0xFFFFFFFF)),
            ("KCP PUSH pbJWT", kcp(0x83, pb_wrap(info["token"]))),
            ("KCP PUSH pbJWT conv=room", kcp(0x83, pb_wrap(info["token"]), room_id & 0xFFFFFFFF)),
            ("KCP PUSH encJWT(mk,mk)", kcp(0x83, bytes.fromhex(await EnC_PacKeT(info["token"].encode().hex(), bytes.fromhex(match_key), bytes.fromhex(match_key))))),
            ("KCP PUSH encJWT conv=room", kcp(0x83, bytes.fromhex(await EnC_PacKeT(info["token"].encode().hex(), bytes.fromhex(match_key), bytes.fromhex(match_key))), room_id & 0xFFFFFFFF)),
        ]

        winner = None
        for name, pkt in variants:
            try:
                await loop.sock_sendto(sock, pkt, (match_ip, match_port))
            except Exception:
                continue
            try:
                data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 9999), timeout=3)
                log(f"✅ BATTLE SERVER REPLIED to '{name}' ({len(data)} bytes)")
                winner = (name, pkt)
                break
            except asyncio.TimeoutError:
                continue
        if not winner:
            log("⚠️ No battle auth variant answered — staying with heartbeat anyway")

        stay = rnd(*BR_MATCH_STAY if self.mode == "br" else CS_MATCH_STAY)
        deadline = time.time() + stay
        last_beat = time.time()
        last_reauth = time.time()
        last_rx = time.time()
        log(f"⏱️ In battle connection ~{int(stay)}s")
        try:
            while self.running and time.time() < deadline:
                try:
                    data, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 9999), timeout=6)
                    last_rx = time.time()
                except asyncio.TimeoutError:
                    if time.time() - last_rx > 90:
                        log("🔇 Battle server silent for 90s — leaving match")
                        break
                    if time.time() - last_beat > rnd(4, 8):
                        await loop.sock_sendto(sock, bytes.fromhex("0500000003"), (match_ip, match_port))
                        last_beat = time.time()
                    if winner and time.time() - last_reauth > 120:
                        await loop.sock_sendto(sock, winner[1], (match_ip, match_port))
                        log("🔁 Battle re-auth sent")
                        last_reauth = time.time()
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
        await self.read_level()
        log(f"🎮 Battle session over — level {self.level}, exp {self.exp}")

    async def level_monitor(self):
        while self.running:
            await asyncio.sleep(60)
            await self.read_level()
            if self.level is not None and self.level >= self.target_level:
                log(f"🏁 TARGET REACHED: level {self.level} (>= {self.target_level}) — stopping")
                self.running = False

    async def run(self):
        if not await self.login():
            return 1
        if not await self.read_level():
            log("❌ Could not read current level")
            return 1
        log(f"📊 Current: level {self.level}, exp {self.exp} — target level {self.target_level}")
        if self.level is not None and self.level >= self.target_level:
            log("🏁 Already at target level — nothing to do")
            return 0

        asyncio.create_task(self.run_online())
        asyncio.create_task(self.level_monitor())
        asyncio.create_task(self.keepalive_loop())
        await self.wait_online(timeout=20)

        try:
            while self.running:
                if self.max_matches and self.matches_played >= self.max_matches:
                    log("🏁 Max matches reached")
                    break
                if self.team_code:
                    await self.teamcode_cycle()
                else:
                    found = await self.matchmaking_cycle()
                    if not found:
                        await asyncio.sleep(rnd(30, 60))
                        continue
                    self.battle_task = asyncio.create_task(self.battle_session())
                    await self.battle_task
                    self.in_match = False
                    await asyncio.sleep(rnd(4, 8))
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            log("⏹️ Interrupted")
        finally:
            self.running = False
            if self.online_writer:
                try:
                    self.online_writer.close()
                except Exception:
                    pass
        log(f"📋 Summary: {self.matches_played} matches/cycles · level {self.level} · exp {self.exp}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="EgoX Leveler — Free Fire XP farm to target level")
    parser.add_argument("--uid", default=DEFAULT_UID, help="Garena UID")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Garena password (sha256 hex)")
    parser.add_argument("--team-code", default=None, help="Join this team code for the proven XP farm (recommended)")
    parser.add_argument("--mode", choices=["br", "cs"], default="br", help="Solo matchmaking mode (default br)")
    parser.add_argument("--mode-id", type=int, default=None, help="Override server game mode id (br=0, cs=15)")
    parser.add_argument("--target-level", type=int, default=8, help="Stop once this level is reached (default 8)")
    parser.add_argument("--max-matches", type=int, default=0, help="Stop after N matches (0 = unlimited)")
    parser.add_argument("--region", default=None, help="Region override (default from login)")
    args = parser.parse_args()
    mode_id = args.mode_id if args.mode_id is not None else (BR_MODE_ID if args.mode == "br" else CS_MODE_ID)
    leveler = SoloLeveler(args.uid, args.password, args.mode, mode_id, args.target_level, args.max_matches, args.region, args.team_code)
    try:
        sys.exit(asyncio.run(leveler.run()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()

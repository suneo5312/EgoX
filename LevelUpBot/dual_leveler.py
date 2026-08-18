#!/usr/bin/env python3
"""EgoX Dual Leveler — two accounts level up together:
  HOST  opens its own squad lobby and holds it open (keepalive + re-open).
  BOT   joins the host's team code, presses ready, starts the match (the
        flow the server accepts), stays in the match, leaves, repeats.

Both accounts are in the same squad, so both get pulled into every match and
both earn match EXP until they reach the target level (default 8).

Standalone program, separate from the main LevelUpBot. Reuses SoloLeveler
from solo_leveler.py for login/connection/packet machinery.

Usage:
    python3 dual_leveler.py --target-level 8
    python3 dual_leveler.py --host-uid ... --host-password ... --bot-uid ...
"""

import argparse
import asyncio
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solo_leveler import SoloLeveler, log, rnd, DEFAULT_UID, DEFAULT_PASSWORD
from xDL import SEnd_InV
from app import RedZed_SendInv, RejectMSGtaxt, ArohiAccepted

HOST_UID = "6603148404"
HOST_PASSWORD = "86BAC99AD9F4F25500B7AFA448A66A24B9935A9A2A41A81D25C31432F347CD40"

TEAM_JOIN_TIMEOUT = 90
MATCH_STAY = (600, 900)
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dual_leveler.log")


def dlog(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


class DualLeveler:
    def __init__(self, host_uid, host_password, bot_uid, bot_password, target_level, max_matches):
        self.target_level = target_level
        self.max_matches = max_matches
        self.running = True
        self.host = SoloLeveler(host_uid, host_password, "br", 0, target_level, 0, None, None)
        self.bot = SoloLeveler(bot_uid, bot_password, "br", 0, target_level, 0, None, None)
        self.bot.debug_pkts = True
        self.host.debug_pkts = False
        self.host_code = None
        self.host_code_event = asyncio.Event()

    async def login_all(self):
        dlog(f"🔑 Host   login: {self.host.uid}")
        if not await self.host.login():
            return False
        dlog(f"🔑 Bot    login: {self.bot.uid}")
        if not await self.bot.login():
            return False
        await self.host.read_level()
        await self.bot.read_level()
        dlog(f"📊 Host {self.host.account_uid}: level {self.host.level}, exp {self.host.exp}")
        dlog(f"📊 Bot  {self.bot.account_uid}: level {self.bot.level}, exp {self.bot.exp}")
        return True

    async def host_squad_loop(self):
        dlog("🏠 Host: opening squad lobby ...")
        while self.running:
            try:
                await self.host.wait_online()
                self.host.join_confirmed.clear()
                self.host.squad_owner = None
                await self.host.send(await self.host.leave_squad())
                await asyncio.sleep(rnd(1, 2.5))
                await self.host.send(await self.host.open_own_squad())
                deadline = time.time() + 30
                while time.time() < deadline and self.running and not self.host.join_confirmed.is_set():
                    await asyncio.sleep(2)
                    await self.host.send(await self.host.open_own_squad())
                if not self.host.join_confirmed.is_set():
                    dlog("⚠️ Host: squad not confirmed within 30s — retrying ...")
                    await asyncio.sleep(3)
                    continue
                self.host_code = str(self.host.last_squad_code)
                self.host_code_event.set()
                dlog(f"🏠 Host: team code = {self.host_code}")
                hold_until = time.time() + 120
                while self.running and time.time() < hold_until:
                    await asyncio.sleep(rnd(8, 12))
                    await self.host.send(await self.host.open_own_squad())
                    await self.host.send(await SEnd_InV(5, int(self.bot.account_uid), self.host.key, self.host.iv, self.host.region))
                    dlog(f"📨 Host: invite sent to bot ({self.bot.account_uid})")
                    if self.host.match_started.is_set():
                        dlog("🎮 Host: match start detected — host is in the match too")
                        self.host.match_started.clear()
                        try:
                            await self.host.battle_session()
                        except Exception as e:
                            dlog(f"⚠️ Host battle session error: {str(e)[:80]}")
                        self.host.in_match = False
                        dlog("🏠 Host: back to lobby — reopening squad ...")
                        break
            except asyncio.CancelledError:
                break
            except Exception as e:
                dlog(f"⚠️ Host squad loop error: {str(e)[:80]}")
                await asyncio.sleep(5)

    async def bot_match_loop(self):
        while self.running:
            try:
                if self.max_matches and self.bot.matches_played >= self.max_matches:
                    dlog("🏁 Max matches reached")
                    self.running = False
                    break
                await self.host_code_event.wait()
                await self.bot.wait_online()
                if not self.bot.connected:
                    await asyncio.sleep(5)
                    continue
                await asyncio.sleep(rnd(2, 5))
                self.bot.invite_event.clear()
                self.bot.invite = None
                dlog("📩 Bot: waiting for host invite ...")
                try:
                    await asyncio.wait_for(self.bot.invite_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    dlog("⚠️ Bot: no invite within 60s — retrying next cycle")
                    self.host_code_event.clear()
                    await asyncio.sleep(rnd(5, 10))
                    continue
                if not self.bot.invite:
                    continue
                inviter, code = self.bot.invite
                codes = list(dict.fromkeys([str(code)] + [c for c in self.host.squad_codes if c]))
                self.bot.join_confirmed.clear()
                self.bot.squad_owner = None
                attempts = []
                for c in codes:
                    attempts.append((f"f5-0515/{c[-10:]}", lambda c=c: self.bot.join_code_packet_0515(c)))
                for c in codes:
                    attempts.append((f"f5-0514/{c[-10:]}", lambda c=c: self.bot.join_code_packet(c)))
                attempts.append(("arohi-0515", lambda: ArohiAccepted(int(inviter), str(code), self.bot.key, self.bot.iv)))
                single = True
                for label, factory in attempts:
                    if self.bot.join_confirmed.is_set():
                        break
                    dlog(f"✅ Bot: invite from {inviter} — sending {label} ...")
                    await self.bot.send(await factory())
                    await asyncio.sleep(rnd(0.5, 1.0))
                    if single:
                        break
                    wait = 0
                    while not self.bot.join_confirmed.is_set() and self.running and wait < 8:
                        await asyncio.sleep(2)
                        wait += 2
                if not self.bot.join_confirmed.is_set():
                    dlog("⚠️ Bot: join not confirmed after invite — retrying next cycle")
                    await asyncio.sleep(rnd(5, 10))
                    continue
                dlog(f"✅ Bot: joined squad of {self.bot.squad_owner} — ready & starting match ...")
                await asyncio.sleep(rnd(2, 4))
                ready_packet = await self.bot.ready_squad_packet()
                start_packet = await self.bot.start_squad_packet()
                for _ in range(40):
                    if not self.bot.connected or not self.running:
                        break
                    await self.bot.send(ready_packet)
                    await asyncio.sleep(rnd(0.4, 0.8))
                    await self.bot.send(start_packet)
                    await asyncio.sleep(rnd(0.5, 1.0))

                stay = rnd(*MATCH_STAY)
                dlog(f"⏱️ Match started — staying ~{int(stay)}s (EXP while connected) ...")
                if self.bot.match_started.is_set():
                    self.bot.match_started.clear()
                    try:
                        battle = asyncio.create_task(self.bot.battle_session())
                        await asyncio.sleep(stay)
                        battle.cancel()
                        await asyncio.sleep(1)
                    except Exception:
                        pass
                else:
                    waited = 0
                    while waited < stay and self.running and self.bot.connected:
                        await asyncio.sleep(30)
                        waited += 30
                await self.bot.send(await self.bot.leave_squad())
                self.bot.join_confirmed.clear()
                self.bot.matches_played += 1
                await self.bot.read_level()
                await self.host.read_level()
                dlog(f"🚪 Bot: left squad — cycle done ({self.bot.matches_played} cycles · "
                     f"bot L{self.bot.level}/E{self.bot.exp} · host L{self.host.level}/E{self.host.exp})")
                await asyncio.sleep(rnd(5, 10))
                self.host_code_event.clear()
            except asyncio.CancelledError:
                break
            except Exception as e:
                dlog(f"⚠️ Bot match loop error: {str(e)[:80]}")
                await asyncio.sleep(5)

    async def level_monitor(self):
        while self.running:
            await asyncio.sleep(60)
            await self.bot.read_level()
            await self.host.read_level()
            dlog(f"📈 Levels — bot {self.bot.level} (exp {self.bot.exp}) · host {self.host.level} (exp {self.host.exp})")
            if self.bot.level is not None and self.bot.level >= self.target_level:
                dlog(f"🏁 TARGET REACHED: bot level {self.bot.level} (>= {self.target_level}) — stopping")
                self.running = False

    async def run(self):
        if not await self.login_all():
            return 1
        if self.bot.level is not None and self.bot.level >= self.target_level:
            dlog("🏁 Bot already at target level — nothing to do")
            return 0

        asyncio.create_task(self.host.run_online())
        asyncio.create_task(self.bot.run_online())
        await self.host.wait_online(timeout=20)
        await self.bot.wait_online(timeout=20)
        asyncio.create_task(self.host.keepalive_loop())
        asyncio.create_task(self.bot.keepalive_loop())
        asyncio.create_task(self.host_squad_loop())
        asyncio.create_task(self.bot_match_loop())
        asyncio.create_task(self.level_monitor())

        try:
            while self.running:
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except KeyboardInterrupt:
            dlog("⏹️ Interrupted")
        finally:
            self.running = False
            for acc in (self.host, self.bot):
                if acc.online_writer:
                    try:
                        acc.online_writer.close()
                    except Exception:
                        pass
        dlog(f"📋 Summary — bot: {self.bot.matches_played} matches, level {self.bot.level}, exp {self.bot.exp} · "
             f"host: level {self.host.level}, exp {self.host.exp}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="EgoX Dual Leveler — host + bot accounts level up together")
    parser.add_argument("--host-uid", default=HOST_UID, help="Host account Garena UID")
    parser.add_argument("--host-password", default=HOST_PASSWORD, help="Host account password (sha256 hex)")
    parser.add_argument("--bot-uid", default=DEFAULT_UID, help="Bot account Garena UID")
    parser.add_argument("--bot-password", default=DEFAULT_PASSWORD, help="Bot account password (sha256 hex)")
    parser.add_argument("--target-level", type=int, default=8, help="Stop once the bot reaches this level (default 8)")
    parser.add_argument("--max-matches", type=int, default=0, help="Stop after N bot matches (0 = unlimited)")
    args = parser.parse_args()
    leveler = DualLeveler(args.host_uid, args.host_password, args.bot_uid, args.bot_password, args.target_level, args.max_matches)
    try:
        sys.exit(asyncio.run(leveler.run()))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
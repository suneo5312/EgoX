import asyncio
import json
import os
from datetime import datetime, timezone

import discord
import requests

from Utilities.until import load_accounts

API_BASE = os.environ.get("API_BASE", os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:5000"))
SERVERS = os.environ.get("SERVERS", "IND4").split(",")

FF_GOLD = 0xFFB300
FF_ORANGE = 0xFF6D00
FF_BLUE = 0x1E88E5

INTENTS = discord.Intents.default()
INTENTS.message_content = True


def ts_to_dt(value):
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def rel_time(value):
    dt = ts_to_dt(value)
    if not dt:
        return "Unknown"
    diff = datetime.now(timezone.utc) - dt
    secs = int(diff.total_seconds())
    if secs < 0:
        return "Just now"
    if secs < 3600:
        return f"{max(secs // 60, 1)}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def fmt_num(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 1000000:
        return f"{n / 1000000:.1f}M"
    if n >= 10000:
        return f"{n / 1000:.1f}K"
    return f"{n:,}"


def get_data(endpoint, params):
    try:
        r = requests.get(f"{API_BASE}/{endpoint}", params=params, timeout=45)
        if r.status_code != 200:
            return None, r.status_code
        return r.json(), r.status_code
    except requests.RequestException:
        return None, 0


def fetch(endpoint, uid, **extra):
    errors = []
    for server in SERVERS:
        params = {"server": server, "uid": uid}
        params.update(extra)
        data, code = get_data(endpoint, params)
        if data and code == 200:
            return data, None
        if isinstance(data, dict) and "error" in data:
            errors.append(f"{server}: {data.get('error')} ({data.get('code', '')})")
    return None, " | ".join(errors) if errors else f"All servers failed (HTTP {code})"


def profile_embed(uid, data):
    basic = data.get("basicinfo", {})
    social = data.get("socialinfo", {})
    clan = data.get("clanbasicinfo", {})
    pet = data.get("petinfo", {})

    nickname = basic.get("nickname", "Unknown")
    level = basic.get("level", 0)
    exp = basic.get("exp", 0)
    rank = basic.get("rank", 0)
    rp = basic.get("rankingpoints", 0)
    csrank = basic.get("csrank", 0)
    csrp = basic.get("csrankingpoints", 0)
    likes = basic.get("liked", 0)
    badges = basic.get("badgecnt", 0)
    region = basic.get("region", "??")

    title = basic.get("title", 0)

    embed = discord.Embed(
        title=f"🎮 {nickname}",
        description=f"*{social.get('signature', '')}*" if social.get("signature") else None,
        color=FF_GOLD,
    )
    embed.add_field(name="🔢 Level", value=f"**{level}**\n`{fmt_num(exp)} EXP`", inline=True)
    embed.add_field(name="🌍 Region", value=f"`{region}`", inline=True)
    embed.add_field(name="❣️ Likes", value=f"**{fmt_num(likes)}**", inline=True)

    embed.add_field(
        name="🏆 BR Rank",
        value=f"`#{rank}` · `{fmt_num(rp)} pts`" if rp else f"`#{rank}`",
        inline=True,
    )
    embed.add_field(
        name="🔫 CS Rank",
        value=f"`#{csrank}` · `{fmt_num(csrp)} pts`" if csrp else f"`#{csrank}`",
        inline=True,
    )
    embed.add_field(name="🛡️ Badges", value=f"**{badges}**", inline=True)

    if clan:
        embed.add_field(
            name="🏰 Clan",
            value=f"**{clan.get('clanname', 'N/A')}**\n`Lv{clan.get('clanlevel', 0)} · {clan.get('membernum', 0)}/{clan.get('capacity', 0)} members`",
            inline=True,
        )
    if pet:
        embed.add_field(
            name="🐾 Pet",
            value=f"`Pet #{pet.get('id', 0)}` · `Lv{pet.get('level', 0)}`",
            inline=True,
        )
    if title:
        embed.add_field(name="🎖️ Title", value=f"`{title}`", inline=True)

    embed.add_field(
        name="📅 Created",
        value=f"{ts_to_dt(basic.get('createat')).strftime('%d %b %Y') if ts_to_dt(basic.get('createat')) else 'Unknown'}",
        inline=True,
    )
    embed.add_field(
        name="⏰ Last Login",
        value=rel_time(basic.get("lastloginat")),
        inline=True,
    )
    embed.add_field(name="🔗 UID", value=f"`{uid}`", inline=True)

    embed.set_footer(
        text=f"Free Fire Info • Season {basic.get('seasonid', '?')} • Release {basic.get('releaseversion', '?')}"
    )
    embed.set_author(name="Free Fire Player Info", icon_url="https://cdn.discordapp.com/emojis/1043432218400104478.png")
    return embed


def br_stats_embed(uid, data):
    embed = discord.Embed(
        title="📊 BR Career Statistics",
        description=f"Battle Royale stats for player `{uid}`",
        color=FF_ORANGE,
    )
    for label, key in (("Solo", "solostats"), ("Duo", "duostats"), ("Squad", "quadstats")):
        s = data.get(key) or {}
        detail = s.get("detailedstats") or {}
        games = s.get("gamesplayed", 0) or 0
        wins = s.get("wins", 0) or 0
        kills = s.get("kills", 0) or 0
        deaths = detail.get("deaths", 0) or 0
        kd = f"{kills / deaths:.2f}" if deaths else "∞"
        embed.add_field(
            name=f"🎮 {label}",
            value=(
                f"**Games:** {fmt_num(games)}\n"
                f"**Wins:** {fmt_num(wins)} (`{(wins / games * 100):.1f}%`)\n"
                f"**Kills:** {fmt_num(kills)} · **KD:** {kd}\n"
                f"**HS Kills:** {fmt_num(detail.get('headshotKills', 0))}\n"
                f"**Damage:** {fmt_num(detail.get('damage', 0))}\n"
                f"**Best:** {fmt_num(detail.get('highestKills', 0))} kills"
            ),
            inline=True,
        )
    embed.set_footer(text=f"UID {uid} • CAREER mode")
    return embed


def cs_stats_embed(uid, data):
    s = data.get("csstats") or {}
    detail = s.get("detailedstats") or {}
    games = s.get("gamesplayed", 0) or 0
    wins = s.get("wins", 0) or 0
    kills = s.get("kills", 0) or 0
    deaths = detail.get("deaths", 0) or 0
    kd = f"{kills / deaths:.2f}" if deaths else "∞"
    embed = discord.Embed(
        title="🎯 CS Career Statistics",
        description=f"Clash Squad stats for player `{uid}`",
        color=FF_BLUE,
    )
    embed.add_field(
        name="🎮 Games",
        value=f"**{fmt_num(games)}**\nwins `{fmt_num(wins)}` (`{(wins / games * 100):.1f}%`)",
        inline=True,
    )
    embed.add_field(
        name="🔪 Kills",
        value=f"**{fmt_num(kills)}**\nKD `{kd}`",
        inline=True,
    )
    embed.add_field(
        name="💥 Damage",
        value=f"**{fmt_num(detail.get('damage', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="👑 MVP Count",
        value=f"**{fmt_num(detail.get('mvpCount', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="🎯 Headshots",
        value=f"**{fmt_num(detail.get('headShotKills', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="🤝 Assists",
        value=f"**{fmt_num(detail.get('assists', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="💀 Knockdowns",
        value=f"**{fmt_num(detail.get('knockDowns', 0))}**",
        inline=True,
    )
    embed.add_field(
        name="⚡ Multi-kills",
        value=f"Double `{fmt_num(detail.get('doubleKills', 0))}`\nTriple `{fmt_num(detail.get('tripleKills', 0))}`\nQuad `{fmt_num(detail.get('fourKills', 0))}`",
        inline=True,
    )
    embed.add_field(
        name="💫 Revivals",
        value=f"**{fmt_num(detail.get('revivals', 0))}**",
        inline=True,
    )
    embed.set_footer(text=f"UID {uid} • CAREER mode")
    return embed


def error_embed(title, message):
    return discord.Embed(title=f"❌ {title}", description=f"```{message}```", color=0xE53935)


from discord.ext import commands as _cmds

bot = _cmds.Bot(command_prefix="!", intents=INTENTS, help_command=None)


@bot.event
async def on_ready():
    print(f"[+] Logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"[+] Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"[!] Slash sync failed: {e}")


def parse_uid(arg):
    if not arg or not arg.strip().isdigit():
        return None
    return arg.strip()


@bot.command(name="ff", aliases=["player"])
async def ff(ctx, uid: str):
    """Show full Free Fire player info (profile + BR/CS stats)"""
    uid = parse_uid(uid)
    if not uid:
        await ctx.send(embed=error_embed("Invalid UID", "UID must be a numeric value."))
        return
    async with ctx.typing():
        profile, err = await asyncio.to_thread(fetch, "get_player_personal_show", uid)
        if not profile:
            await ctx.send(embed=error_embed("Player Not Found", err or "No data found."))
            return
        await ctx.send(embed=profile_embed(uid, profile))

        br, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode="br", matchmode="CAREER")
        if br:
            await ctx.send(embed=br_stats_embed(uid, br.get("data", br)))

        cs, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode="cs", matchmode="CAREER")
        if cs:
            await ctx.send(embed=cs_stats_embed(uid, cs.get("data", cs)))


@bot.command(name="profile")
async def profile(ctx, uid: str):
    """Show player profile (level, rank, clan, likes...)"""
    uid = parse_uid(uid)
    if not uid:
        await ctx.send(embed=error_embed("Invalid UID", "UID must be a numeric value."))
        return
    async with ctx.typing():
        data, err = await asyncio.to_thread(fetch, "get_player_personal_show", uid)
        if not data:
            await ctx.send(embed=error_embed("Player Not Found", err or "No data found."))
            return
        await ctx.send(embed=profile_embed(uid, data))


@bot.command(name="stats")
async def stats(ctx, uid: str, mode: str = "br"):
    """Show player stats. Mode: br (default) or cs"""
    uid = parse_uid(uid)
    if not uid:
        await ctx.send(embed=error_embed("Invalid UID", "UID must be a numeric value."))
        return
    mode = mode.lower()
    if mode not in ("br", "cs"):
        await ctx.send(embed=error_embed("Invalid Mode", "Mode must be `br` or `cs`."))
        return
    async with ctx.typing():
        data, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode=mode, matchmode="CAREER")
        if not data:
            await ctx.send(embed=error_embed("No Stats", err or "No data found."))
            return
        payload = data.get("data", data)
        embed = br_stats_embed(uid, payload) if mode == "br" else cs_stats_embed(uid, payload)
        await ctx.send(embed=embed)


@bot.command(name="help", aliases=["commands"])
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📖 Free Fire Info Bot — Commands",
        description="Get player profiles, BR and CS statistics for any Free Fire player.",
        color=FF_GOLD,
    )
    embed.add_field(name="`!ff <uid>`", value="Full player info — profile + BR + CS stats", inline=False)
    embed.add_field(name="`!profile <uid>`", value="Profile: level, ranks, clan, likes, pet", inline=False)
    embed.add_field(name="`!stats <uid> [br|cs]`", value="Stats: Battle Royale (default) or Clash Squad", inline=False)
    embed.set_footer(text="Example: !ff 10502299434")
    await ctx.send(embed=embed)


@bot.tree.command(name="ff", description="Full Free Fire player info (profile + BR/CS stats)")
async def slash_ff(interaction: discord.Interaction, uid: str):
    uid = parse_uid(uid)
    if not uid:
        await interaction.response.send_message(embed=error_embed("Invalid UID", "UID must be a numeric value."), ephemeral=True)
        return
    await interaction.response.defer()
    profile, err = await asyncio.to_thread(fetch, "get_player_personal_show", uid)
    if not profile:
        await interaction.followup.send(embed=error_embed("Player Not Found", err or "No data found."))
        return
    await interaction.followup.send(embed=profile_embed(uid, profile))
    br, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode="br", matchmode="CAREER")
    if br:
        await interaction.followup.send(embed=br_stats_embed(uid, br.get("data", br)))
    cs, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode="cs", matchmode="CAREER")
    if cs:
        await interaction.followup.send(embed=cs_stats_embed(uid, cs.get("data", cs)))


@bot.tree.command(name="profile", description="Show player profile (level, rank, clan, likes...)")
async def slash_profile(interaction: discord.Interaction, uid: str):
    uid = parse_uid(uid)
    if not uid:
        await interaction.response.send_message(embed=error_embed("Invalid UID", "UID must be a numeric value."), ephemeral=True)
        return
    await interaction.response.defer()
    data, err = await asyncio.to_thread(fetch, "get_player_personal_show", uid)
    if not data:
        await interaction.followup.send(embed=error_embed("Player Not Found", err or "No data found."))
        return
    await interaction.followup.send(embed=profile_embed(uid, data))


@bot.tree.command(name="stats", description="Show player stats (br or cs)")
async def slash_stats(interaction: discord.Interaction, uid: str, mode: str = "br"):
    uid = parse_uid(uid)
    mode = mode.lower()
    if not uid or mode not in ("br", "cs"):
        await interaction.response.send_message(
            embed=error_embed("Invalid Input", "UID must be numeric and mode must be `br` or `cs`."), ephemeral=True
        )
        return
    await interaction.response.defer()
    data, err = await asyncio.to_thread(fetch, "get_player_stats", uid, gamemode=mode, matchmode="CAREER")
    if not data:
        await interaction.followup.send(embed=error_embed("No Stats", err or "No data found."))
        return
    payload = data.get("data", data)
    embed = br_stats_embed(uid, payload) if mode == "br" else cs_stats_embed(uid, payload)
    await interaction.followup.send(embed=embed)


def run_bot():
    token = os.environ.get("FF_BOT_TOKEN")
    if not token:
        cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Configuration", "DiscordConfig.json")
        if os.path.exists(cfg):
            with open(cfg) as f:
                token = json.load(f).get("token", "")
    if not token:
        raise SystemExit("No bot token found (set FF_BOT_TOKEN or Configuration/DiscordConfig.json)")
    bot.run(token)


if __name__ == "__main__":
    run_bot()
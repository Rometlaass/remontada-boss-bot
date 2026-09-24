"""
Bot Discord pentru boss timers - Vrajitoarea si Dragonul.

VRAJITOAREA: respawn la fiecare 8 ore. Cineva cu rolul permis scrie
    //vrajitoarea 15:30
in orice canal (comanda functioneaza doar pentru cine are rolul din
ALLOWED_ROLE_NAME). Botul calculeaza urmatorul spawn (15:30 + 8h = 23:30)
si trimite un reminder in canalul de boss-uri cu 10 minute inainte.

DRAGONUL: spawneaza fix in fiecare zi la 22:00, in Tara de Foc. Nu are
nevoie de comanda - botul trimite singur reminder-ul zilnic cu 10 minute
inainte (21:50).

Timerele sunt salvate in timers.json, deci supravietuiesc la un restart
al botului (ex: cand Railway redeployeaza).
"""

import json
import os
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

# Fusul orar folosit pentru toate calculele de timp (Railway ruleaza pe UTC
# implicit, deci fara asta orele ar fi calculate gresit cu 2-3 ore diferenta).
TZ = ZoneInfo("Europe/Bucharest")

# ============================== CONFIGURARE ==============================
# Token-ul botului. Pe Railway il pui ca variabila de mediu DISCORD_TOKEN,
# nu il scrie niciodata direct in cod daca urci fisierul pe un loc public.
TOKEN = os.environ.get("DISCORD_TOKEN", "PUNE_TOKENUL_AICI_DOAR_LOCAL")

# Prefixul comenzii, ex: //vrajitoarea 15:30
PREFIX = "//"

# ID-ul canalului #boss-timers unde se trimit reminder-ele.
BOSS_CHANNEL_ID = 1552771562183069747

# Numele rolului care are voie sa seteze ora de spawn cu //vrajitoarea.
ALLOWED_ROLE_NAME = "PVP-ist"

# Numele rolului care e mentionat in reminder.
PING_ROLE_NAME = "remindere-bosi"

# Reguli Vrajitoarea
VRAJITOARE_INTERVAL = timedelta(hours=8)
VRAJITOARE_REMIND_BEFORE = timedelta(minutes=10)

# Reguli Dragonul (fix zilnic)
DRAGON_SPAWN_TIME = dtime(hour=1, minute=19)  # 22:00 in fiecare zi
DRAGON_REMIND_BEFORE = timedelta(minutes=10)
DRAGON_LOCATION = "Tara de Foc"

TIMERS_FILE = "timers.json"
# ===========================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


def load_timers() -> dict:
    if os.path.exists(TIMERS_FILE):
        with open(TIMERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_timers(data: dict) -> None:
    with open(TIMERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


timers = load_timers()
# Structura: { "vrajitoarea": {"next_spawn": "iso", "reminded": bool} }


def has_allowed_role():
    async def predicate(ctx: commands.Context) -> bool:
        if isinstance(ctx.author, discord.Member):
            return any(r.name == ALLOWED_ROLE_NAME for r in ctx.author.roles)
        return False
    return commands.check(predicate)


def get_ping_role(guild: discord.Guild):
    return discord.utils.get(guild.roles, name=PING_ROLE_NAME)


@bot.event
async def on_ready():
    print(f"Bot conectat ca {bot.user}")
    if not check_timers.is_running():
        check_timers.start()


@bot.command(name="vrajitoarea")
@has_allowed_role()
async def vrajitoarea(ctx: commands.Context, ora: str):
    """//vrajitoarea 15:30 -> seteaza ora de spawn curenta."""
    try:
        h, m = map(int, ora.split(":"))
        now = datetime.now(TZ)
        last_spawn = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if last_spawn > now:
            last_spawn -= timedelta(days=1)
    except ValueError:
        await ctx.send("Format gresit. Foloseste: //vrajitoarea 15:30")
        return

    next_spawn = last_spawn + VRAJITOARE_INTERVAL
    timers["vrajitoarea"] = {
        "next_spawn": next_spawn.isoformat(),
        "reminded": False,
    }
    save_timers(timers)

    await ctx.send(
        f"Vrajitoarea setata. Ultimul spawn: {last_spawn.strftime('%H:%M')} — "
        f"urmatorul spawn estimat: {next_spawn.strftime('%d/%m %H:%M')}."
    )


@vrajitoarea.error
async def vrajitoarea_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("Nu ai rolul necesar pentru comanda asta.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Foloseste: //vrajitoarea 15:30")


@tasks.loop(seconds=30)
async def check_timers():
    try:
        now = datetime.now(TZ)

        # --- Vrajitoarea ---
        v = timers.get("vrajitoarea")
        if v and not v.get("reminded", False):
            next_spawn = datetime.fromisoformat(v["next_spawn"])
            if next_spawn.tzinfo is None:
                # Date vechi, salvate inainte de fix-ul de fus orar - le ignoram.
                del timers["vrajitoarea"]
                save_timers(timers)
            else:
                remind_at = next_spawn - VRAJITOARE_REMIND_BEFORE
                if now >= remind_at:
                    await send_reminder(
                        f"Vrajitoarea respawneaza in ~{int(VRAJITOARE_REMIND_BEFORE.total_seconds() // 60)} minute "
                        f"(estimat {next_spawn.strftime('%H:%M')})."
                    )
                    v["reminded"] = True
                    save_timers(timers)

        # --- Dragonul (fix zilnic la 22:00) ---
        today_spawn = now.replace(
            hour=DRAGON_SPAWN_TIME.hour,
            minute=DRAGON_SPAWN_TIME.minute,
            second=0,
            microsecond=0,
        )
        remind_at = today_spawn - DRAGON_REMIND_BEFORE
        key = f"dragon-{now.strftime('%Y-%m-%d')}"
        if now >= remind_at and now < today_spawn and not timers.get(key):
            await send_reminder(
                f"Dragonul respawneaza in ~{int(DRAGON_REMIND_BEFORE.total_seconds() // 60)} minute "
                f"in {DRAGON_LOCATION} (ora {DRAGON_SPAWN_TIME.strftime('%H:%M')})."
            )
            timers[key] = True
            save_timers(timers)
    except Exception as e:
        print(f"Eroare in check_timers: {e}")


async def send_reminder(text: str):
    channel = bot.get_channel(BOSS_CHANNEL_ID)
    if channel is None:
        print("Nu gasesc canalul de boss-timers, verifica BOSS_CHANNEL_ID.")
        return
    role = get_ping_role(channel.guild)
    mention = role.mention if role else ""
    await channel.send(f"{mention} ⚠️ {text}")


if __name__ == "__main__":
    bot.run(TOKEN)

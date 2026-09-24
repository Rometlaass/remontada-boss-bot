import json
import os
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

# Fusul orar folosit pentru toate calculele de timp
TZ = ZoneInfo("Europe/Bucharest")

# ============================== CONFIGURARE ==============================
TOKEN = os.environ.get("DISCORD_TOKEN", "PUNE_TOKENUL_AICI_DOAR_LOCAL")
PREFIX = "//"

BOSS_CHANNEL_ID = 1552771562183069747
ALLOWED_ROLE_NAME = "PVP-ist"
PING_ROLE_NAME = "remindere-bosi"

# Reguli Vrajitoarea
VRAJITOARE_INTERVAL = timedelta(hours=8)
VRAJITOARE_REMIND_BEFORE = timedelta(minutes=10)

# Reguli Dragonul (fix zilnic) - CORECTAT LA 22:00
DRAGON_SPAWN_TIME = dtime(hour=22, minute=0)  
DRAGON_REMIND_BEFORE = timedelta(minutes=10)
DRAGON_LOCATION = "Tara de Foc"

# Pentru a nu pierde datele pe Railway la redeploy, trebuie sa creezi un 
# Shared Volume in panoul Railway si sa pui calea aici (ex: "/data/timers.json")
TIMERS_FILE = "timers.json"
# ===========================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


def load_timers() -> dict:
    if os.path.exists(TIMERS_FILE):
        try:
            with open(TIMERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_timers(data: dict) -> None:
    with open(TIMERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


timers = load_timers()


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
        
        # Daca ora introdusa e mai mare decat ora curenta, inseamna ca spawnul a fost ieri
        if last_spawn > now:
            last_spawn -= timedelta(days=1)
    except ValueError:
        await ctx.send("Format greșit. Folosește: //vrajitoarea 15:30")
        return

    next_spawn = last_spawn + VRAJITOARE_INTERVAL
    timers["vrajitoarea"] = {
        "next_spawn": next_spawn.isoformat(),
        "reminded": False,
    }
    save_timers(timers)

    await ctx.send(
        f"Vrăjitoarea setată. Ultimul spawn: {last_spawn.strftime('%H:%M')} — "
        f"următorul spawn estimat: {next_spawn.strftime('%d/%m %H:%M')}."
    )


@vrajitoarea.error
async def vrajitoarea_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("Nu ai rolul necesar pentru comanda asta.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Folosește: //vrajitoarea 15:30")


@bot.command(name="status")
@has_allowed_role()
async def bot_status(ctx: commands.Context):
    """Comanda de debug pentru a verifica starea timerelor."""
    now = datetime.now(TZ)
    v = timers.get("vrajitoarea")
    
    msg = f"🕒 **Ora internă a botului (România):** {now.strftime('%H:%M:%S')}\n"
    
    if v:
        next_sp = datetime.fromisoformat(v["next_spawn"])
        reminded = v.get("reminded", False)
        msg += f"🧙‍♀️ **Vrăjitoarea:** Așteptat la {next_sp.strftime('%H:%M')} (Reminded: {reminded})\n"
    else:
        msg += "🧙‍♀️ **Vrăjitoarea:** Niciun timer setat (sau datele au fost șterse).\n"
        
    await ctx.send(msg)


@tasks.loop(seconds=30)
async def check_timers():
    try:
        now = datetime.now(TZ)

        # --- Vrajitoarea ---
        v = timers.get("vrajitoarea")
        if v and not v.get("reminded", False):
            next_spawn = datetime.fromisoformat(v["next_spawn"])
            
            # Reparam fusul orar in loc sa stergem direct timerul
            if next_spawn.tzinfo is None:
                next_spawn = next_spawn.replace(tzinfo=TZ)
                
            remind_at = next_spawn - VRAJITOARE_REMIND_BEFORE
            if now >= remind_at:
                await send_reminder(
                    f"Vrăjitoarea respawnează în ~{int(VRAJITOARE_REMIND_BEFORE.total_seconds() // 60)} minute "
                    f"(estimat {next_spawn.strftime('%H:%M')})."
                )
                v["reminded"] = True
                save_timers(timers)

        # --- Dragonul (fix zilnic) ---
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
                f"Dragonul respawnează în ~{int(DRAGON_REMIND_BEFORE.total_seconds() // 60)} minute "
                f"în {DRAGON_LOCATION} (ora {DRAGON_SPAWN_TIME.strftime('%H:%M')})."
            )
            timers[key] = True
            save_timers(timers)
            
    except Exception as e:
        print(f"Eroare in check_timers: {e}")


async def send_reminder(text: str):
    channel = bot.get_channel(BOSS_CHANNEL_ID)
    if channel is None:
        print("Nu găsesc canalul de boss-timers, verifică BOSS_CHANNEL_ID.")
        return
    role = get_ping_role(channel.guild)
    mention = role.mention if role else ""
    await channel.send(f"{mention} ⚠️ {text}")


if __name__ == "__main__":
    bot.run(TOKEN)

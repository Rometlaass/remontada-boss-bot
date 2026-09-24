import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

# ============================== CONFIGURARE ==============================
TOKEN = os.environ.get("DISCORD_TOKEN", "PUNE_TOKENUL_AICI_DOAR_LOCAL")
PREFIX = "//"

BOSS_CHANNEL_ID = 1552771562183069747
ALLOWED_ROLE_NAME = "PVP-ist"
PING_ROLE_NAME = "remindere-bosi"

# Fusul orar pentru Romania
TZ = ZoneInfo("Europe/Bucharest")

# Timpi si intervale
VRAJITOARE_HOURS = 8
REMINDER_MINUTES = 10

DRAGON_HOUR = 22
DRAGON_MINUTE = 0
DRAGON_LOCATION = "Tara de Foc"

TIMERS_FILE = "timers.json"
# ===========================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

def load_timers() -> dict:
    if not os.path.exists(TIMERS_FILE):
        return {}
    try:
        with open(TIMERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
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

@bot.event
async def on_ready():
    print(f"✅ Bot conectat ca {bot.user}")
    if not check_timers.is_running():
        check_timers.start()

# --- COMANDA PENTRU A SETA VRAJITOAREA (DOAR CU ROL) ---
@bot.command(name="vrajitoarea")
@has_allowed_role()
async def vrajitoarea(ctx: commands.Context, ora: str):
    try:
        h, m = map(int, ora.split(":"))
        now = datetime.now(TZ)
        last_spawn = now.replace(hour=h, minute=m, second=0, microsecond=0)
        
        if last_spawn > now:
            last_spawn -= timedelta(days=1)
            
    except ValueError:
        await ctx.send("❌ Format greșit. Folosește: `//vrajitoarea 15:30`")
        return

    next_spawn = last_spawn + timedelta(hours=VRAJITOARE_HOURS)
    
    timers["vrajitoarea"] = {
        "spawn_ts": next_spawn.timestamp(),
        "reminded": False
    }
    save_timers(timers)

    await ctx.send(
        f"✅ **Vrăjitoarea setată.**\n"
        f"Ultimul spawn: `{last_spawn.strftime('%H:%M')}`\n"
        f"Următorul spawn estimat: `{next_spawn.strftime('%d/%m %H:%M')}`"
    )

@vrajitoarea.error
async def vrajitoarea_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ Nu ai rolul necesar pentru a seta ora.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Folosește: `//vrajitoarea 15:30`")


# --- COMANDA DE STATUS BOSI (PENTRU TOATA LUMEA) ---
@bot.command(name="bosi")
async def bosi_status(ctx: commands.Context):
    now = datetime.now(TZ)
    msg = f"📊 **Status Boși** (Ora curentă: `{now.strftime('%H:%M')}`)\n\n"
    
    # Calcul Dragon
    next_dragon = now.replace(hour=DRAGON_HOUR, minute=DRAGON_MINUTE, second=0, microsecond=0)
    if now >= next_dragon:
        next_dragon += timedelta(days=1)
    
    msg += f"🐉 **Dragonul:** `{next_dragon.strftime('%d/%m %H:%M')}` (în {DRAGON_LOCATION})\n"
    
    # Calcul Vrajitoare
    v = timers.get("vrajitoarea")
    if v:
        next_sp = datetime.fromtimestamp(v["spawn_ts"], tz=TZ)
        if now < next_sp:
            msg += f"🧙‍♀️ **Vrăjitoarea:** `{next_sp.strftime('%d/%m %H:%M')}`\n"
        else:
            msg += f"🧙‍♀️ **Vrăjitoarea:** Momentan nesetată (ultimul spawn a expirat la `{next_sp.strftime('%H:%M')}`).\n"
    else:
        msg += "🧙‍♀️ **Vrăjitoarea:** Nu este setată o oră.\n"
        
    await ctx.send(msg)


# --- LOOP VERIFICARE TIMERE ---
@tasks.loop(seconds=30)
async def check_timers():
    try:
        now = datetime.now(TZ)
        channel = bot.get_channel(BOSS_CHANNEL_ID)
        
        if not channel:
            return
            
        role = discord.utils.get(channel.guild.roles, name=PING_ROLE_NAME)
        mention = role.mention if role else ""

        # --- Vrajitoarea ---
        v = timers.get("vrajitoarea")
        if v and not v.get("reminded", False):
            next_spawn = datetime.fromtimestamp(v["spawn_ts"], tz=TZ)
            remind_at = next_spawn - timedelta(minutes=REMINDER_MINUTES)
            
            if now >= remind_at and now < next_spawn:
                await channel.send(f"{mention} ⚠️ Vrăjitoarea respawnează în ~{REMINDER_MINUTES} minute (estimat `{next_spawn.strftime('%H:%M')}`).")
                v["reminded"] = True
                save_timers(timers)
            elif now >= next_spawn:
                v["reminded"] = True
                save_timers(timers)

        # --- Dragonul ---
        today_dragon = now.replace(hour=DRAGON_HOUR, minute=DRAGON_MINUTE, second=0, microsecond=0)
        remind_at = today_dragon - timedelta(minutes=REMINDER_MINUTES)
        today_str = now.strftime("%Y-%m-%d")
        
        if now >= remind_at and now < today_dragon and timers.get("dragon_last_reminded") != today_str:
            await channel.send(f"{mention} ⚠️ Dragonul respawnează în ~{REMINDER_MINUTES} minute în {DRAGON_LOCATION} (ora `{today_dragon.strftime('%H:%M')}`).")
            timers["dragon_last_reminded"] = today_str
            save_timers(timers)

    except Exception as e:
        print(f"Eroare in bucla check_timers: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)

import asyncio, logging, os, re, sqlite3, time
from collections import defaultdict, deque
from datetime import datetime, timezone
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from house_ai import ask_ai

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DATABASE_PATH", "drhousebot.sqlite3")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN fehlt. Lege es als Umgebungsvariable fest.")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
bot = Bot(TOKEN)
dp = Dispatcher()
flood = defaultdict(deque)
spam_last = {}
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS groups(chat_id INTEGER PRIMARY KEY, title TEXT, owner_id INTEGER, rules TEXT DEFAULT '', anti_spam INTEGER DEFAULT 1, anti_flood INTEGER DEFAULT 1, link_filter INTEGER DEFAULT 0, welcome INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS operators(user_id INTEGER PRIMARY KEY, admin_room_id INTEGER UNIQUE, created_at TEXT);
CREATE TABLE IF NOT EXISTS users(chat_id INTEGER, user_id INTEGER, points INTEGER DEFAULT 0, style TEXT DEFAULT 'neutral', PRIMARY KEY(chat_id,user_id));
CREATE TABLE IF NOT EXISTS warnings(chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0, PRIMARY KEY(chat_id,user_id));
CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor INTEGER, chat_id INTEGER, action TEXT, target INTEGER, details TEXT);
""")
db.commit()

def operator(uid:int):
    return db.execute("SELECT * FROM operators WHERE user_id=?", (uid,)).fetchone()
def is_admin(uid:int, chat_id:int=None)->bool:
    op=operator(uid)
    return bool(op and (chat_id is None or op["admin_room_id"]==chat_id))
def owner_of_group(chat_id:int):
    row=db.execute("SELECT owner_id FROM groups WHERE chat_id=?", (chat_id,)).fetchone()
    return row["owner_id"] if row else None
def log_action(actor, chat_id, action, target=0, details=""):
    db.execute("INSERT INTO logs(at,actor,chat_id,action,target,details) VALUES(?,?,?,?,?,?)",
      (datetime.now(timezone.utc).isoformat(),actor,chat_id,action,target,details[:500]))
    db.commit()
def group_row(chat):
    db.execute("INSERT OR IGNORE INTO groups(chat_id,title) VALUES(?,?)",(chat.id,chat.title or str(chat.id)))
    db.commit()
    return db.execute("SELECT * FROM groups WHERE chat_id=?",(chat.id,)).fetchone()
def linked(chat_id):
    return db.execute("SELECT 1 FROM groups WHERE chat_id=?",(chat_id,)).fetchone() is not None
def user_row(chat_id, user_id):
    db.execute("INSERT OR IGNORE INTO users(chat_id,user_id) VALUES(?,?)",(chat_id,user_id)); db.commit()
    return db.execute("SELECT * FROM users WHERE chat_id=? AND user_id=?",(chat_id,user_id)).fetchone()
def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="🛡 Moderation & Sicherheit",callback_data="menu:mod"),InlineKeyboardButton(text="⚙ Gruppeneinstellungen",callback_data="menu:group")],
      [InlineKeyboardButton(text="👋 Begrüßung & Regeln",callback_data="menu:welcome"),InlineKeyboardButton(text="🎭 Nutzerpersönlichkeit",callback_data="menu:style")],
      [InlineKeyboardButton(text="🏆 Aktivität & Ranking",callback_data="menu:rank"),InlineKeyboardButton(text="🤖 KI & Werkzeuge",callback_data="menu:ai")],
      [InlineKeyboardButton(text="📋 Protokolle",callback_data="menu:logs")]])
def setting_keyboard(row):
    labels={"anti_spam":"Anti-Spam","anti_flood":"Anti-Flood","link_filter":"Linkfilter","welcome":"Begrüßung"}
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=f"{'✅' if row[k] else '❌'} {v}",callback_data=f"toggle:{k}") for k,v in labels.items()],
      [InlineKeyboardButton(text="📜 Regeln setzen: /setrules Text",callback_data="noop")]])
@dp.message(Command("setupadminroom"))
async def setup_adminroom(m:Message):
    if m.chat.type not in ("group","supergroup"):
        await m.answer("Führe /setupadminroom in deiner eigenen Admin-Gruppe aus."); return
    try:
        member=await bot.get_chat_member(m.chat.id,m.from_user.id)
        if member.status not in ("administrator","creator"):
            await m.reply("Nur Admins dieser Gruppe können sie als Adminraum registrieren."); return
    except Exception:
        await m.reply("Ich konnte deine Adminrechte nicht prüfen. Stelle sicher, dass ich Zugriff auf die Gruppenmitglieder habe."); return
    existing=db.execute("SELECT user_id FROM operators WHERE admin_room_id=?", (m.chat.id,)).fetchone()
    if existing and existing["user_id"] != m.from_user.id:
        await m.reply("Dieser Adminraum ist bereits einem anderen Betreiber zugeordnet."); return
    db.execute("INSERT INTO operators(user_id,admin_room_id,created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET admin_room_id=excluded.admin_room_id", (m.from_user.id,m.chat.id,datetime.now(timezone.utc).isoformat())); db.commit()
    await m.reply("Dein Adminraum ist registriert. Nur du kannst von hier aus deine verknüpften Gruppen verwalten. Füge jetzt Dr.Housebot in deine Zielgruppe ein und nutze dort /connect.")
@dp.message(Command("start"))
async def start(m:Message):
    await m.answer("Dr.Housebot online. Ich bin kein Wunderheiler. Wobei, im Vergleich zu manchen Admins …",reply_markup=menu())
@dp.message(Command("help"))
async def help_cmd(m:Message):
    await m.answer("Befehle: /menu, /connect, /setupadminroom, /setrules TEXT, /rules, /rank, /stil neutral|trocken|freundlich, /ai TEXT, /wetter STADT, /zitat, /nasa. Im eigenen Adminraum: /send TEXT, /warn CHAT_ID USER_ID GRUND, /mute CHAT_ID USER_ID MINUTEN [GRUND], /unmute CHAT_ID USER_ID, /kick CHAT_ID USER_ID, /ban CHAT_ID USER_ID [GRUND], /unban CHAT_ID USER_ID.")
@dp.message(Command("menu"))
async def menu_cmd(m:Message):
    await m.answer("Was soll ich tun? Bitte nichts Medizinisches. Ich bin ein Bot.",reply_markup=menu())
@dp.callback_query(F.data.startswith("menu:"))
async def menu_callback(c:CallbackQuery):
    key=c.data.split(":",1)[1]
    text={"mod":"Moderation: /warn, /mute, /kick, /ban. Im Adminraum nur für freigeschaltete Admin-IDs.",
    "group":"Gruppenschalter sind für Gruppenadmins verfügbar. /settings zeigt den Status.",
    "welcome":"/setrules TEXT setzt die Gruppenregeln; /rules zeigt sie an.",
    "style":"Nutze /stil neutral, /stil trocken oder /stil freundlich. Das ändert niemals Rechte.",
    "rank":"/rank zeigt die aktivsten Mitglieder dieser Gruppe.",
    "ai":"/ai FRAGE, /wetter STADT, /zitat und /nasa.",
    "logs":"/logs zeigt die letzten Moderationsaktionen (Adminraum/Admins)."} .get(key,"")
    await c.message.edit_text(text,reply_markup=menu())
    await c.answer()
@dp.callback_query(F.data.startswith("toggle:"))
async def toggle(c:CallbackQuery):
    if not c.message or c.message.chat.type=="private":
        await c.answer("Nur in einer Gruppe.",show_alert=True); return
    member=await bot.get_chat_member(c.message.chat.id,c.from_user.id)
    if member.status not in ("administrator","creator"):
        await c.answer("Nur Gruppenadmins.",show_alert=True); return
    key=c.data.split(":",1)[1]
    if key not in ("anti_spam","anti_flood","link_filter","welcome"):
        await c.answer(); return
    row=group_row(c.message.chat)
    db.execute(f"UPDATE groups SET {key}=? WHERE chat_id=?",(0 if row[key] else 1,c.message.chat.id)); db.commit()
    await c.message.edit_reply_markup(reply_markup=setting_keyboard(group_row(c.message.chat)))
    await c.answer("Gespeichert.")
@dp.message(Command("connect"))
async def connect(m:Message):
    if m.chat.type=="private":
        await m.answer("Führe /connect in der Zielgruppe aus; du musst dort Admin sein."); return
    member=await bot.get_chat_member(m.chat.id,m.from_user.id)
    if member.status not in ("administrator","creator"):
        await m.reply("Nur Gruppenadmins können diese Gruppe verknüpfen."); return
    op=operator(m.from_user.id)
    if not op:
        await m.reply("Registriere zuerst deinen Adminraum mit /setupadminroom dort. Dann erneut /connect hier."); return
    db.execute("INSERT INTO groups(chat_id,title,owner_id) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, owner_id=COALESCE(groups.owner_id, excluded.owner_id)",(m.chat.id,m.chat.title or str(m.chat.id),m.from_user.id)); db.commit(); log_action(m.from_user.id,m.chat.id,"connect")
    await m.reply("Gruppe mit Dr.Housebot verknüpft. Adminraum-Befehle sind jetzt für diese Gruppe freigeschaltet.")
@dp.message(Command("settings"))
async def settings(m:Message):
    if m.chat.type=="private": await m.answer("Gruppeneinstellungen funktionieren in einer Gruppe."); return
    row=group_row(m.chat)
    await m.answer("Einstellungen:",reply_markup=setting_keyboard(row))
@dp.message(Command("setrules"))
async def setrules(m:Message):
    if m.chat.type=="private": return
    member=await bot.get_chat_member(m.chat.id,m.from_user.id)
    if member.status not in ("administrator","creator"): await m.reply("Nur Gruppenadmins."); return
    rules=m.text.partition(" ")[2].strip()
    if not rules: await m.reply("Verwendung: /setrules Hier stehen die Regeln"); return
    group_row(m.chat); db.execute("UPDATE groups SET rules=? WHERE chat_id=?",(rules[:4000],m.chat.id)); db.commit()
    await m.reply("Regeln gespeichert. Wenigstens etwas, das hier geregelt ist.")
@dp.message(Command("rules"))
async def rules(m:Message):
    if m.chat.type=="private": await m.answer("Bitte in der Gruppe nutzen."); return
    row=group_row(m.chat); await m.answer("📜 Gruppenregeln\n"+(row["rules"] or "Noch keine Regeln hinterlegt. Anarchie, aber mit Datenbank."))
@dp.message(Command("stil"))
async def style(m:Message):
    args=m.text.split(maxsplit=1)
    if len(args)<2 or args[1].lower() not in ("neutral","trocken","freundlich"):
        await m.reply("Wähle: /stil neutral, /stil trocken oder /stil freundlich"); return
    cid=m.chat.id if m.chat.type!="private" else 0
    user_row(cid,m.from_user.id); db.execute("UPDATE users SET style=? WHERE chat_id=? AND user_id=?",(args[1].lower(),cid,m.from_user.id)); db.commit()
    await m.reply("Stil gespeichert. Deine Rechte bleiben davon unbeeindruckt.")
@dp.message(Command("ai"))
async def ai_cmd(m:Message):
    prompt=m.text.partition(" ")[2].strip()
    if not prompt: await m.reply("Verwendung: /ai Deine Frage"); return
    style=user_row(m.chat.id if m.chat.type!="private" else 0,m.from_user.id)["style"]
    prefixes={"neutral":"Antworte auf Deutsch, klar und knapp.","trocken":"Antworte auf Deutsch, trocken, sarkastisch und knapp, mit eigener Formulierung im Stil eines zynischen Diagnostikers.","freundlich":"Antworte auf Deutsch, freundlich und hilfreich."}
    try: answer=await ask_ai(prefixes[style]+"\n"+prompt)
    except Exception as e:
        logging.warning("AI unavailable: %s",e); answer="Die KI-Ärzte sind gerade nicht erreichbar. Moderation und Gruppenfunktionen laufen weiter."
    await m.answer(answer[:4000])
@dp.message(Command("zitat"))
async def quote(m:Message):
    import random
    quotes=["Menschen lügen. Datenbanken auch, wenn man sie falsch abfragt.","Wenn Schweigen Gold ist, ist Gruppenchatscrollen Bergbau.","Ich bin nicht unhöflich. Ich spare nur unnötige Silben."]
    await m.answer(random.choice(quotes))
@dp.message(Command("wetter"))
async def weather(m:Message):
    city=m.text.partition(" ")[2].strip()
    if not city: await m.reply("Verwendung: /wetter STADT"); return
    import aiohttp
    try:
      async with aiohttp.ClientSession() as s:
        async with s.get("https://geocoding-api.open-meteo.com/v1/search",params={"name":city,"count":1,"language":"de","format":"json"},timeout=10) as r: geo=await r.json()
        if not geo.get("results"): await m.reply("Ort nicht gefunden."); return
        p=geo["results"][0]
        async with s.get("https://api.open-meteo.com/v1/forecast",params={"latitude":p["latitude"],"longitude":p["longitude"],"current":"temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m","timezone":"auto"},timeout=10) as r: data=await r.json()
      c=data["current"]
      await m.answer(f"🌦 {p['name']}: {c['temperature_2m']} °C (gefühlt {c['apparent_temperature']} °C), Luftfeuchte {c['relative_humidity_2m']} %, Wind {c['wind_speed_10m']} km/h.")
    except Exception: await m.reply("Wetterdienst nicht erreichbar. Der Himmel verweigert die Aussage.")
@dp.message(Command("nasa"))
async def nasa(m:Message):
    import aiohttp
    key=os.getenv("NASA_API_KEY","DEMO_KEY")
    try:
      async with aiohttp.ClientSession() as s:
        async with s.get("https://api.nasa.gov/planetary/apod",params={"api_key":key},timeout=12) as r: data=await r.json()
      msg=f"🌌 {data.get('title','NASA APOD')}\n{data.get('explanation','')[:2500]}\n{data.get('url','')}"
      await m.answer(msg[:4000])
    except Exception: await m.reply("NASA-Daten gerade nicht verfügbar. Selbst das Weltall hat Wartungsfenster.")
@dp.message(Command("rank"))
async def rank(m:Message):
    if m.chat.type=="private": await m.answer("Das Ranking gibt es pro Gruppe."); return
    rows=db.execute("SELECT user_id,points FROM users WHERE chat_id=? ORDER BY points DESC LIMIT 10",(m.chat.id,)).fetchall()
    await m.answer("🏆 Aktivitätsranking\n"+("\n".join(f"{i+1}. {r['user_id']} — {r['points']} Punkte" for i,r in enumerate(rows)) if rows else "Noch keine Aktivität erfasst."))
@dp.message(Command("send"))
async def send(m:Message):
    if not is_admin(m.from_user.id,m.chat.id):
        await m.reply("Dieser Befehl ist nur für freigeschaltete Admins im konfigurierten Adminraum."); return
    text=m.text.partition(" ")[2].strip()
    if not text: await m.reply("Verwendung: /send Nachricht"); return
    rows=db.execute("SELECT chat_id FROM groups WHERE owner_id=?",(m.from_user.id,)).fetchall(); ok=0
    for row in rows:
      try: await bot.send_message(row["chat_id"],text); ok+=1
      except Exception as e: logging.warning("Send to %s failed: %s",row["chat_id"],e)
    log_action(m.from_user.id,m.chat.id,"broadcast",details=f"{ok}/{len(rows)}")
    await m.reply(f"Nachricht an {ok} von {len(rows)} verknüpften Gruppen gesendet.")
async def admin_action(m:Message, action:str):
    if not is_admin(m.from_user.id,m.chat.id):
        await m.reply("Nur freigeschaltete Admins im Adminraum dürfen das."); return
    parts=m.text.split(maxsplit=4)
    need=3 if action in ("warn","kick","ban","unban","unmute") else 4
    if len(parts)<need:
        await m.reply(f"Parameter fehlen. Beispiel: /{action} CHAT_ID USER_ID"+(" MINUTEN" if action=="mute" else "")); return
    try:
      cid=int(parts[1]); uid=int(parts[2])
      if not linked(cid) or owner_of_group(cid)!=m.from_user.id: await m.reply("Diese Gruppe ist nicht mit deinem Betreiberkonto verknüpft."); return
      reason=parts[3] if len(parts)>3 else "Keine Begründung angegeben"
      if action=="warn":
        db.execute("INSERT OR IGNORE INTO warnings(chat_id,user_id,count) VALUES(?,?,0)",(cid,uid))
        db.execute("UPDATE warnings SET count=count+1 WHERE chat_id=? AND user_id=?",(cid,uid)); db.commit()
        n=db.execute("SELECT count FROM warnings WHERE chat_id=? AND user_id=?",(cid,uid)).fetchone()["count"]
        log_action(m.from_user.id,cid,"warn",uid,reason)
        await bot.send_message(cid,f"⚠️ Verwarnung für {uid}: {reason} ( {n}/3 )")
        if n>=3: await bot.ban_chat_member(cid,uid); log_action(m.from_user.id,cid,"auto_ban",uid,"3 Verwarnungen")
      elif action=="mute":
        mins=int(parts[3]); reason=parts[4] if len(parts)>4 else "Keine Begründung angegeben"
        await bot.restrict_chat_member(cid,uid,ChatPermissions(can_send_messages=False),until_date=int(time.time()+max(1,min(mins,10080))*60))
        log_action(m.from_user.id,cid,"mute",uid,reason)
      elif action=="unmute":
        await bot.restrict_chat_member(cid,uid,ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
        log_action(m.from_user.id,cid,"unmute",uid)
      elif action=="kick":
        await bot.ban_chat_member(cid,uid); await bot.unban_chat_member(cid,uid); log_action(m.from_user.id,cid,"kick",uid,reason)
      elif action=="ban":
        await bot.ban_chat_member(cid,uid); log_action(m.from_user.id,cid,"ban",uid,reason)
      elif action=="unban":
        await bot.unban_chat_member(cid,uid); log_action(m.from_user.id,cid,"unban",uid)
      await m.reply(f"Aktion {action} für {uid} in {cid} ausgeführt.")
    except Exception as e:
      logging.exception("Moderation failed"); await m.reply(f"Aktion fehlgeschlagen: {e}")
for action in ("warn","mute","unmute","kick","ban","unban"):
    async def handler(m:Message, _action=action): await admin_action(m,_action)
    dp.message.register(handler,Command(action))
@dp.message(Command("logs"))
async def logs(m:Message):
    if not is_admin(m.from_user.id,m.chat.id): await m.reply("Kein Zugriff."); return
    rows=db.execute("SELECT at,actor,chat_id,action,target,details FROM logs ORDER BY id DESC LIMIT 15").fetchall()
    await m.answer("📋 Letzte Aktionen\n"+("\n".join(f"{r['at'][11:19]} {r['action']} chat={r['chat_id']} user={r['target']} {r['details']}" for r in rows) if rows else "Noch keine Protokolle."))
@dp.message(F.chat.type.in_({"group","supergroup"}))
async def group_guard(m:Message):
    if not linked(m.chat.id): return
    row=group_row(m.chat)
    if m.from_user and not m.from_user.is_bot:
      user_row(m.chat.id,m.from_user.id)
      db.execute("UPDATE users SET points=points+1 WHERE chat_id=? AND user_id=?",(m.chat.id,m.from_user.id)); db.commit()
    if not m.from_user or m.from_user.is_bot: return
    try:
      member=await bot.get_chat_member(m.chat.id,m.from_user.id)
      if member.status in ("administrator","creator"): return
    except Exception: pass
    text=m.text or m.caption or ""
    now=time.time(); q=flood[(m.chat.id,m.from_user.id)]; q.append(now)
    while q and now-q[0]>8: q.popleft()
    if row["anti_flood"] and len(q)>=7:
      try: await m.delete(); await bot.restrict_chat_member(m.chat.id,m.from_user.id,ChatPermissions(can_send_messages=False),until_date=int(now+60)); log_action(0,m.chat.id,"anti_flood",m.from_user.id)
      except Exception: pass
      return
    if row["anti_spam"] and text:
      key=(m.chat.id,m.from_user.id,text.lower())
      if now-spam_last.get(key,0)<3:
        try: await m.delete(); log_action(0,m.chat.id,"anti_spam",m.from_user.id)
        except Exception: pass
        return
      spam_last[key]=now
    if row["link_filter"] and re.search(r"(https?://|t\.me/|www\.)",text,re.I):
      try: await m.delete(); log_action(0,m.chat.id,"link_filter",m.from_user.id)
      except Exception: pass
    if m.new_chat_members and row["welcome"]:
      for member in m.new_chat_members:
        await m.answer(f"Willkommen, {member.full_name}. Benehm dich. Wir sind hier nicht im Wartezimmer.")

async def main():
    logging.info("Dr.Housebot startet")
    await dp.start_polling(bot)
if __name__=="__main__":
    asyncio.run(main())

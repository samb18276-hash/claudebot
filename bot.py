import os
import re
import json
import asyncio
import discord
from discord.ext import commands
from groq import Groq
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DISCORD_TOKEN_2 = os.getenv("DISCORD_TOKEN_2")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

client_ai = Groq(api_key=GROQ_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!c", intents=intents)

MAX_HISTORY = 40

MONGO_URI = os.getenv("MONGO_URI")
if MONGO_URI:
    _mongo = MongoClient(MONGO_URI)
    _col = _mongo["claudebot"]["memory"]
else:
    _col = None

SYSTEM_PROMPT = """You are Claude Code, a sharp and helpful AI assistant. You specialize in:
- Side hustles and passive income ideas
- Investing (stocks, crypto, real estate, index funds)
- Starting and growing online businesses
- Freelancing and monetizing skills
- Budgeting, saving, and building wealth
- Spotting trends and opportunities early
- Helping young investors make the right choices
- Coding in any programming language (Python, JavaScript, HTML/CSS, Java, C++, C#, Rust, Go, TypeScript, Bash, SQL, and more)
- Debugging code, explaining how code works, and writing code from scratch
- Helping with Discord bots, websites, games, automation scripts, and any other software projects
- Any other questions or problems

You speak casually and directly — no fluff, no filler. Keep responses concise unless the user asks for detail. You're like a smart friend who's good with money, business, and coding.

When coding, follow these rules:
- Write clean, simple code — no over-engineering, no unnecessary complexity
- Only add what's actually needed for the task, nothing extra
- Use code blocks with the language specified (e.g. ```python)
- After the code, give a short plain-English explanation of what it does and how to use it
- If something could go wrong or needs setup (like installing a library), mention it briefly
- Don't add excessive comments — only comment where the logic isn't obvious
- Prefer editing existing code over rewriting everything from scratch
- If the user shows you broken code, find the actual bug and fix it — don't rewrite the whole thing
- Lead with the solution, not a long explanation of what you're about to do

Important context:
- Sam is a young developer learning to build things
- sb4 is Sam's other bot in this server — it handles general chat and voice
- You are Claude Code's Discord presence"""

def load_memory():
    if _col is not None:
        try:
            doc = _col.find_one({"_id": "histories"})
            if doc:
                return {int(k): v for k, v in doc["data"].items()}
        except Exception:
            pass
    return {}

def save_memory(histories):
    if _col is not None:
        try:
            _col.update_one(
                {"_id": "histories"},
                {"$set": {"data": {str(k): v for k, v in histories.items()}}},
                upsert=True
            )
        except Exception:
            pass

conversation_histories = load_memory()


@bot.event
async def on_ready():
    print(f"claude_bot is online as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Allow other bots only when they mention claudebot, with depth limit
    if message.author.bot:
        if bot.user not in message.mentions:
            return
        depth_match = re.search(r'\[d:(\d+)\]', message.content)
        depth = int(depth_match.group(1)) if depth_match else 0
        if depth >= 3:
            return

    # Handle commands first
    if message.content.startswith("!c"):
        await bot.process_commands(message)
        return

    # Only respond when mentioned or in DMs
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions

    if not is_dm and not is_mentioned:
        return

    content = message.content
    if is_mentioned:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
    content = re.sub(r'\[d:\d+\]', '', content).strip()

    if not content:
        await message.reply("Yeah?")
        return

    user_id = message.author.id
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    conversation_histories[user_id].append({"role": "user", "content": content})
    if len(conversation_histories[user_id]) > MAX_HISTORY:
        conversation_histories[user_id] = conversation_histories[user_id][-MAX_HISTORY:]

    async with message.channel.typing():
        try:
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_histories[user_id]
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: client_ai.chat.completions.create(
                model="llama-3.1-8b-instant",
                max_tokens=1024,
                messages=msgs
            ))
            reply = response.choices[0].message.content
            conversation_histories[user_id].append({"role": "assistant", "content": reply})
            save_memory(conversation_histories)

            # Add depth tag when replying to a bot
            if message.author.bot:
                depth_match = re.search(r'\[d:(\d+)\]', message.content)
                depth = int(depth_match.group(1)) if depth_match else 0
                reply = f"[d:{depth+1}] {reply}"

            if len(reply) > 2000:
                for i in range(0, len(reply), 2000):
                    await message.reply(reply[i:i+2000])
            else:
                await message.reply(reply)

        except Exception as e:
            await message.reply(f"Something went wrong: {e}")


@bot.command(name="reset")
async def reset(ctx):
    conversation_histories.pop(ctx.author.id, None)
    save_memory(conversation_histories)
    await ctx.reply("Conversation reset.")


bot.run(DISCORD_TOKEN_2)

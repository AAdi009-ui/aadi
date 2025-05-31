import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
import logging

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('discord')

async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py') and not filename.startswith('_'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f'Successfully loaded cog: {filename}')
            except Exception as e:
                logger.error(f'Failed to load cog {filename}: {e}')

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'Discord.py Version: {discord.__version__}')
    logger.info('Attempting to load cogs...')
    await load_cogs()
    logger.info('Cogs loading process complete.')
    logger.info(f'{bot.user.name} is ready and online!')

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    if TOKEN is None:
        logger.error("DISCORD_BOT_TOKEN not found")
    else:
        asyncio.run(main())

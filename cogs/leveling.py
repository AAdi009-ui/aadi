import discord
from discord.ext import commands
import aiosqlite
import math
import logging

logger = logging.getLogger('discord')

import time
import json

class LevelingSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'd:\\3rd bot\\leveling.db'
        self.bot.loop.create_task(self.init_db())
        self.user_cooldowns = {}

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    last_message_timestamp INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    level_up_channel_id INTEGER,
                    xp_per_message INTEGER DEFAULT 15,
                    cooldown_seconds INTEGER DEFAULT 60,
                    level_roles TEXT DEFAULT '{}',
                    channel_multipliers TEXT DEFAULT '{}'
                )
            ''')
            await db.commit()
        logger.info("Leveling system database initialized.")

    async def get_guild_settings(self, guild_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT level_up_channel_id, xp_per_message, cooldown_seconds, level_roles, channel_multipliers FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
                settings = await cursor.fetchone()
                if settings:
                    return settings[0], settings[1], settings[2], json.loads(settings[3] or '{}'), json.loads(settings[4] or '{}')
            await db.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
            return None, 15, 60, {}, {}

    async def get_user_data(self, user_id, guild_id):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT xp, level, last_message_timestamp FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
                return await cursor.fetchone()

    async def update_user_data(self, user_id, guild_id, xp, level, last_message_timestamp):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR REPLACE INTO users (user_id, guild_id, xp, level, last_message_timestamp) VALUES (?, ?, ?, ?, ?)", 
                             (user_id, guild_id, xp, level, last_message_timestamp))
            await db.commit()

    def calculate_xp_for_level(self, level):
        if level < 0: return 0
        return int(5 * (level ** 2) + 50 * level + 100)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        user_id = message.author.id
        guild_id = message.guild.id
        channel_id = message.channel.id
        current_time = int(time.time())

        level_up_channel_id, base_xp_to_add, cooldown_seconds, level_roles_config, channel_multipliers_config = await self.get_guild_settings(guild_id)

        xp_to_add = base_xp_to_add
        channel_multiplier = channel_multipliers_config.get(str(channel_id))
        if channel_multiplier is not None:
            xp_to_add = int(base_xp_to_add * channel_multiplier)

        user_data = await self.get_user_data(user_id, guild_id)
        if not user_data:
            await self.update_user_data(user_id, guild_id, 0, 0, 0)
            xp, current_level, last_msg_ts = 0, 0, 0
        else:
            xp, current_level, last_msg_ts = user_data

        if current_time - last_msg_ts < cooldown_seconds:
            return

        xp += xp_to_add
        await self.update_user_data(user_id, guild_id, xp, current_level, current_time)

        xp_needed_for_next_level = self.calculate_xp_for_level(current_level + 1)
        
        if xp >= xp_needed_for_next_level:
            new_level = current_level + 1
            while xp >= self.calculate_xp_for_level(new_level +1 ):
                 new_level += 1
            
            await self.update_user_data(user_id, guild_id, xp, new_level, current_time)
            
            level_up_message = f'🎉 Congratulations {message.author.mention}, you have reached **Level {new_level}**! 🎉'
            target_channel = None
            if level_up_channel_id:
                target_channel = self.bot.get_channel(level_up_channel_id)
            
            if target_channel:
                try:
                    await target_channel.send(level_up_message)
                except discord.Forbidden:
                    await message.channel.send(f"{level_up_message} (Couldn't send to configured channel.)")
                    logger.warning(f"Could not send level up message to {level_up_channel_id} in guild {guild_id} due to permissions.")
                except discord.HTTPException:
                    await message.channel.send(f"{level_up_message} (Couldn't send to configured channel.)")
                    logger.warning(f"Could not send level up message to {level_up_channel_id} in guild {guild_id} due to HTTP error.")
            else:
                await message.channel.send(level_up_message)
            logger.info(f'{message.author.name} (ID: {user_id}) leveled up to {new_level} in guild {message.guild.name} (ID: {guild_id}). XP: {xp}')

            try:
                role_to_add_id = level_roles_config.get(str(new_level))
                if role_to_add_id:
                    role = message.guild.get_role(int(role_to_add_id))
                    if role and role <= message.guild.me.top_role:
                        await message.author.add_roles(role, reason=f"Reached Level {new_level}")
                        logger.info(f"Assigned role {role.name} to {message.author.name} for reaching level {new_level}.")
                    elif role:
                        logger.warning(f"Cannot assign role {role.name} to {message.author.name} - Bot's role is too low.")
                    else:
                        logger.warning(f"Role ID {role_to_add_id} for level {new_level} not found in guild {guild_id}.")
            except Exception as e:
                logger.error(f"Error assigning role for level {new_level} to {message.author.name}: {e}")

    @commands.hybrid_command(name="rank", description="Check your current rank and XP.")
    async def rank(self, ctx: commands.Context, member: discord.Member = None):
        target_member = member or ctx.author

        user_data = await self.get_user_data(target_member.id, ctx.guild.id)
        if not user_data or user_data[0] == 0:
            await ctx.send(f"{target_member.mention} hasn't earned any XP yet or is not ranked.", ephemeral=True)
            return

        xp, level, _ = user_data 

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users WHERE guild_id = ? AND xp > ?", (ctx.guild.id, xp)) as cursor:
                rank = (await cursor.fetchone())[0] + 1
            async with db.execute("SELECT COUNT(*) FROM users WHERE guild_id = ? AND xp > 0", (ctx.guild.id,)) as cursor:
                total_ranked_users = (await cursor.fetchone())[0]

        xp_for_current_level = self.calculate_xp_for_level(level)
        xp_for_next_level = self.calculate_xp_for_level(level + 1)
        
        current_level_xp = xp - xp_for_current_level
        needed_for_next_level_up = xp_for_next_level - xp_for_current_level

        progress_percentage = (current_level_xp / needed_for_next_level_up) * 100 if needed_for_next_level_up > 0 else 0

        embed = discord.Embed(
            title=f"{target_member.display_name}'s Leveling Stats",
            color=target_member.color if target_member.color != discord.Color.default() else discord.Color.blue()
        )
        embed.set_thumbnail(url=target_member.avatar.url if target_member.avatar else target_member.default_avatar.url)
        
        embed.add_field(name="🏅 Level", value=f"`{level}`", inline=True)
        embed.add_field(name="✨ XP", value=f"`{xp:,}/{xp_for_next_level:,}`", inline=True)
        embed.add_field(name="🏆 Rank", value=f"`#{rank}/{total_ranked_users}`", inline=True)

        progress_bar_length = 15
        filled_blocks = int(progress_bar_length * (current_level_xp / needed_for_next_level_up)) if needed_for_next_level_up > 0 else 0
        empty_blocks = progress_bar_length - filled_blocks
        progress_bar = '▓' * filled_blocks + '░' * empty_blocks
        
        embed.add_field(
            name=f"Progress to Level {level + 1}", 
            value=f"`{progress_bar}` `({current_level_xp:,}/{needed_for_next_level_up:,} XP)` - **{progress_percentage:.2f}%**", 
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Shows the server's top 10 users.")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def leaderboard(self, ctx: commands.Context):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id, xp, level FROM users WHERE guild_id = ? AND xp > 0 ORDER BY xp DESC LIMIT 10", (ctx.guild.id,)) as cursor:
                top_users = await cursor.fetchall()

        if not top_users:
            await ctx.send("The leaderboard is currently empty. Get chatting to rank up!", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🏆 Leaderboard for {ctx.guild.name}",
            color=discord.Color.gold()
        )

        for i, (user_id, xp, level) in enumerate(top_users):
            member = ctx.guild.get_member(user_id)
            name = member.mention if member else f"User ID: {user_id} (Left Server)"
            embed.add_field(name=f"`#{i+1}` {name}", value=f"**Level:** `{level}` | **XP:** `{xp:,}`", inline=False)
        
        embed.set_footer(text=f"Top 10 users by XP in {ctx.guild.name}")
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="levelconfig", description="Configure leveling system settings.", fallback="show")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def levelconfig(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            level_up_channel_id, xp_per_message, cooldown_seconds, level_roles_config, channel_multipliers_config = await self.get_guild_settings(ctx.guild.id)
            channel_mention = f"<#{level_up_channel_id}>" if level_up_channel_id else "Not Set (Defaults to command channel)"
            
            embed = discord.Embed(title=f"Leveling Configuration for {ctx.guild.name}", color=discord.Color.orange())
            embed.add_field(name="📢 Level Up Channel", value=channel_mention, inline=False)
            embed.add_field(name="✨ Base XP Per Message", value=f"`{xp_per_message}` XP", inline=True)
            embed.add_field(name="⏱️ Cooldown", value=f"`{cooldown_seconds}` seconds", inline=True)
            
            roles_str = "No level roles configured."
            if level_roles_config:
                roles_list = []
                for lvl, role_id_str in sorted(level_roles_config.items(), key=lambda item: int(item[0])):
                    role = ctx.guild.get_role(int(role_id_str))
                    roles_list.append(f"Level `{lvl}` → {role.mention if role else f'`Role ID: {role_id_str} (Not Found)`'}")
                if roles_list:
                    roles_str = "\n".join(roles_list)
            embed.add_field(name="🏅 Level Roles", value=roles_str, inline=False)

            multipliers_str = "No channel-specific XP multipliers configured."
            if channel_multipliers_config:
                multi_list = []
                for ch_id_str, multiplier in sorted(channel_multipliers_config.items(), key=lambda item: float(item[1] if isinstance(item[1], (int, float)) else 1.0), reverse=True):
                    channel_obj = ctx.guild.get_channel(int(ch_id_str))
                    multi_list.append(f"{channel_obj.mention if channel_obj else f'`Channel ID: {ch_id_str} (Not Found)`'}: `{multiplier}x` XP")
                if multi_list:
                    multipliers_str = "\n".join(multi_list)
            embed.add_field(name="💸 Channel XP Multipliers", value=multipliers_str, inline=False)

            embed.set_footer(text="Use /levelconfig <subcommand> to change settings.")
            await ctx.send(embed=embed)

    @levelconfig.command(name="setchannel", description="Sets the channel for level-up announcements.")
    @commands.has_permissions(manage_guild=True)
    async def setlevelchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        async with aiosqlite.connect(self.db_path) as db:
            if channel:
                await db.execute("INSERT INTO guild_settings (guild_id, level_up_channel_id) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET level_up_channel_id = excluded.level_up_channel_id", (ctx.guild.id, channel.id))
                await ctx.send(f"✅ Level up announcements will now be sent to {channel.mention}.")
            else:
                await db.execute("INSERT INTO guild_settings (guild_id, level_up_channel_id) VALUES (?, NULL) ON CONFLICT(guild_id) DO UPDATE SET level_up_channel_id = NULL", (ctx.guild.id,))
                await ctx.send("✅ Level up announcements channel has been reset. Announcements will be in the channel where the user levels up.")
            await db.commit()

    @levelconfig.command(name="setxp", description="Sets the amount of XP gained per message.")
    @commands.has_permissions(manage_guild=True)
    async def setxppermessage(self, ctx: commands.Context, amount: commands.Range[int, 1, 1000]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO guild_settings (guild_id, xp_per_message) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET xp_per_message = excluded.xp_per_message", (ctx.guild.id, amount))
            await db.commit()
        await ctx.send(f"✅ XP gained per message set to `{amount}`.")

    @levelconfig.command(name="setcooldown", description="Sets the cooldown (in seconds) for gaining XP.")
    @commands.has_permissions(manage_guild=True)
    async def setcooldown(self, ctx: commands.Context, seconds: commands.Range[int, 0, 3600]):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO guild_settings (guild_id, cooldown_seconds) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET cooldown_seconds = excluded.cooldown_seconds", (ctx.guild.id, seconds))
            await db.commit()
        await ctx.send(f"✅ XP gain cooldown set to `{seconds}` seconds.")

    @levelconfig.command(name="addrole", description="Assigns a role to be given when a user reaches a specific level.")
    @commands.has_permissions(manage_guild=True)
    async def setlevelrole(self, ctx: commands.Context, level: commands.Range[int, 1, 1000], role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.send(f"❌ I cannot assign the role {role.mention} because it is higher than or equal to my highest role. Please adjust my role hierarchy.", ephemeral=True)
            return
        if role.is_default(): # @everyone
             await ctx.send(f"❌ The `@everyone` role cannot be assigned as a level reward.", ephemeral=True)
             return
        if role.is_premium_subscriber() or role.is_bot_managed():
            await ctx.send(f"❌ The role {role.mention} is a Nitro Booster role or managed by a bot and cannot be assigned.", ephemeral=True)
            return

        _, _, _, level_roles_config = await self.get_guild_settings(ctx.guild.id)
        level_roles_config[str(level)] = str(role.id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT INTO guild_settings (guild_id, level_roles) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET level_roles = excluded.level_roles", (ctx.guild.id, json.dumps(level_roles_config)))
            await db.commit()
        await ctx.send(f"✅ Users reaching Level `{level}` will now receive the {role.mention} role.")

    @levelconfig.command(name="removerole", description="Removes a role assignment for a specific level.")
    @commands.has_permissions(manage_guild=True)
    async def removelevelrole(self, ctx: commands.Context, level: int):
        _, _, _, level_roles_config = await self.get_guild_settings(ctx.guild.id)
        if str(level) in level_roles_config:
            removed_role_id = level_roles_config.pop(str(level))
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE guild_settings SET level_roles = ? WHERE guild_id = ?", (json.dumps(level_roles_config), ctx.guild.id))
                await db.commit()
            role = ctx.guild.get_role(int(removed_role_id))
            await ctx.send(f"✅ Role assignment for Level `{level}` ({role.mention if role else 'Unknown Role'}) has been removed.")
        else:
            await ctx.send(f"❌ No role is assigned to Level `{level}`.", ephemeral=True)

    @levelconfig.command(name="listroles", description="Lists all configured level roles.")
    @commands.has_permissions(manage_guild=True)
    async def listlevelroles(self, ctx: commands.Context):
        _, _, _, level_roles_config = await self.get_guild_settings(ctx.guild.id)
        if not level_roles_config:
            await ctx.send("No level roles are currently configured for this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏅 Configured Level Roles for {ctx.guild.name}", color=discord.Color.purple())
        description_lines = []
        for level_str, role_id_str in sorted(level_roles_config.items(), key=lambda item: int(item[0])):
            role = ctx.guild.get_role(int(role_id_str))
            description_lines.append(f"**Level `{level_str}`** → {role.mention if role else f'`Role ID: {role_id_str} (Not Found)`'}")
        
        embed.description = "\n".join(description_lines)
        await ctx.send(embed=embed)

    @levelconfig.command(name="setchannelxp", description="Sets an XP multiplier for a specific channel (e.g., 1.5 for 1.5x XP).")
    @commands.has_permissions(manage_guild=True)
    async def setchannelmultiplier(self, ctx: commands.Context, channel: discord.TextChannel, multiplier: commands.Range[float, 0.0, 10.0]):
        _, _, _, _, channel_multipliers_config = await self.get_guild_settings(ctx.guild.id)
        if multiplier == 1.0:
            if str(channel.id) in channel_multipliers_config:
                del channel_multipliers_config[str(channel.id)]
                message = f"✅ XP multiplier for {channel.mention} has been reset to default (1x)."
            else:
                await ctx.send(f"ℹ️ XP multiplier for {channel.mention} is already at default (1x). No changes made.", ephemeral=True)
                return
        elif multiplier == 0.0:
            channel_multipliers_config[str(channel.id)] = 0.0
            message = f"✅ XP gain in {channel.mention} has been **disabled** (0x multiplier)."
        else:
            channel_multipliers_config[str(channel.id)] = multiplier
            message = f"✅ XP multiplier for {channel.mention} set to `{multiplier}x`."
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE guild_settings SET channel_multipliers = ? WHERE guild_id = ?", (json.dumps(channel_multipliers_config), ctx.guild.id))
            await db.commit()
        await ctx.send(message)

    @levelconfig.command(name="removechannelxp", description="Removes an XP multiplier from a specific channel, reverting to default.")
    @commands.has_permissions(manage_guild=True)
    async def removechannelmultiplier(self, ctx: commands.Context, channel: discord.TextChannel):
        _, _, _, _, channel_multipliers_config = await self.get_guild_settings(ctx.guild.id)
        if str(channel.id) in channel_multipliers_config:
            del channel_multipliers_config[str(channel.id)]
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("UPDATE guild_settings SET channel_multipliers = ? WHERE guild_id = ?", (json.dumps(channel_multipliers_config), ctx.guild.id))
                await db.commit()
            await ctx.send(f"✅ XP multiplier for {channel.mention} has been removed. It will now use the server default XP rate (1x).")
        else:
            await ctx.send(f"❌ No specific XP multiplier is set for {channel.mention}. It's already using the default rate.", ephemeral=True)

    @levelconfig.command(name="listchannelxp", description="Lists all channel-specific XP multipliers.")
    @commands.has_permissions(manage_guild=True)
    async def listchannelmultipliers(self, ctx: commands.Context):
        _, _, _, _, channel_multipliers_config = await self.get_guild_settings(ctx.guild.id)
        if not channel_multipliers_config:
            await ctx.send("No channel-specific XP multipliers are configured for this server.", ephemeral=True)
            return

        embed = discord.Embed(title=f"💸 Channel XP Multipliers for {ctx.guild.name}", color=discord.Color.green())
        description_lines = []
        for channel_id_str, multiplier in sorted(channel_multipliers_config.items(), key=lambda item: float(item[1] if isinstance(item[1], (int, float)) else 1.0), reverse=True):
            channel_obj = ctx.guild.get_channel(int(channel_id_str))
            status = f'`{multiplier}x` XP'
            if multiplier == 0.0:
                status = '`Disabled (0x)`'
            description_lines.append(f"{channel_obj.mention if channel_obj else f'`Channel ID: {channel_id_str} (Not Found)`'}: {status}")
        
        embed.description = "\n".join(description_lines)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="levelhelp", aliases=['lhelp'], description="Shows help for leveling system commands.")
    async def levelhelp(self, ctx: commands.Context):
        embed = discord.Embed(title="✨ Leveling System Help ✨", color=discord.Color.teal())
        embed.description = "Here are the available commands for the leveling system:"

        embed.add_field(name="`!rank [member]`", value="Check your or another member's rank, XP, and level.", inline=False)
        embed.add_field(name="`!leaderboard`", value="Display the server's top 10 users by XP.", inline=False)
        
        admin_header = "🛠️ Admin Configuration Commands (`/levelconfig`)"
        admin_commands_value = (
            "`show` - View current leveling settings.\n"
            "`setchannel [channel]` - Set the channel for level-up messages (leave blank to reset).\n"
            "`setxp <amount>` - Set base XP gained per message (1-1000).\n"
            "`setcooldown <seconds>` - Set XP gain cooldown (0-3600s).\n"
            "`addrole <level> <role>` - Assign a role for reaching a level.\n"
            "`removerole <level>` - Remove role assignment for a level.\n"
            "`listroles` - List all configured level-to-role assignments.\n"
            "`setchannelxp <channel> <multiplier>` - Set XP multiplier for a channel (e.g., 1.5 for 1.5x, 0 to disable XP).\n"
            "`removechannelxp <channel>` - Remove XP multiplier from a channel.\n"
            "`listchannelxp` - List all channel XP multipliers."
        )
        embed.add_field(name=admin_header, value=admin_commands_value, inline=False)
        embed.set_footer(text=f"Use {ctx.prefix}command or /command for slash commands.")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LevelingSystem(bot))
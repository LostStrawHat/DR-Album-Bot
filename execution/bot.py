import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import sqlite3

# Import our custom logic
from filter_logic import process_attachment, add_to_meme_cache, add_to_uploaded_cache
from storage import upload_to_cloudinary, log_photo_to_db
import db_manager

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
TOKEN = os.getenv('DISCORD_TOKEN')
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(WORKSPACE_ROOT, 'photos.sqlite3')


def get_db():
    return sqlite3.connect(DB_PATH)

def set_config(key: str, value: str):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_config(key: str):
    conn = get_db()
    cursor = conn.execute("SELECT value FROM config WHERE key=?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


async def discord_log(bot, msg: str):
    """Pipes terminal prints securely into the Discord Log channel."""
    print(msg) # Terminal redundancy
    log_channel_id = get_config("log_channel_id")
    if log_channel_id:
        channel = bot.get_channel(int(log_channel_id))
        if channel:
            await channel.send(f"`[LOG]` {msg}")


class ReviewView(discord.ui.View):
    def __init__(self, original_message: discord.Message, attachment: discord.Attachment, file_hash: str, bot_instance):
        super().__init__(timeout=None)
        self.original_message = original_message
        self.attachment = attachment
        self.file_hash = file_hash
        self.bot = bot_instance

    @discord.ui.button(label="Approve Photo", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Uploading... Please wait.", ephemeral=True)
        try:
            cloud_url = await upload_to_cloudinary(self.attachment)
            log_photo_to_db(self.original_message.id, self.original_message.author.id, cloud_url, self.attachment.filename)
            add_to_uploaded_cache(self.file_hash, cloud_url) # Cache the fingerprint to prevent future duplicate uploads!
            await discord_log(self.bot, f"✅ Mod Approved Image: `{self.attachment.filename}` -> `<{cloud_url}>`")
            await interaction.followup.send(f"✅ Approved! Saved to Cloud.", ephemeral=False)
        except Exception as e:
            await discord_log(self.bot, f"🚨 **Upload Crash on Approval** `{self.attachment.filename}`:\n```{e}```")
            await interaction.followup.send(f"❌ Upload failed. Pls check `#bot-logs`.", ephemeral=False)
            
        for item in self.children: item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Discard (Once)", style=discord.ButtonStyle.gray, emoji="🗑️")
    async def discard_once(self, interaction: discord.Interaction, button: discord.ui.Button):
        await discord_log(self.bot, f"🗑️ Mod Silently Discarded: `{self.attachment.filename}`")
        await interaction.response.send_message(f"🗑️ Discarded this image.", ephemeral=False)
        for item in self.children: item.disabled = True
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Discard & Blacklist", style=discord.ButtonStyle.red, emoji="🚫")
    async def discard_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        add_to_meme_cache(self.file_hash)
        await discord_log(self.bot, f"🚫 Mod BLACKLISTED Meme Hash: `{self.file_hash}`")
        await interaction.response.send_message(f"🚫 Blacklisted! Will auto-ignore in the future.", ephemeral=False)
        for item in self.children: item.disabled = True
        await interaction.message.edit(view=self)


class PhotoBotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        db_manager.setup_database() # Auto-boots database tables upon module load to prevent edge case crashing!
        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f'Logged on as {self.user}!')

bot = PhotoBotClient()

@bot.tree.command(name="setup_server", description="Auto-generates the private Admin Queue and Logging channels secretly for the owner!")
async def setup_server(interaction: discord.Interaction):
    guild = interaction.guild
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this!", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True)
    }
    
    category = await guild.create_category("Bot Operations", overwrites=overwrites)
    admin_queue = await category.create_text_channel("admin-queue")
    bot_logs = await category.create_text_channel("bot-logs")
    
    set_config("review_channel_id", str(admin_queue.id))
    set_config("log_channel_id", str(bot_logs.id))
    
    await interaction.followup.send(f"✅ Created {admin_queue.mention} and {bot_logs.mention} privately! Run `/set_photo_channel` to tell me where to listen next.")

@bot.tree.command(name="set_photo_channel", description="Set the channel to observe for hangout photos")
@app_commands.describe(channel="The channel to listen to")
async def set_photo_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    set_config("photo_channel_id", str(channel.id))
    await interaction.response.send_message(f"Photo channel bound to {channel.mention}.", ephemeral=True)


async def handle_media_routing(message: discord.Message):
    for attachment in message.attachments:
        action, file_hash = await process_attachment(attachment)
        
        if action == "DISCARD":
            await discord_log(bot, f"🚯 Automatically filtered meme/gif: `{attachment.filename}`")
            continue
            
        elif action == "DUPLICATE":
            await discord_log(bot, f"♻️ **Ignored duplicate photo**: `{attachment.filename}` (Already securely archived).")
            continue
            
        elif action == "SAVE":
            await discord_log(bot, f"📸 High-Res Photo accepted: `{attachment.filename}`. Uploading!")
            try:
                cloud_url = await upload_to_cloudinary(attachment)
                log_photo_to_db(message.id, message.author.id, cloud_url, attachment.filename)
                add_to_uploaded_cache(file_hash, cloud_url) # Prevent dupes
                await discord_log(bot, f"✅ Safely Archived to `<{cloud_url}>`")
            except Exception as e:
                await discord_log(bot, f"🚨 **Upload Crash on High-Res Auto-Save** `{attachment.filename}`:\n```{e}```")
            
        elif action == "REVIEW":
            review_channel_id = get_config("review_channel_id")
            if review_channel_id:
                review_channel = bot.get_channel(int(review_channel_id))
                if review_channel:
                    view = ReviewView(original_message=message, attachment=attachment, file_hash=file_hash, bot_instance=bot)
                    content = f"**Pending Review Queue!**\nSent by: {message.author.mention}\n{attachment.url}"
                    await review_channel.send(content=content, view=view)

@bot.tree.command(name="sync_history", description="Syncs all historical messages in the photo channel")
async def sync_history(interaction: discord.Interaction):
    photo_channel_id = get_config("photo_channel_id")
    if not photo_channel_id:
        await interaction.response.send_message("Please run `/set_photo_channel` first!", ephemeral=True)
        return
        
    await interaction.response.send_message(f"Starting historical scrape on channel <#{photo_channel_id}>... This might take a while.", ephemeral=True)
    
    channel = bot.get_channel(int(photo_channel_id))
    if not channel: return
        
    async for message in channel.history(limit=None, oldest_first=True):
        if message.attachments:
            await handle_media_routing(message)
            
    print(f"Finished history sync.")

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
        
    photo_channel_id = get_config("photo_channel_id")
    if photo_channel_id and str(message.channel.id) == photo_channel_id:
        if message.attachments:
            await handle_media_routing(message)

if __name__ == '__main__':
    if TOKEN and TOKEN != 'your_discord_bot_token_here':
        bot.run(TOKEN)
    else:
        print("WARNING: Please set DISCORD_TOKEN in the .env file")

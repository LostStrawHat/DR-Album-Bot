import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import sqlite3

# Import our custom logic
from filter_logic import process_attachment, add_to_meme_cache, add_to_uploaded_cache, remove_from_meme_cache, remove_from_uploaded_cache, is_known_upload
from storage import log_photo_to_db, remove_photo_from_db
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

async def discord_log(bot, msg: str, attachment_url: str = None):
    """Pipes terminal prints securely into the Discord Log channel."""
    print(msg) 
    log_channel_id = get_config("log_channel_id")
    if log_channel_id:
        channel = bot.get_channel(int(log_channel_id))
        if channel:
            final_msg = f"`[LOG]` {msg}"
            if attachment_url:
                final_msg += f"\n{attachment_url}"
            await channel.send(final_msg)

class ReviewView(discord.ui.View):
    def __init__(self, original_message: discord.Message, attachment: discord.Attachment, file_hash: str, bot_instance):
        super().__init__(timeout=None)
        self.original_message = original_message
        self.attachment = attachment
        self.file_hash = file_hash
        self.bot = bot_instance
        self.last_action = None
        self.cloud_url = None

    @discord.ui.button(label="Approve Photo", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        try:
            self.cloud_url = self.attachment.url
            # First, remove it from the default blacklist since it's being rescued
            remove_from_meme_cache(self.file_hash)
            
            composite_id = f"{self.original_message.id}-{self.attachment.id}"
            log_photo_to_db(composite_id, self.original_message.channel.id, self.original_message.author.id, self.original_message.author.display_name, self.cloud_url, self.attachment.filename, self.original_message.created_at.isoformat())
            add_to_uploaded_cache(self.file_hash, self.cloud_url)
            
            await discord_log(self.bot, f"✅ Mod Approved Image: `{self.attachment.filename}` -> Natively recorded inside SQL!", self.attachment.url)
            
            self.last_action = "APPROVE"
            self.update_buttons()
            await interaction.followup.send(f"✅ Approved! Seamlessly mounted permanently to dashboard.", ephemeral=False)
            await interaction.message.edit(view=self)
        except Exception as e:
            await discord_log(self.bot, f"🚨 **Database Crash on Approval** `{self.attachment.filename}`:\n```{e}```", self.attachment.url)
            await interaction.followup.send(f"❌ Core exception failed. Pls check `#bot-logs`.", ephemeral=False)

    @discord.ui.button(label="Discard & Blacklist", style=discord.ButtonStyle.red, emoji="🚫")
    async def discard_blacklist(self, interaction: discord.Interaction, button: discord.ui.Button):
        add_to_meme_cache(self.file_hash)
        await discord_log(self.bot, f"🚫 Mod BLACKLISTED Meme Hash: `{self.file_hash}`", self.attachment.url)
        
        self.last_action = "BLACKLIST"
        self.update_buttons()
        await interaction.response.send_message(f"🚫 Blacklisted! Will auto-ignore in the future.", ephemeral=False)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.blurple, emoji="↩️", disabled=True)
    async def undo_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.last_action == "BLACKLIST":
            remove_from_meme_cache(self.file_hash)
            await discord_log(self.bot, f"↩️ Mod UNDID Blacklist for Hash: `{self.file_hash}`", self.attachment.url)
            await interaction.response.send_message("↩️ Un-Blacklisted! Image is back in the queue.", ephemeral=False)
        elif self.last_action == "APPROVE":
            remove_from_uploaded_cache(self.file_hash)
            composite_id = f"{self.original_message.id}-{self.attachment.id}"
            remove_photo_from_db(composite_id)
            await discord_log(self.bot, f"↩️ Mod UNDID Approval for: `{self.attachment.filename}`. (Cloud URL orphaned)", self.attachment.url)
            await interaction.response.send_message("↩️ Undo successful! Image is removed from SQLite duplicate shield.", ephemeral=False)

        self.last_action = None
        self.reset_buttons()
        await interaction.message.edit(view=self)

    def update_buttons(self):
        self.approve.disabled = True
        self.discard_blacklist.disabled = True
        self.undo_action.disabled = False

    def reset_buttons(self):
        self.approve.disabled = False
        self.discard_blacklist.disabled = False
        self.undo_action.disabled = True

class ResetConfirmView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=60.0)
        self.bot = bot_instance

    @discord.ui.button(label="NUKE DATABASE", style=discord.ButtonStyle.danger, emoji="💥")
    async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        db_manager.reset_all_data()
        await discord_log(self.bot, f"💥 **DATABASE NUKED** by {interaction.user.mention}!")
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ Database has been completely wiped. All photos and caches are gone.", view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Whew! Database reset cancelled.", view=self)

class UploadSelect(discord.ui.Select):
    def __init__(self, message: discord.Message, attachments: list[discord.Attachment]):
        self.msg = message
        self.attachments_map = {att.id: att for att in attachments}
        
        options = []
        for i, att in enumerate(attachments):
            options.append(discord.SelectOption(
                label=f"Image {i+1}: {att.filename[-50:]}", 
                value=str(att.id)
            ))
            
        super().__init__(
            placeholder="Select attachments to forcefully add...",
            min_values=1,
            max_values=len(options),
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        added_count = 0
        duplicate_count = 0
        
        for att_id_str in self.values:
            att = self.attachments_map[int(att_id_str)]
            # We bypass the filter intentionally as requested, but we still deduplicate
            try:
                import hashlib
                image_bytes = await att.read()
                file_hash = hashlib.sha256(image_bytes).hexdigest()
                
                # Deduplication logic remains to prevent spam
                if is_known_upload(file_hash):
                    duplicate_count += 1
                    continue
                
                cloud_url = att.url
                composite_id = f"{self.msg.id}-{att.id}"
                log_photo_to_db(composite_id, self.msg.channel.id, self.msg.author.id, self.msg.author.display_name, cloud_url, att.filename, self.msg.created_at.isoformat())
                add_to_uploaded_cache(file_hash, cloud_url)
                added_count += 1
            except Exception as e:
                print(f"Error saving manually added photo: {e}")
                pass
                
        lines = []
        if added_count > 0:
            lines.append(f"✅ Successfully forced {added_count} photo(s) into the Dashboard!")
        if duplicate_count > 0:
            lines.append(f"♻️ {duplicate_count} ignored (already archived).")
            
        await interaction.followup.send("\n".join(lines), ephemeral=True)

class UploadView(discord.ui.View):
    def __init__(self, message: discord.Message, attachments: list[discord.Attachment]):
        super().__init__(timeout=120.0)
        self.add_item(UploadSelect(message, attachments))

class PhotoBotClient(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Register right-click Context Menu
        self.tree.add_command(app_commands.ContextMenu(
            name='Add to Vault',
            callback=self.context_add_to_vault
        ))
        
        db_manager.setup_database()
        await self.tree.sync()
        print("Slash commands synced.")

    async def context_add_to_vault(self, interaction: discord.Interaction, message: discord.Message):
        """Native right-click App command to add photos from a message without copying links."""
        await handle_manual_add(interaction, message)

    async def on_ready(self):
        print(f'Logged on as {self.user}!')
        # Store guild_id so the dashboard backfill can resolve server nicknames
        if self.guilds:
            set_config("guild_id", str(self.guilds[0].id))

bot = PhotoBotClient()

@bot.tree.command(name="setup_server", description="Auto-generates the private Admin Queue and Logging channels secretly for the owner!")
async def setup_server(interaction: discord.Interaction):
    guild = interaction.guild
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this!", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
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
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ **Missing Permissions!** I need `Manage Channels` and `Manage Roles` permissions.\n"
            "Please re-invite me with **Administrator** permissions using the OAuth2 URL Generator in the Discord Developer Portal.",
            ephemeral=True
        )

@bot.tree.command(name="reset_database", description="Wipe all photos and caches. Highly destructive!")
async def reset_database(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this!", ephemeral=True)
        return
        
    view = ResetConfirmView(bot_instance=bot)
    await interaction.response.send_message(
        "⚠️ **WARNING** ⚠️\n"
        "Are you absolutely sure you want to completely wipe the photo database?\n"
        "This will permanently delete ALL photo records, meme caches, and blocklists. "
        "The web Dashboard will instantly become entirely empty.\n\n"
        "**This action cannot be undone.**",
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="set_photo_channel", description="Set the channel to observe for hangout photos")
@app_commands.describe(channel="The channel to listen to")
async def set_photo_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    set_config("photo_channel_id", str(channel.id))
    await interaction.response.send_message(f"Photo channel bound to {channel.mention}.", ephemeral=True)

@bot.tree.command(name="set_album_url", description="Set the public URL for the album dashboard")
@app_commands.describe(url="The public URL (e.g. from Cloudflare)")
async def set_album_url(interaction: discord.Interaction, url: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("Only admins can run this!", ephemeral=True)
        return
    # Ensure it starts with http/https
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    set_config("album_url", url)
    await interaction.response.send_message(f"✅ Album URL saved as: {url}", ephemeral=True)

@bot.tree.command(name="album", description="Get the link to the official memory vault album!")
async def album_command(interaction: discord.Interaction):
    url = get_config("album_url")
    if url:
        await interaction.response.send_message(f"🔗 Here is the album link: **[Album](<{url}>)**")
    else:
        await interaction.response.send_message("❌ The album URL hasn't been set yet. An admin needs to run `/set_album_url`.", ephemeral=True)



async def handle_media_routing(message: discord.Message):
    for attachment in message.attachments:
        action, file_hash = await process_attachment(attachment)
        
        if action == "DISCARD":
            await discord_log(bot, f"🚯 Automatically filtered meme/gif: `{attachment.filename}`", attachment.url)
            continue
            
        elif action == "DUPLICATE":
            await discord_log(bot, f"♻️ **Ignored duplicate photo**: `{attachment.filename}` (Hash: `{file_hash[:8]}`). Already securely archived.", attachment.url)
            continue
            
        elif action == "SAVE":
            readable_date = message.created_at.strftime("%Y-%m-%d %H:%M")
            await discord_log(bot, f"📸 High-Res Photo matched natively: `{attachment.filename}` (Sent: {readable_date}). Anchoring to database!")
            try:
                cloud_url = attachment.url
                composite_id = f"{message.id}-{attachment.id}"
                log_photo_to_db(composite_id, message.channel.id, message.author.id, message.author.display_name, cloud_url, attachment.filename, message.created_at.isoformat())
                add_to_uploaded_cache(file_hash, cloud_url)
                await discord_log(bot, f"✅ Safely Archived seamlessly to Dashboard!", attachment.url)
                
                # Send the auto-deleting confirmation message in the chat
                url = get_config("album_url")
                album_text = ""
                if url:
                    album_text = f" View them here: **[Album](<{url}>)**"
                await message.channel.send(f"{message.author.mention} ✅ successfully uploaded your photo/video(s) to the vault!{album_text}", delete_after=8.0)
            except Exception as e:
                await discord_log(bot, f"🚨 **SQL Engine Crash on Auto-Save** `{attachment.filename}`:\n```{e}```", attachment.url)
            
        elif action == "REVIEW":
            # Blacklist by default unless approved
            add_to_meme_cache(file_hash)
            await discord_log(bot, f"🛡️ **Auto-Blacklisted pending review**: `{attachment.filename}` (Small size/Heuristic flag).", attachment.url)
            
            review_channel_id = get_config("review_channel_id")
            if review_channel_id:
                review_channel = bot.get_channel(int(review_channel_id))
                if review_channel:
                    view = ReviewView(original_message=message, attachment=attachment, file_hash=file_hash, bot_instance=bot)
                    content = f"🛡️ **Auto-Blacklisted Image - Rescue?**\nSent by: {message.author.mention}\n{attachment.url}"
                    await review_channel.send(content=content, view=view)

async def handle_manual_add(interaction: discord.Interaction, message: discord.Message):
    if not message.attachments:
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ No attachments found on that message.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No attachments found on that message.", ephemeral=True)
        return

    # Option B: Interactive selection for multiple objects
    if len(message.attachments) > 1:
        view = UploadView(message, message.attachments)
        if not interaction.response.is_done():
            await interaction.response.send_message("Select the attachments you want to manually add to the vault:", view=view, ephemeral=True)
        else:
            await interaction.followup.send("Select the attachments you want to manually add to the vault:", view=view, ephemeral=True)
    else:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        att = message.attachments[0]
        try:
            import hashlib
            image_bytes = await att.read()
            file_hash = hashlib.sha256(image_bytes).hexdigest()
            
            if is_known_upload(file_hash):
                await interaction.followup.send(f"♻️ Ignored. `{att.filename}` is already securely archived.", ephemeral=True)
                return
            
            cloud_url = att.url
            composite_id = f"{message.id}-{att.id}"
            log_photo_to_db(composite_id, message.channel.id, message.author.id, message.author.display_name, cloud_url, att.filename, message.created_at.isoformat())
            add_to_uploaded_cache(file_hash, cloud_url)
            await interaction.followup.send(f"✅ Successfully forced `{att.filename}` into the Dashboard!", ephemeral=True)
        except Exception as e:
            print(f"Error saving manually added photo: {e}")
            await interaction.followup.send(f"❌ Failed to parse or save `{att.filename}`.", ephemeral=True)

@bot.tree.command(name="add", description="Manually archive a photo by providing a message link or ID")
@app_commands.describe(message_link="The Discord message link containing the photo")
async def add_photo_command(interaction: discord.Interaction, message_link: str):
    await interaction.response.defer(ephemeral=True)
    
    # Try to extract message ID and channel ID from a link
    message_id_str = message_link.split('/')[-1] if '/' in message_link else message_link
    try:
        message_id = int(message_id_str)
    except ValueError:
        await interaction.followup.send("❌ Invalid message link or ID format.", ephemeral=True)
        return

    channel = None
    if 'discord.com/channels/' in message_link:
        parts = message_link.split('/')
        try:
            channel_id = int(parts[-2])
            channel = bot.get_channel(channel_id)
        except (ValueError, IndexError):
            pass
    
    if not channel:
        channel = interaction.channel

    try:
        message = await channel.fetch_message(message_id)
    except discord.NotFound:
        await interaction.followup.send("❌ Message not found. Please provide a full message link, or run this command in the same channel as the message.", ephemeral=True)
        return
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to read that message.", ephemeral=True)
        return
    except discord.HTTPException:
        await interaction.followup.send("❌ Failed to fetch the message.", ephemeral=True)
        return

    await handle_manual_add(interaction, message)

@bot.tree.command(name="refresh_names", description="Updates all dashboard identities to current Discord nicknames")
async def refresh_names(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = get_db()
    users = conn.execute("SELECT DISTINCT user_id FROM photos").fetchall()
    
    count = 0
    for row in users:
        uid = int(row[0])
        try:
            # Try to get member from the current guild for nickname
            user = interaction.guild.get_member(uid)
            if not user:
                # Fallback to global user lookup
                user = await bot.fetch_user(uid)
            
            if user:
                name = getattr(user, 'display_name', user.name)
                conn.execute("UPDATE photos SET user_name = ? WHERE user_id = ?", (name, str(uid)))
                count += 1
        except Exception as e:
            print(f"Failed to refresh name for {uid}: {e}")
            
    conn.commit()
    conn.close()
    await interaction.followup.send(f"✅ Successfully refreshed {count} user identities across the dashboard!", ephemeral=True)

@bot.tree.command(name="sync_history", description="Syncs all historical messages in the photo channel")
async def sync_history(interaction: discord.Interaction):
    photo_channel_id = get_config("photo_channel_id")
    if not photo_channel_id:
        await interaction.response.send_message("Please run `/set_photo_channel` first!", ephemeral=True)
        return
        
    await interaction.response.send_message(f"Starting historical scrape on channel <#{photo_channel_id}>... This might take a while.", ephemeral=True)
    
    channel = bot.get_channel(int(photo_channel_id))
    if not channel: return
    
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            if message.attachments:
                await handle_media_routing(message)
                
        await discord_log(bot, "✅ History sync complete!")
    except discord.Forbidden:
        await discord_log(bot, "❌ **Missing Access!** I can't read message history in that channel. Please grant me `Read Message History` and `View Channels` permissions.")

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

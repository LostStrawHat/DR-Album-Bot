import os
import discord
import requests
import hashlib
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import sqlite3

# Import our custom logic
from filter_logic import process_attachment, add_to_meme_cache, add_to_uploaded_cache, remove_from_meme_cache, remove_from_uploaded_cache, is_known_upload
from storage import log_photo_to_db, remove_photo_from_db, remove_all_photos_for_message
import db_manager
import tunnel_manager
from media_processor import process_media_eagerly
import asyncio

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
            
            self.bot.loop.create_task(process_media_eagerly(self.attachment, composite_id))
            
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
                author_name = getattr(self.msg.author, 'nick', None) or self.msg.author.display_name
                log_photo_to_db(composite_id, self.msg.channel.id, self.msg.author.id, author_name, cloud_url, att.filename, self.msg.created_at.isoformat())
                add_to_uploaded_cache(file_hash, cloud_url)
                bot.loop.create_task(process_media_eagerly(att, composite_id))
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
        # Ensure the dashboard is running on startup
        try:
            tunnel_manager.start_dashboard()
        except Exception as e:
            print(f"Warning: Failed to auto-start dashboard: {e}")
            
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


@bot.tree.command(name="album", description="Get the link to the official memory vault album!")
async def album_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    
    # Ensure the tunnel is active and grab the newest URL
    url = tunnel_manager.ensure_tunnel_active()
    
    if url:
        set_config("album_url", url)
        await interaction.followup.send(f"🔗 Here is the live album link: **[Album](<{url}>)**", ephemeral=False)
    else:
        # Fallback to database URL if tunnel fails to spawn
        db_url = get_config("album_url")
        if db_url:
            await interaction.followup.send(f"⚠️ Tunnel manager failed, but here is the last known link: **[Album](<{db_url}>)**", ephemeral=False)
        else:
            await interaction.followup.send("❌ Could not generate a public link. Please ensure `cloudflared_local` exists and the dashboard is running on port 5050.", ephemeral=False)



async def handle_media_routing(message: discord.Message, silent: bool = False):
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
                author_name = getattr(message.author, 'nick', None) or message.author.display_name
                log_photo_to_db(composite_id, message.channel.id, message.author.id, author_name, cloud_url, attachment.filename, message.created_at.isoformat())
                add_to_uploaded_cache(file_hash, cloud_url)
                bot.loop.create_task(process_media_eagerly(attachment, composite_id))
                await discord_log(bot, f"✅ Safely Archived seamlessly to Dashboard!", attachment.url)
                
                # Send the auto-deleting confirmation message in the chat (unless silent)
                # Removed as per user request
            except Exception as e:
                await discord_log(bot, f"🚨 **SQL Engine Crash on Auto-Save** `{attachment.filename}`:\n```{e}```", attachment.url)
            
        elif action == "REVIEW":
            # Blacklist by default unless approved, but store metadata for Web Review
            author_name = getattr(message.author, 'nick', None) or message.author.display_name
            add_to_meme_cache(
                file_hash, 
                cloud_url=attachment.url, 
                file_name=attachment.filename,
                user_id=str(message.author.id),
                user_name=author_name,
                timestamp=message.created_at.isoformat(),
                channel_id=str(message.channel.id),
                original_msg_id=str(message.id),
                attachment_id=str(attachment.id)
            )
            await discord_log(bot, f"🛡️ **Auto-Blacklisted pending review**: `{attachment.filename}` (Small size/Heuristic flag).", attachment.url)
            
            review_channel_id = get_config("review_channel_id")
            if review_channel_id:
                review_channel = bot.get_channel(int(review_channel_id))
                if review_channel:
                    url = get_config("album_url")
                    review_link = f"**[Review Queue](<{url}/review>)**" if url else "the web dashboard"
                    
                    content = (
                        f"🛡️ **New Item in Review Queue**\n"
                        f"Sent by: {message.author.mention}\n"
                        f"File: `{attachment.filename}`\n"
                        f"Hash: `{file_hash}`\n"
                        f"Please moderate this item on {review_link}.\n"
                        f"{attachment.url}"
                    )
                    msg = await review_channel.send(content=content)
                    await msg.add_reaction("✅")
                    await msg.add_reaction("❌")

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
            author_name = getattr(message.author, 'nick', None) or message.author.display_name
            log_photo_to_db(composite_id, message.channel.id, message.author.id, author_name, cloud_url, att.filename, message.created_at.isoformat())
            add_to_uploaded_cache(file_hash, cloud_url)
            bot.loop.create_task(process_media_eagerly(att, composite_id))
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
            user = None
            try:
                # Force an API call instead of relying on the local intent cache
                user = await interaction.guild.fetch_member(uid)
            except discord.NotFound:
                # Fallback to global user lookup if they left the server
                user = await bot.fetch_user(uid)
            
            if user:
                name = getattr(user, 'nick', None) or getattr(user, 'display_name', None) or user.name
                conn.execute("UPDATE photos SET user_name = ? WHERE user_id = ?", (name, str(uid)))
                conn.execute("UPDATE meme_cache SET user_name = ? WHERE user_id = ?", (name, str(uid)))
                count += 1
            
            # Respect Discord API rate limits by waiting 0.5s per member
            await asyncio.sleep(0.5)
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
                await handle_media_routing(message, silent=True)
                
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

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
        
    review_channel_id = get_config("review_channel_id")
    if not review_channel_id or payload.channel_id != int(review_channel_id):
        return
        
    emoji = str(payload.emoji)
    if emoji not in ["✅", "❌", "🚫"]:
        return
        
    channel = bot.get_channel(payload.channel_id)
    if not channel:
        return
        
    try:
        message = await channel.fetch_message(payload.message_id)
    except:
        return
        
    if message.author.id != bot.user.id or "New Item in Review Queue" not in message.content:
        return
        
    import re
    match = re.search(r'Hash:\s*`([a-f0-9]+)`', message.content)
    if not match:
        return
        
    file_hash = match.group(1)
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    try:
        if emoji == "✅":
            row = conn.execute("SELECT cloud_url, file_name, user_id, user_name, timestamp, channel_id, original_msg_id, attachment_id FROM meme_cache WHERE file_hash=?", (file_hash,)).fetchone()
            if not row:
                # Fallback for older legacy items
                row = conn.execute("SELECT cloud_url, file_name, user_id, user_name, timestamp FROM meme_cache WHERE file_hash=?", (file_hash,)).fetchone()

            if row:
                row = dict(row)
                orig_msg_id = row.get("original_msg_id")
                attach_id = row.get("attachment_id")
                
                # Determine the permanent message_id. Prefer Snowflake composite for deletion sync.
                if orig_msg_id and attach_id:
                    final_msg_id = f"{orig_msg_id}-{attach_id}"
                else:
                    final_msg_id = f"web-{file_hash[:12]}"

                channel_id = row.get("channel_id") or "web-review"
                conn.execute('''
                    INSERT OR IGNORE INTO photos (message_id, channel_id, user_id, user_name, timestamp, cloud_url, file_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (final_msg_id, channel_id, row["user_id"], row["user_name"], row["timestamp"], row["cloud_url"], row["file_name"]))
                
                conn.execute("INSERT OR IGNORE INTO uploaded_cache (file_hash, cloud_url, date_added) VALUES (?, ?, ?)",
                             (file_hash, row["cloud_url"], row["timestamp"]))
                
                # Ensure it's cached eagerly with the CORRECT final ID
                bot.loop.create_task(process_media_eagerly(row["cloud_url"], final_msg_id))
                
                conn.execute("DELETE FROM meme_cache WHERE file_hash=?", (file_hash,))
                conn.commit()
                
                msg_text = f"Approved item and added to vault."
                if row.get('file_name'):
                    msg_text = f"Approved and added `{row['file_name']}` to vault."
                await channel.send(f"✅ {msg_text}", delete_after=5.0)
            
        elif emoji in ["❌", "🚫"]:
            row = conn.execute("SELECT file_name FROM meme_cache WHERE file_hash=?", (file_hash,)).fetchone()
            file_name = row["file_name"] if row and row["file_name"] else "Item"
            
            conn.execute("UPDATE meme_cache SET cloud_url=NULL, file_name=NULL, user_id=NULL, user_name=NULL, timestamp=NULL WHERE file_hash=?", (file_hash,))
            conn.commit()
            
            await channel.send(f"❌ Discarded `{file_name}`.", delete_after=5.0)
            
    except Exception as e:
        print(f"Error handling reaction moderation: {e}")
    finally:
        conn.close()
        
    try:
        await message.delete()
    except:
        pass

@bot.event
async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
    """Deep synchronization: if a message is deleted on Discord, purge it from the vault!"""
    remove_all_photos_for_message(payload.message_id)
    await discord_log(bot, f"🗑️ Synchronized deletion: Message `{payload.message_id}` vanished from Discord. Cleaned up vault entry.")

@bot.event
async def on_raw_bulk_message_delete(payload: discord.RawBulkMessageDeleteEvent):
    """Deep synchronization for massive purges: handle bulk deletions efficiently."""
    for message_id in payload.message_ids:
        remove_all_photos_for_message(message_id)
    await discord_log(bot, f"🗑️ Bulk Synchronization: Processed {len(payload.message_ids)} deleted messages. Vault is clean.")

if __name__ == '__main__':
    if TOKEN and TOKEN != 'your_discord_bot_token_here':
        bot.run(TOKEN)
    else:
        print("WARNING: Please set DISCORD_TOKEN in the .env file")

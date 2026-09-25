"""Mirror new messages between two Discord text channels. See README.md."""

import asyncio
import logging
import os

import discord

log = logging.getLogger("mirror")


class MirrorBot(discord.Client):
    def __init__(self, source_id: int, destination_id: int):
        intents = discord.Intents(guilds=True, guild_messages=True, message_content=True)
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.source_id = source_id
        self.destination_id = destination_id
        self.destination = None
        self.mirror_lock = asyncio.Lock()

    async def setup_hook(self):
        source = await self.fetch_channel(self.source_id)
        self.destination = await self.fetch_channel(self.destination_id)
        if not all(isinstance(c, discord.TextChannel) for c in (source, self.destination)):
            raise ValueError("Both channel IDs must refer to server text channels.")

    async def on_ready(self):
        log.info("Logged in as %s; mirroring %s -> %s", self.user, self.source_id, self.destination_id)

    async def on_message(self, message: discord.Message):
        if message.channel.id != self.source_id or message.author == self.user:
            return

        # Keep each message's text and attachments together during bursts.
        async with self.mirror_lock:
            try:
                name = discord.utils.escape_markdown(message.author.display_name)
                content = f"**{name}**\n{message.content}"
                if not message.content and not message.attachments:
                    content += f"[View original message](<{message.jump_url}>)"

                # Users can send messages longer than a bot's 2,000-character limit.
                for offset in range(0, len(content), 2000):
                    await self.destination.send(content[offset:offset + 2000])

                for attachment in message.attachments:
                    if attachment.size > self.destination.guild.filesize_limit:
                        await self.destination.send(
                            f"Attachment exceeds upload limit: <{attachment.url}>"
                        )
                        continue
                    file = None
                    try:
                        file = await attachment.to_file()
                        await self.destination.send(file=file)
                    except discord.HTTPException:
                        log.warning("Could not copy attachment %s; sending its link", attachment.id)
                        await self.destination.send(f"Attachment: <{attachment.url}>")
                    finally:
                        if file is not None:
                            file.close()
            except discord.HTTPException:
                log.exception("Failed to mirror message %s", message.id)


def main():
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set the DISCORD_TOKEN environment variable first.")
    try:
        source_id = int(os.environ["SOURCE_CHANNEL_ID"])
        destination_id = int(os.environ["DESTINATION_CHANNEL_ID"])
        if source_id <= 0 or destination_id <= 0 or source_id == destination_id:
            raise ValueError
    except (KeyError, ValueError):
        raise SystemExit("Set SOURCE_CHANNEL_ID and DESTINATION_CHANNEL_ID to different positive IDs.")
    MirrorBot(source_id, destination_id).run(token)


if __name__ == "__main__":
    main()

from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
import requests
import discord
from discord import (
    Member,
    User,
    app_commands,
    Client,
    Intents,
    Message,
    Reaction,
)
from commands.mod_commands import ModCommands
from commands.viewer_commands import ViewerCommands
from commands.manager_commands import ManagerCommands
from config import Config
from controllers.sub_controller import SubController
from db import DB
from threading import Thread


discord.utils.setup_logging(level=logging.INFO, root=True)

COOL_URL = "http://localhost:3000/publish-cool"
COOL_ID = Config.CONFIG["Discord"]["CoolEmojiID"]
AUTH_TOKEN = Config.CONFIG["Server"]["AuthToken"]
UNCOOL_ID = Config.CONFIG["Discord"]["UncoolEmojiID"]
STREAM_CHAT_ID = int(Config.CONFIG["Discord"]["StreamChannel"])
WELCOME_CHAT_ID = int(Config.CONFIG["Discord"]["WelcomeChannel"])
PENDING_REWARDS_CHAT_ID = int(Config.CONFIG["Discord"]["PendingRewardChannel"])
GUILD_ID = int(Config.CONFIG["Discord"]["GuildID"])
CROWD_MUTE_EMOJI_ID = int(Config.CONFIG["Discord"]["CrowdMuteEmojiID"])
CROWD_MUTE_THRESHOLD = int(Config.CONFIG["Discord"]["CrowdMuteThreshold"])
CROWD_MUTE_DURATION = int(Config.CONFIG["Discord"]["CrowdMuteDuration"])
SERVER_SUBSCRIPTION_MESSAGE_TYPE = 25


class RaffleBot(Client):
    def __init__(self):
        intents = Intents.default()
        intents.members = True
        intents.message_content = True
        intents.guilds = True

        # initialize DB for the first time
        DB()

        super().__init__(intents=intents)

    async def on_ready(self):
        logging.info(f"Logged in as {self.user} (ID: {self.user.id})")
        # guild = discord.Object(id=GUILD_ID)
        # tree.clear_commands(guild=guild)
        # tree.copy_global_to(guild=guild)
        # await tree.sync(guild=guild)
        SubController(self).send_count.start()

    async def on_message(self, message: Message):
        # Don't respond to ourselves
        if message.author == self.user:
            return

        # Server Subscription message
        if (
            message.channel.id == WELCOME_CHAT_ID
            and message.type.value == SERVER_SUBSCRIPTION_MESSAGE_TYPE
        ):
            await SubController.subscribe(message, self)

        # Only look in the active stream channel
        if message.channel.id == STREAM_CHAT_ID:
            DB().accrue_channel_points(message.author.id, message.author.roles)
            cool = COOL_ID in message.content
            uncool = UNCOOL_ID in message.content
            if cool and not uncool:
                Thread(
                    target=publish_cool,
                    args=(1,),
                ).start()
            elif uncool and not cool:
                Thread(
                    target=publish_cool,
                    args=(-1,),
                ).start()

    async def on_reaction_add(self, reaction: Reaction, user: Member | User):
        if isinstance(reaction.emoji, str):
            return
        if reaction.emoji.id != CROWD_MUTE_EMOJI_ID:
            return
        if reaction.count < CROWD_MUTE_THRESHOLD:
            return

        if reaction.count == CROWD_MUTE_THRESHOLD:
            mute_reason = (
                "been crowd muted for 10 minutes, likely due to asking:"
                " "
                " 1. An easily Googleable question"
                " "
                " 2. A question about aim (see <#1056639643443007659>)"
                " "
                " 3. A question answered directly within our <#1035739990413545492>."
            )
            await reaction.message.author.timeout(
                timedelta(minutes=CROWD_MUTE_DURATION), reason=f"You have {mute_reason}"
            )
            await reaction.message.reply(f"This user has {mute_reason}")


client = RaffleBot()
tree = app_commands.CommandTree(client)


@client.event
async def on_guild_join(guild):
    tree.clear_commands(guild=guild)
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)


def publish_cool(cool: int):
    payload = {"cool": cool}
    response = requests.post(
        url=COOL_URL, json=payload, headers={"x-access-token": AUTH_TOKEN}
    )
    if response.status_code != 200:
        LOG.error(f"Failed to publish sub summary: {response.text}")

async def main():
    async with client:
        tree.add_command(ModCommands(tree, client))
        tree.add_command(ViewerCommands(tree, client))
        tree.add_command(ManagerCommands(tree, client))
        await client.start(Config.CONFIG["Discord"]["Token"])


if __name__ == "__main__":
    asyncio.run(main())

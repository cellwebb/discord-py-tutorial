import os
import logging
import time

import discord
import openai
import tiktoken


token = os.getenv("DISCORD_HILLBOT_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'{time.strftime("%I:%M:%S %p")} - We have logged in as {client.user}')

@client.event
async def on_message(message):
    print(f'{time.strftime("%I:%M:%S %p")} - Message from {message.author} in #{message.channel}: {message.content}')

    if message.author == client.user:
        return

    if message.content.startswith('!davefacts'):
        with open('davefacts.txt', 'a') as f:
            new_fact = message.content.replace('!davefacts', '').strip()
            f.write('- ' + new_fact + '\n')
        await message.channel.send('Thanks for telling me more about Dave!')
        return

    if 'hillbot' in message.content.lower() or client.user.mentioned_in(message):
        with open('system.txt') as f:
            system_msg = f.read()
        with open('davefacts.txt') as f:
            davefacts = f.read()

        print('pulling conversation history...')
        from config import channel_history_limit
        conversation_history_generator = message.channel.history(limit=channel_history_limit)
        conversation_history = []
        async for prev_message in conversation_history_generator:
            conversation_history.append(
                {"role": "assistant" if prev_message.author == client.user else "user",
                 "content": prev_message.content})
        conversation_history.reverse()

        # break down long messages
        i = 0
        while i < len(conversation_history):
            if len(conversation_history[i]["content"]) > 2000:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
                tokenized_content = encoding.encode(conversation_history[i]["content"])
                num_tokens = len(tokenized_content)
                if num_tokens > 2000:
                    conversation_history[i]["content"] = ''.join(tokenized_content[:2000])
                    conversation_history.insert(
                        i + 1,
                        {"role": conversation_history[i]["role"],
                         "content": tokenized_content[2000:]}
                    )
            i += 1

        messages = [{"role": "system", "content": system_msg + '\n' + davefacts}]
        messages.extend(conversation_history)
        messages[-1]["content"] = "Reply in Dave's voice. " + messages[-1]["content"]

        print(messages)
        print('calling openai api...')
        from config import max_openai_api_attempts, temperature
        for n_attempts in range(1, max_openai_api_attempts):
            try:
                chat_completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=temperature
                )
                response = chat_completion.choices[0].message.content
                break
            except (openai.error.RateLimitError, openai.error.ServiceUnavailableError) as err:
                wait_period = 30 * n_attempts
                await message.channel.send(f"{err} I'll try again in {wait_period} seconds!")
                time.sleep(wait_period)
            except openai.error.APIError as err:
                await message.channel.send(f"{err} I'll try re-connecting to the API!")
                time.sleep(5)
                openai.api_key = os.getenv("OPENAI_API_KEY")
                time.sleep(5)
        else:
            response = "The server is busy! Please try again later!"
        await message.channel.send(response)


handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
client.run(token, log_handler=handler)

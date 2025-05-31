# Professional Leveling Discord Bot

This is a Discord bot with a professional leveling system, similar to AmariBot.

## Features

- XP gain on message activity
- Leveling up
- Rank checking
- Server leaderboard
- Customizable settings (planned)

## Setup

1.  **Prerequisites:**
    *   Python 3.8 or higher
    *   A Discord Bot Token (You can get one from the [Discord Developer Portal](https://discord.com/developers/applications))

2.  **Clone the repository (or download the files):**
    ```bash
    git clone <repository_url> # Or download and extract the ZIP
    cd <repository_folder>
    ```

3.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    ```
    Activate it:
    *   Windows: `.\venv\Scripts\activate`
    *   macOS/Linux: `source venv/bin/activate`

4.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configure the Bot Token:**
    *   Rename the `.env.example` file (if provided) to `.env` or create a new file named `.env` in the root directory of the project.
    *   Open the `.env` file and add your Discord Bot Token:
        ```
        DISCORD_BOT_TOKEN=YOUR_ACTUAL_BOT_TOKEN_HERE
        ```
        Replace `YOUR_ACTUAL_BOT_TOKEN_HERE` with your bot's token.

## Running the Bot

Once you have completed the setup, you can run the bot using the following command:

```bash
python bot.py
```

## Bot Commands

*   `!rank [member]` - Displays your rank or the rank of the mentioned member.
*   `!leaderboard` - Shows the server's top 10 users by XP.

## Project Structure

```
discord-leveling-bot/
├── .env                # Stores environment variables (like your bot token)
├── bot.py              # Main bot script
├── requirements.txt    # Python package dependencies
├── cogs/               # Directory for bot extensions (cogs)
│   ├── __init__.py
│   └── leveling_system.py # Cog for the leveling system logic
└── leveling.db         # SQLite database for storing user levels and XP
└── README.md           # This file
```

## Customization (Future)

*   Setting custom XP per message.
*   Setting cooldowns for XP gain.
*   Configuring level-up announcement channels.
*   Role rewards for reaching certain levels.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.
Goal                                                                                                                                                              
                                                                                                                                                                    
  Bot runs in a container, connects to Telegram via long polling, responds to /scorepoll in any chat with a fixed message. No DB, no voting logic yet.              
                  
  Scope (in)                                                                                                                                                        
                  
  - Project layout matching docs/STRUCTURE.md for the files we actually need now                                                                                    
  - /scorepoll and /start handlers returning fixed text
  - Container image + compose.yaml running just the bot service                                                                                                     
  - .env based config loading (token + log level only for now)                                                                                                      
                                                                                                                                                                    
  Scope (deferred)                                                                                                                                                  
                                                                                                                                                                    
  - PostgreSQL service, db.py, repositories, models, migrations                                                                                                     
  - voting_methods/, rendering.py, callbacks.py, hashing.py
  - /closepoll, inline keyboards, DM ballot flow                                                                                                                    
  - Tests (no logic worth testing yet)                                                                                                                              
                                                                                                                                                                    
  Steps                                                                                                                                                             
                                                                                                                                                                    
  1. Dependencies — update pyproject.toml to add python-telegram-bot[ext] and python-dotenv. Lock with uv sync.                                                     
  2. Source layout — create src/voting_bot/ with:
    - __init__.py                                                                                                                                                   
    - config.py — load+validate TELEGRAM_BOT_TOKEN, LOG_LEVEL from env (skip DB/HMAC vars until they're used; per CLAUDE.md, no scaffolding ahead of need).
    - handlers/__init__.py, handlers/commands.py — /start and /scorepoll returning fixed strings.                                                                   
    - main.py — build Application, register handlers, run_polling().                                                                                                
  3. Entry point — switch pyproject.toml to expose voting-bot = "voting_bot.main:main" and delete the top-level main.py placeholder.                                
  4. Containerfile — Python 3.12 slim base, install uv, copy project, uv sync --frozen, run uv run voting-bot.                                                      
  5. compose.yaml — single bot service for now, env file .env, restart: unless-stopped. Leave a comment noting db will be added later.                              
  6. .env.example — trim to just TELEGRAM_BOT_TOKEN and LOG_LEVEL for this milestone (or keep extras commented out — your call).                                    
  7. Smoke test — podman compose up --build, message the bot /scorepoll in a test group, confirm fixed reply and clean shutdown on Ctrl-C.                          
                                                                                                                                                                    
  Open questions                                                                                                                                                    
                                                                                                                                                                    
  - Do you already have a bot token from @BotFather, or should the plan include that step?                                                                          
  - Are you deploying to the Hetzner VPS as part of this milestone, or is "runs locally under Podman" enough to call it done?
  - Trim .env.example now, or keep the full set so it doesn't churn next milestone?

  I have a bot token already, but I won't expose it to you. I think we can just run locally under podman for now. We can keep .env.example for now. Please go ahead 
   with implementation, thanks! 
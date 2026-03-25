import yaml
import os
import logging
from dotenv import load_dotenv

def load_config(config_path="config.yaml"):
    """Loads configuration from yaml and environment variables."""
    # Load .env file
    load_dotenv()
    
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    
    # Token must be in .env for safety
    config["token"] = os.getenv("DISCORD_TOKEN")
    
    return config

def setup_logging(config):
    """Sets up logging configuration."""
    log_cfg = config.get("logging", {})
    level_str = log_cfg.get("level", "INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    filename = log_cfg.get("file", "bot.log")

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(filename),
            logging.StreamHandler()
        ]
    )

import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("steam_web_api_token")
steamID = "765611981402004412"

response = requests.get(f"https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/?key={api_key}&steamids={steamID}").json()
print(all(["response" in response, "players" in response["response"], response["response"]["players"]]))
import requests
from rich.console import Console
from dotenv import load_dotenv
from os import getenv
from pydantic import BaseModel, Field
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


console = Console()
load_dotenv()

class TrainInfo(BaseModel):
    train_number: str = Field(..., description="Train number")
    departure_time: str = Field(..., description="Departure time in YYYYMMDDTHHMMSS format")
    destination: str = Field(..., description="Destination station")
    physical_mode: str = Field(..., description="Physical mode")

    # Formatting the departure time for better readability
    def formatted_departure_time(self) -> str:
        # Convertir le string en objet datetime
        dt = datetime.strptime(self.departure_time, "%Y%m%dT%H%M%S")
        # Formatter pour l'affichage
        return dt.strftime("%H:%M on %d/%m/%Y")


def fetch_train_info(api_key: str, train_station: str) -> list[TrainInfo]:
    url = f"https://api.sncf.com/v1/coverage/sncf/stop_areas/{train_station}/departures"
    headers = {"Authorization": api_key}
    params = {"count": 10}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    
    return [TrainInfo(
        train_number=departure['display_informations']['trip_short_name'],
        departure_time=departure['stop_date_time']['departure_date_time'],
        destination=departure['display_informations']['direction'],
        physical_mode=departure['display_informations']['physical_mode']
    )
    for departure in data['departures']]



def main():
    api_key = getenv("SNCF_API_KEY")
    if not api_key:
        console.print("[red]Error: SNCF_API_KEY not found in environment variables.[/red]")
        return
    
    train_station = "stop_area:SNCF:87386649" 
    try:
        train_infos = fetch_train_info(api_key, train_station)
        for info in train_infos:
            console.print(f"[green]{info.physical_mode}[/green] to [blue]{info.destination}[/blue] departs at [yellow]{info.formatted_departure_time()}[/yellow]")
    except requests.HTTPError as e:
        console.print(f"[red]HTTP Error: {e}[/red]")
        return
    
    # filter for specific destination
    specific_destination = "Paris Saint-Lazare (Paris)"
    filtered_trains = [info for info in train_infos 
                       if info.destination == specific_destination and info.physical_mode != "Bus"]
    console.print(f"\n[bold]Number of Trains to {specific_destination}:[/bold] {len(filtered_trains)}")

    slack_token = getenv("SLACK_BOT_TOKEN")
    
    client = WebClient(token=slack_token)

    try:
        response = client.chat_postMessage(
            channel="C0XXXXXX",
            text="Hello from your app! :tada:"
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["error"]    # str like 'invalid_auth', 'channel_not_found'




if __name__ == "__main__":
    main()

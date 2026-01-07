import requests
from rich.console import Console
from dotenv import load_dotenv
from os import getenv
from pydantic import BaseModel, Field
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from zoneinfo import ZoneInfo

console = Console()
load_dotenv()

class Departure(BaseModel):
    origin: str
    destination: str
    aimed_departure_time: str
    expected_departure_time: str
    status: str
    train_number: int
    delay: int = 0


def fetch_next_departures(api_key: str, station_code: str) -> list[Departure]:
    url = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"

    headers = {
        "apiKey": api_key,
    }

    params = {
        "MonitoringRef": station_code,
    }

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    departures = []
    visits = (
        data.get("Siri", {})
        .get("ServiceDelivery", {})
        .get("StopMonitoringDelivery", [{}])[0]
        .get("MonitoredStopVisit", [])
    )

    def parse_time(ts):
        if not ts:
            return None
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(PARIS_TZ)

    def format_time(dt):
        return dt.strftime("%H:%M") if dt else "—"

    def minutes_delay(aimed, expected):
        if not aimed or not expected:
            return 0
        return int((expected - aimed).total_seconds() / 60)

    for visit in visits:
        mvj = visit.get("MonitoredVehicleJourney", {})
        call = mvj.get("MonitoredCall", {})

        aimed_dep = parse_time(call.get("AimedDepartureTime"))
        expected_dep = parse_time(call.get("ExpectedDepartureTime"))

        status_dep = call.get("DepartureStatus", "").lower()
        status_arr = call.get("ArrivalStatus", "").lower()

        cancelled = "cancel" in status_dep or "cancel" in status_arr

        delay = minutes_delay(aimed_dep, expected_dep)

        departures.append(
            Departure(
                origin=mvj.get("DirectionRef", {}).get("value", "—"),
                destination=mvj.get("DestinationName", [{}])[0].get("value", "—"),
                aimed_departure_time=format_time(aimed_dep),
                expected_departure_time=format_time(expected_dep),
                status="Cancelled" if cancelled else "On time" if delay == 0 else f"Delayed",
                train_number=mvj.get("VehicleJourneyName", [{}])[0].get("value", "—"),
                delay=delay,
            )
        )
    return departures

def format_departure_info(departures: list[Departure]) -> str:
    emoji_status = {
        "On time": "✅",
        "Cancelled": "❌",
        "Delayed": "⏰",
    }
    

    lines = []
    for dep in departures:
        msg = ""
        msg += f"{emoji_status.get(dep.status, '')} Train {dep.train_number} to {dep.destination} | "
        msg += f"{dep.aimed_departure_time} → {dep.expected_departure_time} (+{dep.delay} min)" if dep.delay > 0 else f"{dep.aimed_departure_time} "
        lines.append(msg)

    return "\n".join(lines)


def main():
    api_key = getenv("IDF_API_KEY")
    if not api_key:
        console.print("[red]Error: IDF_API_KEY not found in environment variables.[/red]")
        return
    
    train_station = "STIF:StopArea:SP:47966:" 
    try:
        next_departures = fetch_next_departures(api_key, train_station)
    except requests.HTTPError as e:
        console.print(f"[red]HTTP Error: {e}[/red]")
        return
    
    # sort and display all departures
    sorted_trains = sorted(next_departures, key=lambda x: x.expected_departure_time)

    msg = format_departure_info(sorted_trains)
    console.print(msg)

    # filter for specific destination
    specific_destination = "Paris Saint-Lazare"
    filtered_trains = [departure for departure in sorted_trains 
                       if departure.destination == specific_destination]

    console.print(f"\n[bold]Number of Trains to {specific_destination}:[/bold] {len(filtered_trains)}")

    msg = format_departure_info(filtered_trains)
    console.print(msg)
    return

    slack_token = getenv("SLACK_BOT_TOKEN")
    channel_id = getenv("CHANNEL_ID")
    if not slack_token:
        console.print("[red]Error: SLACK_BOT_TOKEN not found in environment variables.[/red]")
        return
    
    # A nice formated message for Slack with MRKDWN
    message_text = f"*Next Trains to {specific_destination}:* \n"
    message_text += "```"
    message_text += format_departure_info(filtered_trains)
    message_text += "```"

    
    if not channel_id:
        console.print("[red]Error: CHANNEL_ID not found in environment variables.[/red]")
        return
    
    client = WebClient(token=slack_token)

    try:
        response = client.chat_postMessage(
            channel=channel_id, 
            text=message_text
        )
    except SlackApiError as e:
        # You will get a SlackApiError if "ok" is False
        assert e.response["error"]    # str like 'invalid_auth', 'channel_not_found'


if __name__ == "__main__":
    main()

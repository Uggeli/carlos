from typing import Any
import requests

api_endpoint = "http://192.168.50.202:1234"

def api_talk(message: str, url: str) -> dict:
    """Send Message to API endpoint and return response."""
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(f"{api_endpoint}/{url}", headers=headers, json=message)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API error: {response.status_code} - {response.text}")
    
def curate(message: str) -> dict[str, Any]:
    """Send Message to curator model"""
    curator_message = {
        "model": "curator",
        "messages": [{"role": "user", "content": message}],
        "temperature": 0.5
    }
    response = api_talk(curator_message, url="v1/chat/completions")
    return response

def generate_n_outputs(message: str, output_count: int = 10) -> None:
    """Generate outputs for the curator model."""
    responses = []
    for i in range(output_count):
        response = curate(message)
        responses.append(response)
    with open("curator_outputs.json", "w") as f:
        f.write("Question: " + message + "\n")
        import json
        json.dump(responses, f, indent=2)

if __name__ == "__main__":
    generate_n_outputs("Wow, what a week. I finally finished the main deployment for Project Hydra, so that's a relief. Speaking of which, did we ever decide on a name for the new analytics dashboard we were discussing last month?", output_count=10)
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
    """Send Message to curator twin model"""
    scripe_message = {
        "model": "scripe",
        "messages": [
            {"role": "system", "content": "The user input is a QUESTION. Questions do not contain new information to store. Output empty JSON: {}, The user input is a STATEMENT containing potential new information. Analyze and store only explicit facts mentioned."},
            {"role": "user", "content": message}],
        "temperature": 0.5
    }

    librarian_message = {
        "model": "librarian",
        "messages": [
            # {"role": "system", "content": "The user is asking for information. Generate queries to find existing data that answers their question. The user provided new information. Generate queries to find related existing context and check for duplicates."},
            {"role": "user", "content": message}],
        "temperature": 0.5
    }

    scripe_response = api_talk(scripe_message, url="v1/chat/completions")
    librarian_response = api_talk(librarian_message, url="v1/chat/completions")

    return {
        "scripe_response": scripe_response,
        "libarian_response": librarian_response
    }

def generate_n_outputs(message: str, output_count: int = 10) -> None:
    """Generate outputs for the curator twin model."""
    responses = []
    for _ in range(output_count):
        response = curate(message)
        responses.append(response)
    with open("twin_curator_outputs.json", "w") as f:
        f.write("Question: " + message + "\n")
        import json
        json.dump(responses, f, indent=2)

if __name__ == "__main__":
    generate_n_outputs("Wow, what a week. I finally finished the main deployment for Project Hydra, so that's a relief. Speaking of which, did we ever decide on a name for the new analytics dashboard we were discussing last month?", output_count=10)
import json
import os
import sys
sys.path.insert(0, os.getcwd())    # for command line


import carlos


def test_curator_output():
    """Test the curator output for a sample message."""
    carlos_instance = carlos.Carlos(username="curator_test")
    message = "Have i ever been in France?"
    
    curator_message = {
        "model": "carlos",
        "messages": [
            {"role": "system", "content": carlos_instance.curator_system_prompt},
            {"role": "user", "content": message}
        ],
        "response_format": carlos_instance.curator_schema,
        "temperature": 0,
        "max_tokens": -1,
        "stream": False
    }
    response = carlos_instance._api_talk(curator_message, url="v1/chat/completions")

    assert "choices" in response
    assert len(response["choices"]) > 0
    assert "message" in response["choices"][0]
    assert "content" in response["choices"][0]["message"]

    json_content = json.loads(response["choices"][0]["message"]["content"])
    # '{"fresh_data_to_store": {"entities": [{"name": "France", "type": "location"}], "user_state_updates": {"active_projects": {}, "preferences": {}, "current_mood": "curious", "context_flags": ["travel_history"]}} , "context_retrieval_queries": [{"purpose": "Check if France is already in the user\'s travel history.", "collection": "user_state", "query": {"travel_history": "France"}, "priority": 5}, {"purpose": "Find any past conversations where travel to France was mentioned as a goal or plan.", "collection": "conversations", "query": {"semantic_tags": "travel_planning", "entities": "France"}, "priority": 4}], "context_focus": {"primary_theme": "Travel history and experiences in France." , "emotional_context": "information"} , "curiosity_analysis": {"user_intent": "Inquire about past travel to France.", "conversation_trajectory": "follow_up", "implied_questions": ["Have I been in France before?"]}}'
    assert "fresh_data_to_store" in json_content
    assert "context_retrieval_queries" in json_content

    context_queries = json_content["context_retrieval_queries"]
    fresh_data = json_content["fresh_data_to_store"]
    assert isinstance(context_queries, list)
    assert isinstance(fresh_data, dict)




if __name__ == "__main__":
    test_curator_output()

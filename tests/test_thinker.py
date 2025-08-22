import os
import sys
sys.path.insert(0, os.getcwd())    # for command line


import carlos


def test_thinker_output():
    """Test the thinker output for a sample message."""
    carlos_instance = carlos.Carlos(username="thinker_test")
    message = "Have i ever been in France?"
    response = carlos_instance.chat(message)
    assert isinstance(response, dict), "Response should be a dictionary"
    assert len(response) > 0, "Response should not be empty"

if __name__ == "__main__":
    test_thinker_output()
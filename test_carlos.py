import os
import time
import requests
import json

BASE = os.getenv("TEST_CARLOS_BASE", "http://localhost:5000")


def send_message(text, debug=False):
    """Send a message to Carlos and return the response."""
    endpoint = "/api/debug_chat" if debug else "/api/chat"
    body = {"message": text}
    r = requests.post(f"{BASE}{endpoint}", json=body, timeout=120)
    r.raise_for_status()
    return r.json()


def test_secret_handshake():
    """Test Carlos's ability to recall specific information after noise."""
    print("[TEST] Secret Handshake: recall project codename after noise")
    
    # Introduce unique fact
    print("  Setting up secret project...")
    res = send_message("Hi there. By the way, my secret project codename is 'Blue Falcon'.")
    print(f"  Carlos: {res.get('reply', '<no reply>')[:100]}...")
    
    # Add chat noise to test memory retention
    print("  Adding noise messages...")
    for i in range(20):  # Reduced for faster testing
        send_message(f"Tell me a random fact about the number {i}.")
        if i % 5 == 0:
            print(f"    sent {i} noise messages...")
    
    # Test recall
    print("  Testing recall...")
    res = send_message("A while back, I mentioned a secret project I was working on. Do you remember its codename?")
    reply = res.get('reply', '<no reply>')
    print(f"  Carlos: {reply}")
    
    # Check if 'Blue Falcon' is mentioned
    success = 'blue falcon' in reply.lower() or 'blue-falcon' in reply.lower()
    print(f"  ✅ SUCCESS: Recalled codename" if success else f"  ❌ FAILED: Did not recall codename")
    return success


def test_evolving_preferences():
    """Test Carlos's ability to track changing preferences."""
    print("[TEST] Evolving Preferences: latest preference recall")
    
    # Initial preference
    print("  Setting initial preference...")
    send_message("For my new website design, I'm thinking of using a very dark, black-and-gray theme.")
    
    # Add some noise
    for i in range(10):  # Reduced for faster testing
        send_message(f"What font pairs well with a tech blog? Question #{i}")
    
    # Change preference
    print("  Changing preference...")
    send_message("After looking at examples, the dark theme is too gloomy. I'm now leaning towards a bright, minimalist white theme.")
    
    # More noise
    for i in range(10):
        send_message(f"What grid layout do you recommend for a portfolio? Question #{i}")
    
    # Test preference recall
    print("  Testing preference recall...")
    res = send_message("Okay, I'm ready to start. Based on our discussion, what color should the main background of the site be?")
    reply = res.get('reply', '<no reply>')
    print(f"  Carlos: {reply}")
    
    # Check if latest preference (white/bright) is mentioned
    success = any(word in reply.lower() for word in ['white', 'bright', 'light', 'minimalist'])
    dark_mentioned = any(word in reply.lower() for word in ['dark', 'black', 'gray'])
    
    if success and not dark_mentioned:
        print("  ✅ SUCCESS: Recalled latest preference (white/bright)")
        return True
    elif dark_mentioned:
        print("  ❌ FAILED: Recalled old preference (dark)")
        return False
    else:
        print("  ⚠️  UNCLEAR: No clear preference mentioned")
        return False


def test_story_arc():
    """Test Carlos's ability to maintain story consistency across many interactions."""
    print("[TEST] Story Arc: summarization consistency across long story")
    
    # Start the story
    print("  Starting story...")
    send_message("Let's write a story. It begins with a detective named Alex finding a strange pocket watch.")
    
    # Add story elements with noise
    for i in range(8):  # Reduced for faster testing
        send_message(f"Add a short scene about Alex investigating clues. Scene {i}.")
    
    # Major plot point 1
    print("  Adding major plot point 1...")
    send_message("Alex discovers the watch can stop time for 10 seconds.")
    
    # More story elements
    for i in range(8, 16):
        send_message(f"Add a twist involving the watch's side-effects. Twist {i}.")
    
    # Major plot point 2
    print("  Adding major plot point 2...")
    send_message("A mysterious villain, known only as 'The Clockmaker', tries to steal the watch from Alex.")
    
    # More story elements
    for i in range(16, 24):
        send_message(f"Describe a chase scene through the city. Scene {i}.")
    
    # Climax
    print("  Adding climax...")
    send_message("In a final confrontation, Alex uses the watch to trap The Clockmaker in a time loop.")
    
    # Test story recall
    print("  Testing story summarization...")
    res = send_message("Summarize the entire story we've created from beginning to end.")
    reply = res.get('reply', '<no reply>')
    print(f"  Carlos: {reply}")
    
    # Check if key story elements are present
    key_elements = ['alex', 'detective', 'pocket watch', 'time', 'clockmaker']
    present_elements = [elem for elem in key_elements if elem in reply.lower()]
    
    success = len(present_elements) >= 4  # At least 4 out of 5 key elements
    print(f"  Key elements found: {present_elements}")
    print(f"  ✅ SUCCESS: Story coherence maintained" if success else f"  ❌ FAILED: Story coherence lost")
    return success


def test_debug_functionality():
    """Test the debug endpoint and information retrieval."""
    print("[TEST] Debug Functionality: detailed pipeline inspection")
    
    res = send_message("What color is my car?", debug=True)
    debug_data = res.get('debug', {})
    
    print("  Debug data sections available:")
    for section in debug_data.keys():
        print(f"    - {section}")
    
    # Check curator output
    curator = debug_data.get('curator', {})
    if 'context_retrieval_queries' in curator or 'investigation_queries' in curator:
        queries = curator.get('context_retrieval_queries', []) or curator.get('investigation_queries', [])
        print(f"  Curator generated {len(queries)} queries")
        for i, query in enumerate(queries[:3]):  # Show first 3
            print(f"    Query {i+1}: {query.get('purpose', 'No purpose')[:60]}...")
    
    # Check context assembly
    context = debug_data.get('context', {})
    if 'retrieved_context' in context:
        retrieved = context['retrieved_context']
        if 'queries_executed' in retrieved:
            executed_queries = retrieved['queries_executed']
            print(f"  Context assembly executed {len(executed_queries)} queries")
            total_results = sum(q.get('count', 0) for q in executed_queries)
            print(f"  Total database results: {total_results}")
    
    # Check thinker output
    thinker = debug_data.get('thinker', {})
    if 'situation_summary' in thinker:
        summary = thinker['situation_summary']
        print(f"  Thinker situation summary: {summary[:80]}...")
    
    success = bool(curator and context and thinker)
    print(f"  ✅ SUCCESS: Debug pipeline working" if success else f"  ❌ FAILED: Debug pipeline incomplete")
    return success


def test_database_queries():
    """Test that database queries are being generated and executed properly."""
    print("[TEST] Database Queries: curator query generation and execution")
    
    # Ask a question that should trigger database lookups
    res = send_message("Do you remember what I told you about my favorite color?", debug=True)
    debug_data = res.get('debug', {})
    
    # Check if queries were generated
    curator = debug_data.get('curator', {})
    queries = curator.get('context_retrieval_queries', []) or curator.get('investigation_queries', [])
    
    print(f"  Curator generated {len(queries)} queries")
    
    # Check if queries were executed
    context = debug_data.get('context', {})
    executed_queries = context.get('retrieved_context', {}).get('queries_executed', [])
    
    print(f"  {len(executed_queries)} queries were executed")
    
    # Analyze query results
    for i, query in enumerate(executed_queries):
        collection = query.get('collection', 'unknown')
        count = query.get('count', 0)
        purpose = query.get('purpose', 'No purpose')
        print(f"    Query {i+1}: {collection} -> {count} results ({purpose[:40]}...)")
    
    success = len(queries) > 0 and len(executed_queries) > 0
    print(f"  ✅ SUCCESS: Queries generated and executed" if success else f"  ❌ FAILED: Query system not working")
    return success


def test_memory_storage():
    """Test that Carlos stores and retrieves information correctly."""
    print("[TEST] Memory Storage: information persistence")
    
    # Store some information
    unique_fact = f"My lucky number is 42 and today is test day {int(time.time())}"
    print(f"  Storing: {unique_fact}")
    send_message(f"I want to tell you something important: {unique_fact}")
    
    # Add some noise
    for i in range(5):
        send_message(f"What's the weather like? Random question {i}")
    
    # Try to retrieve the information
    res = send_message("What was that important thing I told you earlier about my lucky number?", debug=True)
    reply = res.get('reply', '')
    
    # Check if the information was retrieved
    success = '42' in reply and 'test day' in reply
    print(f"  Carlos: {reply[:100]}...")
    print(f"  ✅ SUCCESS: Information retrieved" if success else f"  ❌ FAILED: Information not retrieved")
    
    # Also check debug info for database activity
    debug_data = res.get('debug', {})
    executed_queries = debug_data.get('context', {}).get('retrieved_context', {}).get('queries_executed', [])
    db_activity = len(executed_queries) > 0
    print(f"  Database queries executed: {len(executed_queries)}")
    
    return success and db_activity


if __name__ == "__main__":
    print("🤖 Carlos Memory and Functionality Tests")
    print("=" * 50)
    
    results = {}
    
    try:
        # Test basic functionality first
        results['debug'] = test_debug_functionality()
        print()
        
        results['queries'] = test_database_queries()
        print()
        
        results['storage'] = test_memory_storage()
        print()
        
        # Test memory capabilities
        results['handshake'] = test_secret_handshake()
        print()
        
        results['preferences'] = test_evolving_preferences()
        print()
        
        results['story'] = test_story_arc()
        print()
        
    except requests.HTTPError as e:
        print(f"❌ HTTP Error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            print(f"   Details: {error_detail}")
        except:
            print(f"   Raw response: {e.response.text}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{test_name.upper():12} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! Carlos is working correctly.")
    elif passed >= total * 0.7:
        print("⚠️  Most tests passed. Some issues to investigate.")
    else:
        print("🚨 Many tests failed. Significant issues detected.")
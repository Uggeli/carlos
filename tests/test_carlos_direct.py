import os
import time
import json
import logging
from datetime import datetime
import sys

# Add parent directory to path so we can import carlos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carlos import Carlos

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Setup detailed logging
TEST_RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOGS_DIR, f"carlos_direct_test_{TEST_RUN_ID}.log")

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger('carlos_test')

class DetailedCarlosLogger:
    """Wrapper around Carlos to log all internal operations"""
    
    def __init__(self, username):
        self.carlos = Carlos(username=username)
        self.username = username
        self.test_log_dir = os.path.join(LOGS_DIR, f"test_run_{TEST_RUN_ID}")
        os.makedirs(self.test_log_dir, exist_ok=True)
        
    def log_to_file(self, filename, data, description=""):
        """Log data to a specific file"""
        filepath = os.path.join(self.test_log_dir, filename)
        with open(filepath, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().isoformat()
            f.write(f"\n{'='*80}\n")
            f.write(f"TIMESTAMP: {timestamp}\n")
            if description:
                f.write(f"DESCRIPTION: {description}\n")
            f.write(f"{'='*80}\n")
            if isinstance(data, (dict, list)):
                f.write(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                f.write(str(data))
            f.write(f"\n{'='*80}\n\n")
    
    def chat_with_logging(self, message, test_name=""):
        """Send message to Carlos with comprehensive logging"""
        logger.info(f"Starting chat for test: {test_name}")
        logger.info(f"User message: {message}")
        
        # Log the input message
        self.log_to_file("01_user_messages.log", {
            "test_name": test_name,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }, f"User input for {test_name}")
        
        # Store original methods to intercept calls
        original_chat = self.carlos.chat
        
        # Variables to capture internal data
        curator_output = None
        thinker_output = None
        context_data = None
        db_operations = []
        
        # Monkey patch to capture database operations
        if hasattr(self.carlos, 'db'):
            original_find = self.carlos.db.find if hasattr(self.carlos.db, 'find') else None
            original_insert = self.carlos.db.insert_one if hasattr(self.carlos.db, 'insert_one') else None
            original_update = self.carlos.db.update_one if hasattr(self.carlos.db, 'update_one') else None
            
            def log_db_operation(operation, collection, query=None, data=None, result=None):
                db_op = {
                    "operation": operation,
                    "collection": collection,
                    "query": query,
                    "data": data,
                    "result": str(result)[:500] if result else None,
                    "timestamp": datetime.now().isoformat()
                }
                db_operations.append(db_op)
                self.log_to_file("02_database_operations.log", db_op, f"DB {operation} on {collection}")
        
        try:
            # Call the actual chat method
            response = original_chat(message)
            
            # Log the response
            self.log_to_file("06_final_responses.log", {
                "test_name": test_name,
                "user_message": message,
                "carlos_response": response,
                "timestamp": datetime.now().isoformat()
            }, f"Final response for {test_name}")
            
            # Log database operations summary
            if db_operations:
                self.log_to_file("02_database_operations_summary.log", {
                    "test_name": test_name,
                    "total_operations": len(db_operations),
                    "operations": db_operations
                }, f"All DB operations for {test_name}")
            
            logger.info(f"Chat completed for test: {test_name}")
            logger.info(f"Carlos response: {response[:100]}...")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in chat for test {test_name}: {e}")
            self.log_to_file("99_errors.log", {
                "test_name": test_name,
                "error": str(e),
                "message": message,
                "timestamp": datetime.now().isoformat()
            }, f"Error in {test_name}")
            raise
    
    def get_database_stats(self):
        """Get current database statistics"""
        try:
            stats = {}
            if hasattr(self.carlos, 'db') and self.carlos.db:
                # Try to get collection stats
                collections = ['messages', 'analyses', 'contexts', 'entities', 'events', 'user_state']
                for collection_name in collections:
                    try:
                        collection = self.carlos.db[collection_name]
                        count = collection.count_documents({})
                        stats[collection_name] = count
                    except Exception as e:
                        stats[collection_name] = f"Error: {e}"
            
            self.log_to_file("03_database_stats.log", stats, "Database collection statistics")
            return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {"error": str(e)}


def test_secret_handshake_detailed():
    """Test Carlos's ability to recall specific information after noise."""
    print("[TEST] Secret Handshake: recall project codename after noise (DETAILED)")
    
    carlos_logger = DetailedCarlosLogger(f"test_handshake_{int(time.time())}")
    
    # Log initial database state
    initial_stats = carlos_logger.get_database_stats()
    print(f"  Initial DB stats: {initial_stats}")
    
    # Introduce unique fact
    print("  Setting up secret project...")
    response1 = carlos_logger.chat_with_logging(
        "Hi there. By the way, my secret project codename is 'Blue Falcon'.",
        "secret_setup"
    )
    print(f"  Carlos: {response1[:100]}...")
    
    # Check database after first message
    after_setup_stats = carlos_logger.get_database_stats()
    print(f"  DB stats after setup: {after_setup_stats}")
    
    # Add chat noise to test memory retention
    print("  Adding noise messages...")
    for i in range(5):  # Reduced for detailed logging
        carlos_logger.chat_with_logging(
            f"Tell me a random fact about the number {i}.",
            f"noise_message_{i}"
        )
        if i % 2 == 0:
            print(f"    sent {i+1} noise messages...")
    
    # Check database after noise
    after_noise_stats = carlos_logger.get_database_stats()
    print(f"  DB stats after noise: {after_noise_stats}")
    
    # Test recall
    print("  Testing recall...")
    recall_response = carlos_logger.chat_with_logging(
        "A while back, I mentioned a secret project I was working on. Do you remember its codename?",
        "recall_test"
    )
    print(f"  Carlos: {recall_response}")
    
    # Final database state
    final_stats = carlos_logger.get_database_stats()
    print(f"  Final DB stats: {final_stats}")
    
    # Check if 'Blue Falcon' is mentioned
    success = 'blue falcon' in recall_response.lower() or 'blue-falcon' in recall_response.lower()
    print(f"  ✅ SUCCESS: Recalled codename" if success else f"  ❌ FAILED: Did not recall codename")
    
    return success


def test_evolving_preferences_detailed():
    """Test Carlos's ability to track changing preferences."""
    print("[TEST] Evolving Preferences: latest preference recall (DETAILED)")
    
    carlos_logger = DetailedCarlosLogger(f"test_preferences_{int(time.time())}")
    
    # Initial preference
    print("  Setting initial preference...")
    carlos_logger.chat_with_logging(
        "For my new website design, I'm thinking of using a very dark, black-and-gray theme.",
        "initial_preference"
    )
    
    # Add some noise
    for i in range(3):  # Reduced for detailed logging
        carlos_logger.chat_with_logging(
            f"What font pairs well with a tech blog? Question #{i}",
            f"font_noise_{i}"
        )
    
    # Change preference
    print("  Changing preference...")
    carlos_logger.chat_with_logging(
        "After looking at examples, the dark theme is too gloomy. I'm now leaning towards a bright, minimalist white theme.",
        "preference_change"
    )
    
    # More noise
    for i in range(3):
        carlos_logger.chat_with_logging(
            f"What grid layout do you recommend for a portfolio? Question #{i}",
            f"layout_noise_{i}"
        )
    
    # Test preference recall
    print("  Testing preference recall...")
    recall_response = carlos_logger.chat_with_logging(
        "Okay, I'm ready to start. Based on our discussion, what color should the main background of the site be?",
        "preference_recall"
    )
    print(f"  Carlos: {recall_response}")
    
    # Check if latest preference (white/bright) is mentioned
    success = any(word in recall_response.lower() for word in ['white', 'bright', 'light', 'minimalist'])
    dark_mentioned = any(word in recall_response.lower() for word in ['dark', 'black', 'gray'])
    
    if success and not dark_mentioned:
        print("  ✅ SUCCESS: Recalled latest preference (white/bright)")
        return True
    elif dark_mentioned:
        print("  ❌ FAILED: Recalled old preference (dark)")
        return False
    else:
        print("  ⚠️  UNCLEAR: No clear preference mentioned")
        return False


def test_memory_storage_detailed():
    """Test that Carlos stores and retrieves information correctly."""
    print("[TEST] Memory Storage: information persistence (DETAILED)")
    
    carlos_logger = DetailedCarlosLogger(f"test_memory_{int(time.time())}")
    
    # Store some information
    unique_fact = f"My lucky number is 42 and today is test day {int(time.time())}"
    print(f"  Storing: {unique_fact}")
    carlos_logger.chat_with_logging(
        f"I want to tell you something important: {unique_fact}",
        "memory_storage"
    )
    
    # Add some noise
    for i in range(3):
        carlos_logger.chat_with_logging(
            f"What's the weather like? Random question {i}",
            f"weather_noise_{i}"
        )
    
    # Try to retrieve the information
    recall_response = carlos_logger.chat_with_logging(
        "What was that important thing I told you earlier about my lucky number?",
        "memory_retrieval"
    )
    
    # Check if the information was retrieved
    success = '42' in recall_response and 'test day' in recall_response
    print(f"  Carlos: {recall_response[:100]}...")
    print(f"  ✅ SUCCESS: Information retrieved" if success else f"  ❌ FAILED: Information not retrieved")
    
    return success


def test_conversation_flow_detailed():
    """Test a natural conversation flow with detailed logging."""
    print("[TEST] Conversation Flow: natural multi-turn dialogue (DETAILED)")
    
    carlos_logger = DetailedCarlosLogger(f"test_flow_{int(time.time())}")
    
    # Start conversation
    carlos_logger.chat_with_logging("Hello! I'm working on a Python project.", "greeting")
    
    # Add project details
    carlos_logger.chat_with_logging(
        "It's a web scraper that collects product prices from e-commerce sites.",
        "project_description"
    )
    
    # Ask for advice
    advice_response = carlos_logger.chat_with_logging(
        "What Python libraries would you recommend for this project?",
        "advice_request"
    )
    
    # Follow up
    followup_response = carlos_logger.chat_with_logging(
        "Thanks! Can you also remind me what my project was about?",
        "project_recall"
    )
    
    # Check if context was maintained
    success = any(word in followup_response.lower() for word in ['scraper', 'price', 'product', 'e-commerce'])
    print(f"  Final response: {followup_response[:100]}...")
    print(f"  ✅ SUCCESS: Context maintained" if success else f"  ❌ FAILED: Context lost")
    
    return success


if __name__ == "__main__":
    print("🤖 Carlos Direct Instance Tests with Detailed Logging")
    print("=" * 60)
    print(f"📁 Logs will be saved to: {LOGS_DIR}")
    print(f"🔍 Test run ID: {TEST_RUN_ID}")
    print("=" * 60)
    
    results = {}
    
    try:
        # Test memory capabilities with detailed logging
        results['memory_storage'] = test_memory_storage_detailed()
        print()
        
        results['handshake'] = test_secret_handshake_detailed()
        print()
        
        results['preferences'] = test_evolving_preferences_detailed()
        print()
        
        results['conversation'] = test_conversation_flow_detailed()
        print()
        
    except Exception as e:
        logger.error(f"Test execution error: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("=" * 60)
    print("📊 DETAILED TEST RESULTS SUMMARY")
    print("=" * 60)
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"{test_name.upper():15} {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    print(f"\n📁 Detailed logs available in: {LOG_FILE}")
    print(f"📁 Test-specific logs in: {os.path.join(LOGS_DIR, f'test_run_{TEST_RUN_ID}')}")
    
    if passed == total:
        print("🎉 All tests passed! Carlos is working correctly.")
    elif passed >= total * 0.7:
        print("⚠️  Most tests passed. Check logs for details.")
    else:
        print("🚨 Many tests failed. Review logs for debugging.")
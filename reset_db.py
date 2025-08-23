#!/usr/bin/env python3
"""
Database Reset Script for Carlos AI System

This script provides functionality to reset MongoDB databases used by the Carlos AI system.
It can reset individual user databases or all Carlos-related databases.

Usage:
    python reset_db.py --all                    # Reset all Carlos databases
    python reset_db.py --user username          # Reset specific user's database
    python reset_db.py --list                   # List all Carlos databases
    python reset_db.py --collections user       # Reset only collections for a user (keep database)
"""

import argparse
import os
import sys
from typing import List, Optional
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class CarlosDBReset:
    """Handles database reset operations for Carlos AI system."""
    
    def __init__(self, mongo_uri: str = None):
        """Initialize with MongoDB connection."""
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.client = None
        self.connect()
    
    def connect(self):
        """Establish MongoDB connection."""
        try:
            self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.server_info()
            logger.info(f"Connected to MongoDB at {self.mongo_uri}")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            logger.error("Make sure MongoDB is running. You can start it with: docker-compose up -d mongo")
            sys.exit(1)
    
    def get_carlos_databases(self) -> List[str]:
        """Get list of all Carlos-related databases."""
        try:
            all_dbs = self.client.list_database_names()
            carlos_dbs = [db for db in all_dbs if db.startswith('carlos_')]
            return carlos_dbs
        except Exception as e:
            logger.error(f"Error listing databases: {e}")
            return []
    
    def list_databases(self):
        """List all Carlos databases and their collections."""
        carlos_dbs = self.get_carlos_databases()
        
        if not carlos_dbs:
            logger.info("No Carlos databases found.")
            return
        
        logger.info(f"Found {len(carlos_dbs)} Carlos database(s):")
        
        for db_name in carlos_dbs:
            db = self.client[db_name]
            collections = db.list_collection_names()
            
            # Get some stats
            total_docs = 0
            collection_info = []
            
            for coll_name in collections:
                count = db[coll_name].count_documents({})
                total_docs += count
                collection_info.append(f"    - {coll_name}: {count} documents")
            
            logger.info(f"\n📁 Database: {db_name}")
            logger.info(f"   📊 Total documents: {total_docs}")
            logger.info(f"   📚 Collections ({len(collections)}):")
            for info in collection_info:
                logger.info(info)
    
    def reset_user_database(self, username: str, collections_only: bool = False):
        """Reset database for a specific user."""
        db_name = f"carlos_{username}"
        
        if db_name not in self.client.list_database_names():
            logger.warning(f"Database '{db_name}' does not exist.")
            return False
        
        db = self.client[db_name]
        collections = db.list_collection_names()
        
        if not collections:
            logger.info(f"Database '{db_name}' is already empty.")
            return True
        
        # Get stats before deletion
        total_docs = sum(db[coll].count_documents({}) for coll in collections)
        
        logger.info(f"Resetting database for user '{username}'...")
        logger.info(f"Database: {db_name}")
        logger.info(f"Collections to reset: {collections}")
        logger.info(f"Total documents to delete: {total_docs}")
        
        if not self._confirm_action(f"reset user '{username}' database"):
            return False
        
        try:
            if collections_only:
                # Drop all collections but keep the database
                for collection_name in collections:
                    db[collection_name].drop()
                    logger.info(f"✓ Dropped collection: {collection_name}")
                logger.info(f"✅ Successfully reset all collections for user '{username}'")
            else:
                # Drop the entire database
                self.client.drop_database(db_name)
                logger.info(f"✅ Successfully dropped database '{db_name}'")
            
            return True
            
        except Exception as e:
            logger.error(f"Error resetting database for user '{username}': {e}")
            return False
    
    def reset_all_databases(self):
        """Reset all Carlos-related databases."""
        carlos_dbs = self.get_carlos_databases()
        
        if not carlos_dbs:
            logger.info("No Carlos databases found to reset.")
            return True
        
        total_docs = 0
        db_info = []
        
        # Collect information about all databases
        for db_name in carlos_dbs:
            db = self.client[db_name]
            collections = db.list_collection_names()
            db_docs = sum(db[coll].count_documents({}) for coll in collections)
            total_docs += db_docs
            db_info.append(f"  - {db_name}: {len(collections)} collections, {db_docs} documents")
        
        logger.info(f"Found {len(carlos_dbs)} Carlos database(s) to reset:")
        for info in db_info:
            logger.info(info)
        logger.info(f"Total documents to delete: {total_docs}")
        
        if not self._confirm_action("reset ALL Carlos databases"):
            return False
        
        success_count = 0
        for db_name in carlos_dbs:
            try:
                self.client.drop_database(db_name)
                logger.info(f"✓ Dropped database: {db_name}")
                success_count += 1
            except Exception as e:
                logger.error(f"✗ Failed to drop database '{db_name}': {e}")
        
        if success_count == len(carlos_dbs):
            logger.info(f"✅ Successfully reset all {success_count} Carlos databases")
            return True
        else:
            logger.warning(f"⚠️  Reset {success_count}/{len(carlos_dbs)} databases")
            return False
    
    def create_sample_data(self, username: str):
        """Create some sample data for testing."""
        from datetime import datetime, timezone
        
        db_name = f"carlos_{username}"
        db = self.client[db_name]
        
        logger.info(f"Creating sample data for user '{username}'...")
        
        # Sample conversation
        conversations = db["conversations"]
        sample_conversation = {
            "user_id": username,
            "timestamp": datetime.now(timezone.utc),
            "user_input": "Hello Carlos!",
            "assistant_response": "Hello! How can I help you today?",
            "entities": ["greeting"],
            "semantic_tags": ["social", "greeting"],
            "sentiment": "positive"
        }
        conversations.insert_one(sample_conversation)
        
        # Sample user state
        user_state = db["user_state"]
        sample_state = {
            "user_id": username,
            "last_updated": datetime.now(timezone.utc),
            "context_flags": ["active"],
            "preferences": {"language": "english", "tone": "friendly"}
        }
        user_state.insert_one(sample_state)
        
        # Sample entity
        entities = db["entities"]
        sample_entity = {
            "user_id": username,
            "timestamp": datetime.now(timezone.utc),
            "name": "test_project",
            "type": "project",
            "description": "A sample project for testing"
        }
        entities.insert_one(sample_entity)
        
        logger.info("✅ Sample data created successfully")
    
    def _confirm_action(self, action: str) -> bool:
        """Ask for user confirmation before destructive operations."""
        response = input(f"\n⚠️  Are you sure you want to {action}? (yes/no): ").lower().strip()
        return response in ['yes', 'y']
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

def main():
    """Main function to handle command line arguments and execute operations."""
    parser = argparse.ArgumentParser(
        description="Reset MongoDB databases for Carlos AI system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python reset_db.py --list                    # List all Carlos databases
  python reset_db.py --user john               # Reset john's database
  python reset_db.py --collections mary        # Reset mary's collections only
  python reset_db.py --all                     # Reset all Carlos databases
  python reset_db.py --sample test_user        # Create sample data for testing
        """
    )
    
    parser.add_argument('--list', action='store_true', 
                       help='List all Carlos databases and their contents')
    parser.add_argument('--user', type=str, 
                       help='Reset database for specific user')
    parser.add_argument('--collections', type=str, 
                       help='Reset only collections for specific user (keep database)')
    parser.add_argument('--all', action='store_true', 
                       help='Reset all Carlos databases')
    parser.add_argument('--sample', type=str, 
                       help='Create sample data for specified user')
    parser.add_argument('--mongo-uri', type=str, 
                       help='MongoDB connection URI (default: mongodb://localhost:27017)')
    parser.add_argument('--force', action='store_true', 
                       help='Skip confirmation prompts (use with caution)')
    
    args = parser.parse_args()
    
    # Check if any action is specified
    if not any([args.list, args.user, args.collections, args.all, args.sample]):
        parser.print_help()
        sys.exit(1)
    
    # Initialize database reset handler
    try:
        db_reset = CarlosDBReset(args.mongo_uri)
        
        # Override confirmation if force flag is set
        if args.force:
            db_reset._confirm_action = lambda x: True
        
        # Execute requested operations
        if args.list:
            db_reset.list_databases()
        
        if args.user:
            success = db_reset.reset_user_database(args.user)
            if not success:
                sys.exit(1)
        
        if args.collections:
            success = db_reset.reset_user_database(args.collections, collections_only=True)
            if not success:
                sys.exit(1)
        
        if args.all:
            success = db_reset.reset_all_databases()
            if not success:
                sys.exit(1)
        
        if args.sample:
            db_reset.create_sample_data(args.sample)
        
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        if 'db_reset' in locals():
            db_reset.close()

if __name__ == "__main__":
    main()

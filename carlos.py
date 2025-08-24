import re
import requests
from datetime import datetime, timedelta
import os
import json
import asyncio
import threading
import time
from typing import Optional, Dict, Any, List
from CarlosDatabase import CarlosDatabaseHandler, MongoJSONEncoder, CuratorHandler
import logging
logger = logging.getLogger(__name__)


class ProactiveTriggers:
    """Configuration for when autonomous shards should inject proactive messages"""
    CURIOSITY_THRESHOLD = 0.8
    GAP_URGENCY = 0.7
    INSIGHT_CONFIDENCE = 0.9
    TIME_SINCE_LAST = 300  # 5 minutes
    PATTERN_MATCH = 0.85


class ProactiveMessageQueue:
    """Manages proactive messages from autonomous shards"""
    
    def __init__(self, db_handler: CarlosDatabaseHandler):
        self.db_handler = db_handler
        self.pending_messages = []
        self.triggers = ProactiveTriggers()
    
    def add_message(self, message: Dict[str, Any]):
        """Add a proactive message to the queue"""
        message['timestamp'] = datetime.now()
        self.pending_messages.append(message)
        logger.info(f"Added proactive message: {message['type']} - {message.get('preview', 'No preview')}")
    
    def should_inject(self, context: Dict[str, Any]) -> bool:
        """Determine if any pending message should be injected"""
        if not self.pending_messages:
            return False
        
        highest_priority = max(msg.get('urgency', 0) for msg in self.pending_messages)
        time_since_last = context.get('time_since_last_message', 0)
        
        return (highest_priority >= self.triggers.GAP_URGENCY or 
                time_since_last >= self.triggers.TIME_SINCE_LAST)
    
    def get_next_message(self) -> Optional[Dict[str, Any]]:
        """Get the next message to inject, if any"""
        if not self.pending_messages:
            return None
        
        # Sort by urgency and get highest priority
        self.pending_messages.sort(key=lambda x: x.get('urgency', 0), reverse=True)
        return self.pending_messages.pop(0)
    
    def store_active_thought(self, shard_type: str, thought_type: str, content: Dict[str, Any], urgency: float):
        """Store an active thought in the database"""
        thought_doc = {
            'shard_id': shard_type,
            'thought_type': thought_type,
            'content': content,
            'urgency': urgency,
            'context_relevance': content.get('relevance', 0.5),
            'timestamp': datetime.now(),
            'status': 'ready'
        }
        
        try:
            collection = self.db_handler.db['active_thoughts']
            collection.insert_one(thought_doc)
            logger.debug(f"Stored active thought: {shard_type} - {thought_type}")
        except Exception as e:
            logger.error(f"Failed to store active thought: {e}")


class AutonomousShard:
    """Base class for autonomous background shard processes"""
    
    def __init__(self, shard_type: str, db_handler: CarlosDatabaseHandler, message_queue: ProactiveMessageQueue):
        self.shard_type = shard_type
        self.db_handler = db_handler
        self.message_queue = message_queue
        self.running = False
        self.check_interval = 30  # seconds
        self.thread = None
        self.last_check = datetime.now()
        
    def start(self):
        """Start the autonomous shard in background thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            logger.info(f"Started autonomous {self.shard_type} shard")
    
    def stop(self):
        """Stop the autonomous shard"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"Stopped autonomous {self.shard_type} shard")
    
    def _run_loop(self):
        """Main processing loop for the shard"""
        while self.running:
            try:
                self.process_cycle()
                self.last_check = datetime.now()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in {self.shard_type} shard cycle: {e}")
                time.sleep(self.check_interval)
    
    def process_cycle(self):
        """Override in subclasses - main processing logic"""
        pass
    
    def create_proactive_message(self, message_type: str, content: str, urgency: float, context: Dict[str, Any] = None):
        """Create a proactive message and add to queue"""
        message = {
            'shard_type': self.shard_type,
            'type': message_type,
            'content': content,
            'urgency': urgency,
            'context': context or {},
            'preview': content[:50] + "..." if len(content) > 50 else content
        }
        
        self.message_queue.add_message(message)
        self.message_queue.store_active_thought(self.shard_type, message_type, message, urgency)


class AutonomousCurator(AutonomousShard):
    """Autonomous curator that monitors for patterns and information gaps"""
    
    def __init__(self, db_handler: CarlosDatabaseHandler, message_queue: ProactiveMessageQueue, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__("curator", db_handler, message_queue)
        self.api_endpoint = api_endpoint
        self.system_prompt = system_prompt
        self.schema = schema
        self.check_interval = 45  # Slightly longer interval for curator
        
    def process_cycle(self):
        """Monitor database for patterns and gaps that warrant investigation"""
        logger.debug("Autonomous curator processing cycle")
        
        try:
            # Check for new patterns in recent conversations
            recent_conversations = self._get_recent_conversations()
            if recent_conversations:
                patterns = self._analyze_patterns(recent_conversations)
                if patterns:
                    self._generate_pattern_insights(patterns)
            
            # Check for unresolved information gaps
            self._check_information_gaps()
            
            # Look for conversation threads that need follow-up
            self._check_pending_threads()
            
        except Exception as e:
            logger.error(f"Error in autonomous curator cycle: {e}")
    
    def _get_recent_conversations(self) -> List[Dict[str, Any]]:
        """Get recent conversations for pattern analysis"""
        try:
            collection = self.db_handler.get_collection("conversations")
            recent_threshold = datetime.now() - timedelta(hours=2)
            
            conversations = list(collection.find(
                {"timestamp": {"$gte": recent_threshold}},
                {"user_input": 1, "assistant_response": 1, "entities": 1, "semantic_tags": 1, "timestamp": 1}
            ).sort("timestamp", -1).limit(10))
            
            return conversations
        except Exception as e:
            logger.error(f"Error getting recent conversations: {e}")
            return []
    
    def _analyze_patterns(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze conversations for emerging patterns"""
        if len(conversations) < 3:
            return {}
        
        # Simple pattern detection - count recurring entities and themes
        entity_frequency = {}
        tag_frequency = {}
        
        for conv in conversations:
            for entity in conv.get("entities", []):
                entity_frequency[entity] = entity_frequency.get(entity, 0) + 1
            for tag in conv.get("semantic_tags", []):
                tag_frequency[tag] = tag_frequency.get(tag, 0) + 1
        
        # Find patterns that appear multiple times
        recurring_entities = {k: v for k, v in entity_frequency.items() if v >= 2}
        recurring_themes = {k: v for k, v in tag_frequency.items() if v >= 2}
        
        if recurring_entities or recurring_themes:
            return {
                "recurring_entities": recurring_entities,
                "recurring_themes": recurring_themes,
                "conversation_count": len(conversations)
            }
        
        return {}
    
    def _generate_pattern_insights(self, patterns: Dict[str, Any]):
        """Generate insights about detected patterns"""
        entities = patterns.get("recurring_entities", {})
        themes = patterns.get("recurring_themes", {})
        
        # Only create insights for significant patterns (3+ occurrences)
        if entities:
            top_entity = max(entities.items(), key=lambda x: x[1])
            if top_entity[1] >= 3:  # Only for significant patterns
                urgency = min(0.9, 0.6 + (top_entity[1] * 0.1))
                
                # Create rich context for meaningful insight
                pattern_context = {
                    "entity": top_entity[0],
                    "frequency": top_entity[1],
                    "pattern_type": "recurring_entity",
                    "themes": list(themes.keys())[:3],
                    "conversation_span": patterns.get("conversation_count", 0)
                }
                
                self.message_queue.store_active_thought(
                    "curator", 
                    "significant_pattern", 
                    pattern_context, 
                    urgency
                )
    
    def _check_information_gaps(self):
        """Check for critical information gaps that need addressing"""
        try:
            # Look for active thoughts marked as gaps
            collection = self.db_handler.get_collection("active_thoughts")
            recent_gaps = list(collection.find(
                {
                    "thought_type": "information_gap",
                    "status": "pending",
                    "timestamp": {"$gte": datetime.now() - timedelta(hours=6)}
                }
            ))
            
            for gap in recent_gaps:
                if gap.get("urgency", 0) > 0.6:
                    content = f"I'm still missing some key information about {gap.get('content', {}).get('topic', 'something')} from our earlier conversation. Could you help fill in the gaps?"
                    
                    self.create_proactive_message(
                        "information_request",
                        content,
                        gap.get("urgency", 0.6),
                        {"gap_id": str(gap["_id"]), "topic": gap.get("content", {}).get("topic")}
                    )
                    
        except Exception as e:
            logger.error(f"Error checking information gaps: {e}")
    
    def _check_pending_threads(self):
        """Check for conversation threads that need follow-up"""
        # Disabled - thread followups were generating low-value messages
        # Focus on pattern-based and cyclical insights instead
        pass


class AutonomousThinker(AutonomousShard):
    """Autonomous thinker that processes curator findings and generates insights"""
    
    def __init__(self, db_handler: CarlosDatabaseHandler, message_queue: ProactiveMessageQueue, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__("thinker", db_handler, message_queue)
        self.api_endpoint = api_endpoint
        self.system_prompt = system_prompt
        self.schema = schema
        self.check_interval = 60  # Longer interval for deeper thinking
        
    def process_cycle(self):
        """Process curator findings and generate deep insights"""
        logger.debug("Autonomous thinker processing cycle")
        
        try:
            # Check for new curator thoughts to process
            curator_thoughts = self._get_unprocessed_curator_thoughts()
            if curator_thoughts:
                self._process_curator_insights(curator_thoughts)
            
            # Generate spontaneous insights from accumulated context
            self._generate_spontaneous_insights()
            
        except Exception as e:
            logger.error(f"Error in autonomous thinker cycle: {e}")
    
    def _get_unprocessed_curator_thoughts(self) -> List[Dict[str, Any]]:
        """Get curator thoughts that haven't been processed by thinker"""
        try:
            collection = self.db_handler.get_collection("active_thoughts")
            thoughts = list(collection.find(
                {
                    "shard_id": "curator",
                    "status": "ready",
                    "timestamp": {"$gte": datetime.now() - timedelta(hours=4)}
                }
            ).sort("urgency", -1).limit(3))
            
            return thoughts
        except Exception as e:
            logger.error(f"Error getting curator thoughts: {e}")
            return []
    
    def _process_curator_insights(self, curator_thoughts: List[Dict[str, Any]]):
        """Process curator insights and generate deeper analysis"""
        for thought in curator_thoughts:
            try:
                # Use the LLM to think deeply about the curator's finding
                analysis = self._analyze_with_llm(thought)
                if analysis:
                    self._create_insight_message(analysis, thought)
                    
                # Mark curator thought as processed
                collection = self.db_handler.get_collection("active_thoughts")
                collection.update_one(
                    {"_id": thought["_id"]},
                    {"$set": {"status": "processed", "processed_by": "thinker"}}
                )
                
            except Exception as e:
                logger.error(f"Error processing curator insight: {e}")
    
    def _analyze_with_llm(self, curator_thought: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze curator findings"""
        try:
            analysis_prompt = f"""
            AUTONOMOUS INTERNAL ANALYSIS MODE - This is your internal reasoning process, not a user interaction.
            
            You are conducting internal analysis of patterns detected by your autonomous curator subsystem. This is purely internal reasoning - the user is not asking you anything right now.
            
            Curator Finding:
            Type: {curator_thought.get('thought_type')}
            Content: {json.dumps(curator_thought.get('content'), cls=MongoJSONEncoder, indent=2)}
            Urgency: {curator_thought.get('urgency')}
            
            Your task: Analyze this curator finding internally. Determine if this pattern reveals something meaningful about the user's interests, projects, or needs that might warrant a proactive insight.
            
            Think internally about:
            - What deeper patterns does this reveal about the user's behavior/interests?
            - What insights emerge from this data that could be valuable to share?
            - Is there a high-confidence observation worth making proactively?
            
            This is internal analysis only - you are not responding to the user yet.
            """
            
            message = {
                "model": "carlos",
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": analysis_prompt}
                ],
                "response_format": self.schema,
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            response = requests.post(f"{self.api_endpoint}/v1/chat/completions", json=message)
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                logger.debug(f"LLM response content: {content}")
                
                # Try to parse JSON, with fallback handling
                try:
                    return json.loads(content)
                except json.JSONDecodeError as json_err:
                    logger.error(f"Failed to parse LLM JSON response: {json_err}")
                    logger.error(f"Raw content: {content}")
                    # Return None to skip this analysis
                    return None
            else:
                logger.error(f"LLM API error: {response.status_code} - {response.text}")
            
        except Exception as e:
            logger.error(f"Error in LLM analysis: {e}")
        
        return None
    
    def _create_insight_message(self, analysis: Dict[str, Any], original_thought: Dict[str, Any]):
        """Create a proactive message based on thinker analysis"""
        # Always store the full analysis as internal thought
        self._store_internal_thought(analysis, original_thought)
        
        # Only create chat message if it meets high-quality criteria
        if self._is_actionable_message(analysis, original_thought):
            # Use response generator to create natural, meaningful message
            meaningful_message = self._create_meaningful_proactive_message(analysis, original_thought)
            
            if meaningful_message:
                urgency = min(0.9, analysis.get("confidence", 0.5))
                
                self.create_proactive_message(
                    "meaningful_insight",
                    meaningful_message,
                    urgency,
                    {
                        "based_on": str(original_thought["_id"]),
                        "curator_type": original_thought.get("thought_type"),
                        "confidence": analysis.get("confidence", 0),
                        "processed_through_response_generator": True
                    }
                )
    
    def _store_internal_thought(self, analysis: Dict[str, Any], original_thought: Dict[str, Any]):
        """Store internal thought for debugging/monitoring panel"""
        internal_thought = {
            "timestamp": datetime.now(),
            "type": "deep_analysis",
            "analysis": analysis,
            "original_context": original_thought.get("thought_type"),
            "insight": analysis.get("key_insights", ""),
            "suggested_step": analysis.get("suggested_next_step", ""),
            "urgency": original_thought.get("urgency", 0.5)
        }
        
        try:
            collection = self.db_handler.get_collection("internal_thoughts")
            collection.insert_one(internal_thought)
        except Exception as e:
            logger.error(f"Failed to store internal thought: {e}")
    
    def _is_actionable_message(self, analysis: Dict[str, Any], original_thought: Dict[str, Any]) -> bool:
        """Determine if we should create a proactive message based on depth of insight"""
        confidence = analysis.get("confidence", 0)
        insight = analysis.get("novel_insight", "")
        original_type = original_thought.get("thought_type", "")
        
        # Skip generic thread followups entirely
        if original_type == "thread_followup":
            return False
            
        # Only high-confidence, substantive insights
        if confidence < 0.8 or len(insight) < 30:
            return False
            
        # Skip if it contains generic language
        generic_phrases = [
            "clarify", "specify", "remind me", "what part", "which topic",
            "earlier conversation", "previous discussion", "unresolved"
        ]
        
        insight_lower = insight.lower()
        if any(phrase in insight_lower for phrase in generic_phrases):
            return False
            
        return True
    
    def _create_meaningful_proactive_message(self, analysis: Dict[str, Any], original_thought: Dict[str, Any]) -> Optional[str]:
        """Create a meaningful proactive message through the response generator"""
        try:
            # Extract the actual insight content
            novel_insight = analysis.get("novel_insight", "")
            synthesis = analysis.get("synthesis", "")
            original_context = original_thought.get("content", {})
            
            # Create a rich context for the response generator
            proactive_context = {
                "insight_type": "autonomous_observation",
                "novel_insight": novel_insight,
                "synthesis": synthesis,
                "original_pattern": original_context,
                "confidence": analysis.get("confidence", 0),
                "reasoning": analysis.get("thinking_cycles", []),
                "should_be_conversational": True,
                "should_include_question": True if analysis.get("confidence", 0) > 0.9 else False
            }
            
            # Use response generator to create natural, personalized message
            response_prompt = f"""
            CONTEXT: You've been doing autonomous background thinking and discovered an interesting pattern. Now you want to proactively share this insight with the user in a natural conversation.

            Your autonomous insight: {novel_insight}
            
            Pattern synthesis: {synthesis}
            
            Generate a natural proactive message as if you just had this realization while thinking in the background:
            - Sound like you naturally thought of something interesting while reflecting
            - Be conversational and genuine, not robotic or formal
            - Share your observation in an engaging way
            - If appropriate, ask a thoughtful question that shows your curiosity
            - Use your personality - be warm, thoughtful, maybe slightly curious
            - Keep it concise but valuable
            - Show that you've been thinking about their patterns/interests
            
            This should feel like Carlos spontaneously sharing a thoughtful observation, not responding to a user request.
            """
            
            message = {
                "model": "carlos",
                "messages": [
                    {"role": "system", "content": self.response_generator_system_prompt},
                    {"role": "system", "content": f"Context: {json.dumps(proactive_context, cls=MongoJSONEncoder)}"},
                    {"role": "user", "content": response_prompt}
                ],
                "response_format": self.response_generator_schema,
                "temperature": 0.8,  # More creative for proactive messages
                "max_tokens": 200
            }
            
            response = requests.post(f"{self.api_endpoint}/v1/chat/completions", json=message)
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                try:
                    response_data = json.loads(content)
                    return response_data.get("response", content)
                except json.JSONDecodeError:
                    # If JSON parsing fails, return the raw content
                    return content
                    
        except Exception as e:
            logger.error(f"Error creating meaningful proactive message: {e}")
            
        return None
    
    def _create_cyclical_proactive_message(self, thinking_chain: Dict[str, Any], historical_context: List[Dict[str, Any]]) -> Optional[str]:
        """Create a natural proactive message from cyclical thinking"""
        try:
            # Extract key elements
            novel_insight = thinking_chain.get("novel_insight", "")
            actionable_insight = thinking_chain.get("actionable_insight", "")
            synthesis = thinking_chain.get("synthesis", "")
            thinking_cycles = thinking_chain.get("thinking_cycles", [])
            
            # Build rich context for response generator
            cyclical_context = {
                "insight_type": "cyclical_analysis",
                "novel_insight": novel_insight,
                "synthesis": synthesis,
                "actionable_insight": actionable_insight,
                "historical_seeds": [h.get("preview", "") for h in historical_context[:2]],
                "thinking_depth": len(thinking_cycles),
                "confidence": thinking_chain.get("confidence", 0.6)
            }
            
            response_prompt = f"""
            CONTEXT: You've been autonomously analyzing conversation patterns in the background and just had a breakthrough insight. You want to naturally share this discovery.

            Your cyclical insight from background analysis: {novel_insight}
            
            Synthesis across conversation history: {synthesis}
            
            Actionable thought: {actionable_insight}
            
            Historical conversations that sparked this insight: {[h.get("preview", "") for h in historical_context[:2]]}
            
            Generate a natural proactive message as if you just connected some dots while thinking in the background:
            - Sound like you had an "aha!" moment while reflecting on past conversations
            - Show that you've been thinking about patterns across your chat history
            - Be specific about the connections you discovered
            - Share your insight in an engaging, conversational way
            - If appropriate, ask a thoughtful question that shows genuine curiosity
            - Keep it personal and warm - you're sharing a discovery with them
            
            This should feel like Carlos naturally sharing an interesting realization from autonomous reflection, not answering a user question.
            """
            
            message = {
                "model": "carlos",
                "messages": [
                    {"role": "system", "content": self.response_generator_system_prompt},
                    {"role": "system", "content": f"Context: {json.dumps(cyclical_context, cls=MongoJSONEncoder)}"},
                    {"role": "user", "content": response_prompt}
                ],
                "response_format": self.response_generator_schema,
                "temperature": 0.8,
                "max_tokens": 250
            }
            
            response = requests.post(f"{self.api_endpoint}/v1/chat/completions", json=message)
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                try:
                    response_data = json.loads(content)
                    return response_data.get("response", content)
                except json.JSONDecodeError:
                    return content
                    
        except Exception as e:
            logger.error(f"Error creating cyclical proactive message: {e}")
            
        return None
    
    def _generate_spontaneous_insights(self):
        """Generate spontaneous insights using cyclical thinking with historical context"""
        try:
            # Skip if we've generated too many recent thoughts (avoid spam)
            if self._has_recent_similar_thoughts():
                return
                
            # Get random historical context to seed thinking
            historical_context = self._get_random_historical_inputs()
            if not historical_context:
                return
                
            # Perform cyclical thinking chain
            thinking_chain = self._perform_thinking_cycle(historical_context)
            if thinking_chain and self._is_novel_insight(thinking_chain):
                self._store_thinking_chain(thinking_chain)
                
                # Route through response generator for natural language
                if thinking_chain.get("actionable_insight"):
                    natural_message = self._create_cyclical_proactive_message(thinking_chain, historical_context)
                    if natural_message:
                        self.create_proactive_message(
                            "cyclical_insight",
                            natural_message,
                            thinking_chain.get("urgency", 0.6),
                            {
                                "thinking_type": "cyclical",
                                "historical_seeds": [h.get("preview", "") for h in historical_context[:2]],
                                "chain_depth": thinking_chain.get("depth", 1),
                                "confidence": thinking_chain.get("confidence", 0.6)
                            }
                        )
                
        except Exception as e:
            logger.error(f"Error generating spontaneous insights: {e}")
    
    def _get_random_historical_inputs(self, count: int = 3) -> List[Dict[str, Any]]:
        """Get random user inputs from history to seed thinking chains"""
        try:
            collection = self.db_handler.get_collection("conversations")
            
            # Get diverse historical inputs (different time periods)
            pipeline = [
                {"$match": {"user_input": {"$regex": ".{20,}"}}},  # Skip very short inputs
                {"$sample": {"size": count * 3}},  # Get more than needed for filtering
                {"$project": {
                    "user_input": 1, 
                    "timestamp": 1, 
                    "entities": 1, 
                    "semantic_tags": 1
                }}
            ]
            
            candidates = list(collection.aggregate(pipeline))
            
            # Filter for diversity (different entities/topics)
            diverse_inputs = []
            used_entities = set()
            
            for candidate in candidates:
                candidate_entities = set(candidate.get("entities", []))
                if len(diverse_inputs) < count and not candidate_entities.intersection(used_entities):
                    diverse_inputs.append({
                        "content": candidate["user_input"],
                        "timestamp": candidate["timestamp"],
                        "entities": candidate.get("entities", []),
                        "semantic_tags": candidate.get("semantic_tags", []),
                        "preview": candidate["user_input"][:50] + "..." if len(candidate["user_input"]) > 50 else candidate["user_input"]
                    })
                    used_entities.update(candidate_entities)
            
            return diverse_inputs
            
        except Exception as e:
            logger.error(f"Error getting random historical inputs: {e}")
            return []
    
    def _perform_thinking_cycle(self, historical_context: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Perform cyclical thinking using historical context as seeds"""
        try:
            # Build rich context for cyclical reasoning
            context_summary = self._summarize_historical_context(historical_context)
            
            cyclical_prompt = f"""
            INTERNAL AUTONOMOUS REASONING: You are conducting deep cyclical thinking about historical conversation patterns. This is internal analysis - the user is not currently interacting with you.

            You are analyzing these historical conversation fragments from your memory to generate internal insights:

            Historical Context Seeds:
            {context_summary}

            Conduct internal cyclical reasoning:
            1. What behavioral patterns emerge across these historical user conversations?
            2. What connections exist between the user's past interests and current needs?
            3. What insights about the user's goals/challenges arise from this analysis?
            4. What novel understanding of the user emerges from this cyclical analysis?
            5. Is there a valuable insight about the user worth sharing proactively?

            This is autonomous internal reasoning - you are analyzing the user's conversation patterns while they are not actively chatting. Think deeply through multiple internal reasoning cycles.
            """

            message = {
                "model": "carlos",
                "messages": [
                    {"role": "system", "content": self._get_enhanced_thinking_prompt()},
                    {"role": "user", "content": cyclical_prompt}
                ],
                "response_format": self._get_cyclical_thinking_schema(),
                "temperature": 0.7,  # Higher creativity for insights
                "max_tokens": 800   # More space for cyclical reasoning
            }

            response = requests.post(f"{self.api_endpoint}/v1/chat/completions", json=message)
            if response.status_code == 200:
                result = response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
                
                try:
                    thinking_chain = json.loads(content)
                    thinking_chain["historical_seeds"] = historical_context
                    thinking_chain["timestamp"] = datetime.now()
                    return thinking_chain
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse cyclical thinking JSON: {e}")
                    logger.debug(f"Raw cyclical response: {content}")
                    return None
            
        except Exception as e:
            logger.error(f"Error in cyclical thinking: {e}")
        
        return None
    
    def _get_enhanced_thinking_prompt(self) -> str:
        """Enhanced system prompt for cyclical thinking"""
        return """AUTONOMOUS CYCLICAL THINKING MODE - You are in internal reasoning mode, not responding to a user.

You are an advanced reasoning agent performing autonomous cyclical thinking. This is your internal thought process running in the background while the user is not actively chatting.

You are analyzing historical conversation patterns to generate novel insights internally. The user has not asked you anything - this is your autonomous reasoning process.

Your internal thinking should be:
- Multi-layered: Consider immediate patterns, deeper connections, and meta-patterns
- Cyclical: Build on previous thoughts, revisit ideas from new angles
- Novel: Generate genuinely new insights about the user's patterns/interests
- Valuable: Focus on insights that reveal meaningful patterns about the user

This is internal analysis - you are not responding to the user yet. Think deeply about patterns across their conversation history."""

    def _get_cyclical_thinking_schema(self) -> dict:
        """Schema for cyclical thinking responses"""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "cyclical_thinking",
                "schema": {
                    "type": "object",
                    "properties": {
                        "thinking_cycles": {
                            "type": "array",
                            "items": {
                                "type": "object", 
                                "properties": {
                                    "cycle": {"type": "number"},
                                    "observation": {"type": "string"},
                                    "connection": {"type": "string"}
                                }
                            }
                        },
                        "synthesis": {"type": "string"},
                        "novel_insight": {"type": "string"},
                        "actionable_insight": {"type": "string"},
                        "confidence": {"type": "number"},
                        "urgency": {"type": "number"},
                        "depth": {"type": "number"}
                    },
                    "required": ["thinking_cycles", "synthesis", "novel_insight"]
                }
            }
        }
    
    def _summarize_historical_context(self, historical_context: List[Dict[str, Any]]) -> str:
        """Summarize historical context for thinking prompt"""
        summaries = []
        for i, ctx in enumerate(historical_context, 1):
            entities_str = ", ".join(ctx.get("entities", [])[:3])
            tags_str = ", ".join(ctx.get("semantic_tags", [])[:3])
            summaries.append(f"""
            Fragment {i} ({ctx.get("timestamp", "unknown")}):
            Content: {ctx.get("preview", "")}
            Entities: {entities_str}
            Topics: {tags_str}
            """)
        return "\n".join(summaries)
    
    def _store_thinking_chain(self, thinking_chain: Dict[str, Any]):
        """Store cyclical thinking chain in database"""
        try:
            collection = self.db_handler.get_collection("thinking_chains")
            collection.insert_one(thinking_chain)
            logger.debug("Stored cyclical thinking chain")
        except Exception as e:
            logger.error(f"Failed to store thinking chain: {e}")
    
    def _is_novel_insight(self, thinking_chain: Dict[str, Any]) -> bool:
        """Check if the insight is novel (not repetitive)"""
        try:
            novel_insight = thinking_chain.get("novel_insight", "")
            confidence = thinking_chain.get("confidence", 0)
            
            # Skip low-confidence or empty insights
            if confidence < 0.6 or len(novel_insight) < 20:
                return False
            
            # Check against recent similar insights
            collection = self.db_handler.get_collection("thinking_chains")
            recent_chains = list(collection.find(
                {"timestamp": {"$gte": datetime.now() - timedelta(hours=6)}},
                {"novel_insight": 1}
            ))
            
            # Simple similarity check (could be enhanced with embeddings)
            for chain in recent_chains:
                existing_insight = chain.get("novel_insight", "")
                if self._calculate_similarity(novel_insight, existing_insight) > 0.7:
                    logger.debug("Skipping similar insight")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking insight novelty: {e}")
            return False
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Simple similarity calculation (could be enhanced)"""
        if not text1 or not text2:
            return 0.0
        
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _has_recent_similar_thoughts(self, hours: int = 2) -> bool:
        """Check if we've had similar thoughts recently to avoid spam"""
        try:
            collection = self.db_handler.get_collection("thinking_chains")
            recent_count = collection.count_documents({
                "timestamp": {"$gte": datetime.now() - timedelta(hours=hours)}
            })
            return recent_count >= 3  # Max 3 thinking chains per 2 hours
        except:
            return False
    
    def _get_recent_entity_connections(self) -> set:
        """Get entities that have appeared together recently"""
        try:
            collection = self.db_handler.get_collection("conversations")
            recent_conversations = list(collection.find(
                {"timestamp": {"$gte": datetime.now() - timedelta(hours=6)}},
                {"entities": 1}
            ).limit(10))
            
            all_entities = []
            for conv in recent_conversations:
                all_entities.extend(conv.get("entities", []))
            
            # Return entities that appear multiple times
            entity_counts = {}
            for entity in all_entities:
                entity_counts[entity] = entity_counts.get(entity, 0) + 1
            
            return {entity for entity, count in entity_counts.items() if count >= 2}
            
        except Exception as e:
            logger.error(f"Error getting entity connections: {e}")
            return set()


# Phase 1: Perception & Ingestion
# What happens: The Listener perceives the Speaker's utterance.

# Speaker's action: "Person says something." This is the raw data input. It's not just words; it includes tone of voice, cadence, volume (prosody), and in face-to-face conversation, body language and facial expressions.

# Example: Speaker says, "I'm thinking of getting a dog."

# Phase 2: Analysis & Deconstruction
# What happens: The Listener's brain (or an AI's processor) breaks the input down into meaningful components. This isn't just a single action, but several simultaneous processes.

# Listener's action: "Person 2 does analysis what person 1 said."

# Linguistic Parsing: Identifying the words, grammar, and sentence structure. (e.g., Subject: "I", Verb: "am thinking", Object: "getting a dog").

# Semantic Analysis: Understanding the literal meaning of the words. (e.g., The speaker is contemplating the acquisition of a canine.)

# Intent Recognition (Pragmatics): Figuring out the purpose behind the words. Is it a simple statement? Are they seeking an opinion? Are they expressing a desire for companionship? (e.g., This is likely a conversation starter, possibly seeking feedback or sharing a life update.)

# Entity Extraction: Identifying the key concepts. (e.g., Key entities are "I" (the Speaker) and "dog".)

# Phase 3: Contextualization & Retrieval
# What happens: The analyzed information is connected to a vast network of existing knowledge.

# Listener's action: "maybe retrieves some memories about stuff." This is crucial for a relevant response.

# Short-Term / Conversational Context: "What were we just talking about? Did they mention pets before?"

# Long-Term / Relational Memory: "I remember the Speaker telling me their apartment has a 'no pets' policy. This is new." or "They grew up with a golden retriever and loved it."

# World Knowledge: "What do I know about dogs? They need walks, food, vet visits. Certain breeds are better for apartments. Shelters are a good place to look."

# Example Retrieval: The Listener recalls: 1) The Speaker mentioned feeling lonely last week. 2) The Speaker lives in a small apartment. 3) The Listener's cousin just adopted a rescue dog and is very happy.

# Phase 4: Synthesis & Response Generation
# What happens: Based on the analysis and retrieved context, the Listener constructs a response.

# Listener's action: "says something based on that."

# Goal Formulation: The Listener decides on the purpose of their response. Do they want to be encouraging? Cautious? Inquisitive? (e.g., Goal: Be encouraging but also practical).

# Content Selection: Choose which pieces of retrieved information are most relevant. (e.g., Acknowledge their feeling of loneliness, mention the apartment size as a consideration, and bring up the positive adoption story).

# Linguistic Encoding: The chosen content is translated into actual words and sentences with an appropriate tone.

# Example Response: "Oh, that's exciting! A dog would be great company. Have you thought about what breed would be happy in an apartment?"

# Phase 5: Memory Update & Pruning
# What happens: The cycle concludes, and the context is updated for the next turn.

# Listener's action: "stores that cycle context and filters out irrelevant stuff to next cycle."

# Context Integration: The immediate memory is updated. The new "state" of the conversation is: "The topic is the Speaker getting a dog. I have just asked them about breeds suitable for apartments."

# Salience Filtering (Pruning): The mind doesn't store everything verbatim. It holds on to the most important information (the gist) and lets go of the less relevant details. The core concept ("thinking of getting a dog") is highly salient. The exact phrasing ("I'm thinking of...") is less so and might be forgotten. This prevents cognitive overload.

# Memory Consolidation: The key takeaway from this cycle might be stored in long-term memory. (e.g., "Note to self: My friend is considering getting a dog.")

# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	GET  http://192.168.50.202:1234/v1/models
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/chat/completions
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/completions
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/embeddings

# curl http://localhost:1234/v1/chat/completions \
#   -H "Content-Type: application/json" \
#   -d '{
#     "model": "curator",
#     "messages": [
#       { "role": "system", "content": "Always answer in rhymes. Today is Thursday" },
#       { "role": "user", "content": "What day is it today?" }
#     ],
#     "temperature": 0.7,
#     "max_tokens": -1,
#     "stream": false
# }'



class Carlos:
    """Carlos is a conversational AI system that interacts with users, processes messages, and retrieves information from a MongoDB database."""
    curator_schema = "" 
    curator_system_prompt = ""
    thinker_schema = ""
    thinker_system_prompt = ""
    response_generator_schema = ""
    response_generator_system_prompt = ""
    summarizer_schema = ""
    summarizer_system_prompt = ""
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, mongo_uri: Optional[str] = None, api_endpoint: Optional[str] = None):
        """Initialize Carlos with MongoDB client and API endpoint."""
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/carlos")
        self.api_endpoint = api_endpoint or os.getenv("API_ENDPOINT", "http://192.168.50.202:1234")
    
        self.username = username or os.getenv("CARLOS_USERNAME", "test_user")
        self.password = password or os.getenv("CARLOS_PASSWORD", "foobar")
        
        self.db_handler = CarlosDatabaseHandler(self.mongo_uri, username)
        self.curator_handler = CuratorHandler(self.db_handler)

        # Load systems prompts and schemas
        try:
            with open("promts/curator_schema.json", "r") as f:
                self.curator_schema = json.loads(f.read())
            with open("promts/curator_system_prompt.txt", "r") as f:
                self.curator_system_prompt = f.read()
            with open("promts/thinker_schema.json", "r") as f:
                self.thinker_schema = json.loads(f.read())
            with open("promts/thinker_system_prompt.txt", "r") as f:
                self.thinker_system_prompt = f.read()
            with open("promts/response_generator_schema.json", "r") as f:
                self.response_generator_schema = json.loads(f.read())
            with open("promts/response_generator_system_prompt.txt", "r") as f:
                self.response_generator_system_prompt = f.read()
            with open("promts/summarizer_schema.json", "r") as f:
                self.summarizer_schema = json.loads(f.read())
            with open("promts/summarizer_system_prompt.txt", "r") as f:
                self.summarizer_system_prompt = f.read()
            logger.info("Loaded system prompts and schemas successfully")
        except Exception as e:
            logger.error(f"Error loading prompts/schemas: {e}")
            raise   

        # Initialize autonomous shards
        self.message_queue = ProactiveMessageQueue(self.db_handler)
        self.autonomous_curator = AutonomousCurator(
            self.db_handler, 
            self.message_queue, 
            self.api_endpoint, 
            self.curator_system_prompt, 
            self.curator_schema
        )
        self.autonomous_thinker = AutonomousThinker(
            self.db_handler, 
            self.message_queue, 
            self.api_endpoint, 
            self.thinker_system_prompt, 
            self.thinker_schema
        )
        
        # Start autonomous shards
        self.autonomous_curator.start()
        self.autonomous_thinker.start()
        logger.info("Autonomous shards initialized and started")

    def _api_talk(self, message: str, url: str) -> dict:
        """Send Message to API endpoint and return response."""
        headers = {
            "Content-Type": "application/json"
        }
        response = requests.post(f"{self.api_endpoint}/{url}", headers=headers, json=message)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API error {response.status_code}: {response.text}")
            logger.debug(f"Failed request payload: {json.dumps(message)}")
            raise Exception(f"API error: {response.status_code} - {response.text}")
        
        
    def _curate(self, message: str, chunk: str=None) -> dict[str, Any]:
        """Send Message to curator model"""
        curator_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.curator_system_prompt},
                {"role": "user", "content": message}
            ],
            "response_format": self.curator_schema,
            "temperature": 0,
            "max_tokens": -1,
            "stream": False
        }
        if chunk:
            curator_message["messages"].append({"role": "system", "content": f"Long input split into chunks. Directive: Store all information for later synthesis."})
            curator_message["messages"].append({"role": "system", "content": f"Chunk info: {chunk}"})

        response = self._api_talk(curator_message, url="v1/chat/completions")
        logger.debug(f"Curator response: {response}")
        fresh_data_to_store, context_retrieval_queries, context_focus, curiosity_analysis = self._parse_curator_response(response)
        handler_output = self.curator_handler.process_curator_output({
            "fresh_data_to_store": fresh_data_to_store,
            "context_retrieval_queries": context_retrieval_queries,
        })

        from_conversations = self.db_handler.retrieve_from_conversations(
            entities=handler_output.get("entities", []),
            semantic_tags=handler_output.get("semantic_tags", []),
            timeframe="recent",
            limit=5
        )

        # Summarize conversationhistory
        for conv in from_conversations:
            if len(conv.get("user_input", "")) > 150:
                conv["user_input_summary"] = self._summarize_for_memory(conv["user_input"])
            else:
                conv["user_input_summary"] = conv["user_input"]
            if len(conv.get("assistant_response", "")) > 150:
                conv["assistant_response_summary"] = self._summarize_for_memory(conv["assistant_response"])
            else:
                conv["assistant_response_summary"] = conv["assistant_response"]
        
        return {
            "context_focus": context_focus,
            "curiosity_analysis": curiosity_analysis,
            "retrieved_context": handler_output,
            "from_conversations": from_conversations
        }
    
    def _summarize_for_memory(self, message: str) -> str:
        """Summarize message for long-term memory storage."""
        summary_prompt = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.summarizer_system_prompt},
                {"role": "user", "content": message}
            ],
            "response_format": self.summarizer_schema,
            "temperature": 0,
            "max_tokens": 100,
            "stream": False
        }
        response = self._api_talk(summary_prompt, url="v1/chat/completions")
        if response.get("choices"):
            try:
                summary_data = json.loads(response["choices"][0].get("message", {}).get("content", "{}"))
                return summary_data.get("summary", message[:150])
            except json.JSONDecodeError:
                logger.error("Failed to parse summarizer response as JSON")
                return message[:150]
        else:
            logger.error("Summarization returned no choices")
            return message[:150]


    def _think(self, message: str, curator_analysis: dict) -> tuple[dict[str, Any], bool]:
        """Think about the curator provided data. return true if we need to query curator."""
        thinker_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.thinker_system_prompt},
                {"role": "system", "content": "Curator data: " + json.dumps(curator_analysis, cls=MongoJSONEncoder)},
                {"role": "user", "content": f"Orginal user message: {message}"}
            ],
            "response_format": self.thinker_schema,
            "temperature": 0,
            "max_tokens": -1,
            "stream": False
        }

        response = self._api_talk(thinker_message, url="v1/chat/completions")
        logger.debug(f"Thinker response: {response}")
        try:
            think_data = json.loads(response.get("choices", [{}])[0].get("message", {}).get("content", "{}"))
        except json.JSONDecodeError:
            logger.error("Failed to parse thinker response as JSON")
            return {}, False
        return think_data, False  # Flag lets add rethinking logic later
    
    def _build_response(self, think_data: dict[str, Any], message: str, timestamp: str) -> str:
        response_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.response_generator_system_prompt},
                {"role": "system", "content": "Thinker data: " + json.dumps(think_data, cls=MongoJSONEncoder)},
                {"role": "system", "content": f"Current time is {timestamp}"},
                {"role": "user", "content": f"Original user message: {message}"}
            ],
            "response_format": self.response_generator_schema,
            "temperature": 0.7,
        }
        response = self._api_talk(response_message, url="v1/chat/completions")
        if response.get("choices"):
            return response["choices"][0].get("message", {}).get("content", "")
        else:
            logger.error("Response generator returned no choices")
            return "I'm not sure how to respond to that right now."
        
    def _parse_curator_response(self, response: dict) -> tuple:
        """Parse the curator response and extract relevant data."""
        try:
            curator_analysis = json.loads(response.get("choices", [{}])[0].get("message", {}).get("content", ""))
        except json.JSONDecodeError:
            logger.error("Failed to parse curator response as JSON")
            return {}, [], {}, {}
        
        fresh_data_to_store = curator_analysis.get("fresh_data_to_store", {})
        context_retrieval_queries = curator_analysis.get("context_retrieval_queries", {})
        context_focus = curator_analysis.get("context_focus", {})
        curiosity_analysis = curator_analysis.get("curiosity_analysis", {})
        return fresh_data_to_store, context_retrieval_queries, context_focus, curiosity_analysis
    
    def _process_big_input(self, message: str) -> dict[str, Any]:
        """Split big input into smaller chunks if needed."""
        max_chunk_size = 4096
        if len(message) <= max_chunk_size:
            return self._curate(message), self._summarize_for_memory(message)
        # Split by sentences for better coherence
        sentences = re.split(r'(?<=[.!?]) +', message)
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        if current_chunk:
            chunks.append(current_chunk)
        combined_analysis = {
            "context_focus": {},
            "curiosity_analysis": {},
            "retrieved_context": {
                "entities": [],
                "semantic_tags": []
            }
        }
        summary_chunks = []
        # TODO: test if we should think about chunked input and collect all that
        logger.info(f"Input message split into {len(chunks)} chunks for curation")
        for i, chunk in enumerate(chunks):
            logger.debug(f"Processing chunk {i+1}/{len(chunks)}")
            chunk_analysis = self._curate(chunk, chunk=f"Chunk {i+1} of {len(chunks)}")
            summary_chunks.append(self._summarize_for_memory(chunk))
            # Combine retrieved context
            for key in ["entities", "semantic_tags"]:
                combined_analysis["retrieved_context"][key].extend(chunk_analysis.get("retrieved_context", {}).get(key, []))
            # Merge context_focus and curiosity_analysis (simple overwrite for now)
            combined_analysis["context_focus"].update(chunk_analysis.get("context_focus", {}))
            combined_analysis["curiosity_analysis"].update(chunk_analysis.get("curiosity_analysis", {}))
            logger.debug(f"Chunk analysis: {chunk_analysis} \n {i+1}/{len(chunks)}")
        
        # Deduplicate entities and semantic tags
        combined_analysis["retrieved_context"]["entities"] = list(set(combined_analysis["retrieved_context"]["entities"]))
        combined_analysis["retrieved_context"]["semantic_tags"] = list(set(combined_analysis["retrieved_context"]["semantic_tags"]))

        return combined_analysis, summary_chunks

    def chat(self, message: str) -> str:
        """Process a chat message and return a response."""
        timestamp = datetime.now().isoformat()
        logger.info(f"Received message at {timestamp}: {message}")
        
        # Check for proactive messages first
        proactive_response = self.check_proactive_messages()
        if proactive_response:
            # Return proactive message but don't store as conversation
            return proactive_response
        
        message += f" [{timestamp}]"
        message += f" [username: {self.username}]"

        curator_analysis = self._process_big_input(message)
        think_data, needs_curator = self._think(message, curator_analysis)
        if needs_curator:
            logger.info("Rethinking required, querying curator again...")
            # TODO: fire up curator again with thinker data

        response_text = self._build_response(think_data, message, timestamp)
        # Store the conversation turn
        self.db_handler.store_conversation(
            user_input=message,
            assistant_response=response_text,
            entities=curator_analysis.get("retrieved_context", {}).get("entities", []),
            semantic_tags=curator_analysis.get("retrieved_context", {}).get("semantic_tags", [])
        )
        return response_text
    
    def chat_stream(self, message: str):
        """Generator to stream chat response."""
        timestamp = datetime.now().isoformat()
        logger.info(f"Received message at {timestamp}: {message}")
        
        # Check for proactive messages first
        proactive_response = self.check_proactive_messages()
        if proactive_response:
            # Stream proactive message
            yield f"event: proactive\ndata: {json.dumps({'message': proactive_response})}\n\n"
            yield f"event: token\ndata: {json.dumps({'text': proactive_response})}\n\n"
            return
        
        message += f" [{timestamp}]"
        message += f" [username: {self.username}]"
        yield "event: status\ndata: {\"message\": \"thinking\"}\n\n"
        curator_analysis, summarised_message = self._process_big_input(message)
        yield "event: status\ndata: {\"message\": \"formulating\"}\n\n"
        think_data, needs_curator = self._think(message, curator_analysis)
        yield "event: status\ndata: {\"message\": \"pondering\"}\n\n"
        if needs_curator:
            logger.info("Rethinking required, querying curator again...")
            # fire up curator again with thinker data

        response_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.response_generator_system_prompt},
                {"role": "system", "content": "Thinker data: " + json.dumps(think_data, cls=MongoJSONEncoder)},
                {"role": "system", "content": f"Current time is {timestamp}"},
                {"role": "user", "content": f"Original user message: {message}"}
            ],
            "response_format": self.response_generator_schema,
            "temperature": 0.7,
            "stream": True,
        }

        emote_pattern = re.compile(r"(\[.*?\])")
        
        with requests.post(f"{self.api_endpoint}/v1/chat/completions", json=response_message, stream=True) as response:
            response.raise_for_status()
            buffer = ""
            processed_content = ""
            
            for line in response.iter_lines():
                if not line:
                    continue
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[5:].strip()
                    if json_str == "[DONE]":
                        break
                    try:
                        data = json.loads(json_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content_chunk = delta.get("content", "")
                        if content_chunk:
                            buffer += content_chunk
                            
                            # Process complete emotes and text
                            while True:
                                emote_match = emote_pattern.search(buffer)
                                if emote_match:
                                    # Send text before emote
                                    text_before = buffer[:emote_match.start()]
                                    if text_before:
                                        yield f"event: token\ndata: {json.dumps({'text': text_before})}\n\n"
                                        processed_content += text_before
                                    
                                    # Send emote
                                    emote_name = emote_match.group(1).strip("[]")
                                    yield f"event: emote\ndata: {json.dumps({'name': emote_name})}\n\n"
                                    processed_content += emote_match.group(1)
                                    
                                    # Remove processed part from buffer
                                    buffer = buffer[emote_match.end():]
                                else:
                                    # No complete emote found, check if buffer might contain incomplete emote
                                    bracket_pos = buffer.rfind('[')
                                    if bracket_pos == -1:
                                        # No opening bracket, send all as text
                                        if buffer:
                                            yield f"event: token\ndata: {json.dumps({'text': buffer})}\n\n"
                                            processed_content += buffer
                                            buffer = ""
                                        break
                                    else:
                                        # Send text before potential incomplete emote
                                        if bracket_pos > 0:
                                            text_part = buffer[:bracket_pos]
                                            yield f"event: token\ndata: {json.dumps({'text': text_part})}\n\n"
                                            processed_content += text_part
                                            buffer = buffer[bracket_pos:]
                                        break
                                        
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode JSON from stream: {json_str}")
            
            # Send any remaining buffer content
            if buffer:
                yield f"event: token\ndata: {json.dumps({'text': buffer})}\n\n"
                processed_content += buffer
        
        try:
            final_response_data = json.loads(processed_content)
            assistant_response = final_response_data.get("response", processed_content)
        except json.JSONDecodeError:
            assistant_response = processed_content
        # Store the conversation turn
        # TODO: if user message is huge, we should store chunked analysis
        if isinstance(summarised_message, list):
            for summary in summarised_message:
                self.db_handler.store_conversation(
                    user_input=summary,
                    assistant_response=assistant_response,
                    entities=curator_analysis.get("retrieved_context", {}).get("entities", []),
                    semantic_tags=curator_analysis.get("retrieved_context", {}).get("semantic_tags", [])
                )
        else:
            self.db_handler.store_conversation(
                user_input=message,
                assistant_response=assistant_response,
                entities=curator_analysis.get("retrieved_context", {}).get("entities", []),
                semantic_tags=curator_analysis.get("retrieved_context", {}).get("semantic_tags", [])
            )

    def store_conversation(self, user_input: str, assistant_response: str, entities: list[str], semantic_tags: list[str]) -> None:
        """Public method to store a conversation turn."""
        self.db_handler.store_conversation(user_input, assistant_response, entities, semantic_tags)

    def shutdown(self):
        """Gracefully shutdown autonomous shards"""
        logger.info("Shutting down Carlos...")
        self.autonomous_curator.stop()
        self.autonomous_thinker.stop()
        logger.info("Carlos shutdown complete")

    def check_proactive_messages(self, context: Dict[str, Any] = None) -> Optional[str]:
        """Check if there are any proactive messages ready to inject"""
        context = context or {}
        
        if self.message_queue.should_inject(context):
            proactive_msg = self.message_queue.get_next_message()
            if proactive_msg:
                logger.info(f"Injecting proactive message: {proactive_msg['type']}")
                return self._format_proactive_message(proactive_msg)
        
        return None

    def _format_proactive_message(self, proactive_msg: Dict[str, Any]) -> str:
        """Format a proactive message for display"""
        shard_type = proactive_msg.get('shard_type', 'unknown')
        message_type = proactive_msg.get('type', 'thought')
        content = proactive_msg.get('content', '')
        
        # Add visual indicators based on shard type and message type
        if shard_type == 'curator' and message_type == 'pattern_insight':
            return f"🔍 *noticing patterns* {content}"
        elif shard_type == 'thinker' and message_type == 'deep_insight':
            return f"💭 *deep thought* {content}"
        elif message_type == 'information_request':
            return f"❓ *curious* {content}"
        elif message_type == 'spontaneous_insight':
            return f"💡 *insight* {content}"
        else:
            return f"🤔 *{shard_type}* {content}"

    def get_internal_thoughts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent internal thoughts for monitoring panel"""
        try:
            # Get both internal thoughts and thinking chains
            internal_thoughts = self.db_handler.get_collection("internal_thoughts")
            thinking_chains = self.db_handler.get_collection("thinking_chains")
            
            # Get internal thoughts
            thoughts = list(internal_thoughts.find({}, {
                "timestamp": 1,
                "type": 1,
                "insight": 1,
                "suggested_step": 1,
                "original_context": 1,
                "urgency": 1
            }).sort("timestamp", -1).limit(limit // 2))
            
            # Get thinking chains
            chains = list(thinking_chains.find({}, {
                "timestamp": 1,
                "novel_insight": 1,
                "actionable_insight": 1,
                "confidence": 1,
                "depth": 1,
                "thinking_cycles": 1,
                "synthesis": 1
            }).sort("timestamp", -1).limit(limit // 2))
            
            # Combine and sort by timestamp
            all_thoughts = []
            
            for thought in thoughts:
                thought["source"] = "internal"
                all_thoughts.append(thought)
            
            for chain in chains:
                chain["source"] = "cyclical"
                chain["type"] = "cyclical_thinking"
                # Map fields for consistency
                chain["insight"] = chain.get("novel_insight", "")
                chain["suggested_step"] = chain.get("actionable_insight", "")
                chain["urgency"] = chain.get("confidence", 0.5)
                all_thoughts.append(chain)
            
            # Sort by timestamp and limit
            all_thoughts.sort(key=lambda x: x.get("timestamp", datetime.min), reverse=True)
            return all_thoughts[:limit]
            
        except Exception as e:
            logger.error(f"Error getting internal thoughts: {e}")
            return []

    def get_debug_info(self, message: str) -> Dict[str, Any]:
        response = requests.post(f"{self.api_endpoint}/debug", json={"message": message})
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Debug API error: {response.status_code} - {response.text}")

        

if __name__ == "__main__":
    carlos = Carlos()
    print("Carlos initialized with MongoDB client and API endpoint.")

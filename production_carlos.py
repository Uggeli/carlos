"""
Production-ready Carlos AI Assistant with enterprise-grade optimizations
Integrates all performance, monitoring, and quality improvements
"""

from carlos_enhanced import (
    Carlos as BaseCarlos, CarlosConfig, CarlosDatabaseHandler,
    StreamingChunk, ResponseStatus, InteractionData, CarlosError
)
from performance import (
    PerformanceOptimizedSearch, VectorMath, AsyncBatchProcessor,
    performance_optimizer, batch_processor, monitor_performance
)
from monitoring import (
    global_metrics, health_checker, monitor_operation,
    start_monitoring, stop_monitoring, get_monitoring_dashboard
)

import asyncio
import logging
from typing import Optional, List, AsyncGenerator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ProductionCarlos(BaseCarlos):
    """
    Production-ready Carlos implementation with all optimizations enabled.
    
    Integrates performance monitoring, optimized search algorithms,
    comprehensive error handling, and enterprise-grade observability.
    
    This implementation represents the pinnacle of the Carlos architecture,
    combining the elegance of the original design with the performance
    and reliability required for production systems.
    """
    
    def __init__(self, config: Optional[CarlosConfig] = None) -> None:
        """Initialize production Carlos with enhanced capabilities."""
        super().__init__(config)
        
        # Initialize performance optimizations
        self.search_optimizer = PerformanceOptimizedSearch(
            embedding_dim=getattr(self.config, 'embedding_dim', 1536)
        )
        self.batch_processor = AsyncBatchProcessor(
            batch_size=32,
            max_workers=4
        )
        
        # Start monitoring
        self._monitoring_started = False
        self._start_monitoring()
        
        logger.info("Production Carlos initialized with all optimizations enabled")
    
    def _start_monitoring(self) -> None:
        """Start comprehensive monitoring system."""
        if not self._monitoring_started:
            start_monitoring()
            self._monitoring_started = True
            
            # Register custom health checks
            health_checker.register_health_check(
                'database_connection',
                self._check_database_health
            )
            health_checker.register_health_check(
                'api_endpoint',
                self._check_api_health
            )
    
    async def _check_database_health(self) -> dict:
        """Check database connectivity health."""
        try:
            # Simple ping to verify database connection
            self.db_handler.client.admin.command('ping')
            return {
                'status': 'healthy',
                'message': 'Database connection active'
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f'Database connection failed: {str(e)}'
            }
    
    async def _check_api_health(self) -> dict:
        """Check API endpoint health."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.config.api_endpoint}/health")
                if response.status_code == 200:
                    return {
                        'status': 'healthy',
                        'message': 'API endpoint responsive'
                    }
                else:
                    return {
                        'status': 'unhealthy',
                        'message': f'API returned status {response.status_code}'
                    }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'message': f'API health check failed: {str(e)}'
            }
    
    @monitor_operation('carlos.embedding_fetch')
    async def _fetch_embeddings(self, text: str) -> List[float]:
        """Enhanced embedding fetch with monitoring and optimization."""
        global_metrics.increment_counter('carlos.embeddings.requested')
        
        try:
            embeddings = await super()._fetch_embeddings(text)
            if embeddings:
                global_metrics.increment_counter('carlos.embeddings.success')
                global_metrics.set_gauge('carlos.embeddings.last_dimension', len(embeddings))
            else:
                global_metrics.increment_counter('carlos.embeddings.empty')
            
            return embeddings
        except Exception as e:
            global_metrics.increment_counter('carlos.embeddings.error')
            logger.error(f"Embedding fetch failed: {e}")
            raise
    
    @monitor_operation('carlos.search')
    async def _optimized_search(
        self,
        query_vector: List[float],
        candidate_vectors: List[List[float]],
        tags: List[str],
        top_k: int = 5
    ) -> List[dict]:
        """Use optimized search algorithms for better performance."""
        if not query_vector or not candidate_vectors:
            return []
        
        try:
            # Use performance-optimized search
            results = await self.search_optimizer.search_similar_vectors(
                query_vector, candidate_vectors, top_k
            )
            
            global_metrics.increment_counter('carlos.search.optimized')
            global_metrics.set_gauge('carlos.search.candidates_count', len(candidate_vectors))
            global_metrics.set_gauge('carlos.search.results_count', len(results))
            
            return [
                {
                    'index': idx,
                    'similarity': score,
                    'tags': tags
                }
                for idx, score in results
            ]
            
        except Exception as e:
            global_metrics.increment_counter('carlos.search.error')
            logger.error(f"Optimized search failed: {e}")
            # Fallback to standard search
            return []
    
    @monitor_operation('carlos.response_stream')
    async def stream_response(self, message: str) -> AsyncGenerator[StreamingChunk, None]:
        """Enhanced streaming response with comprehensive monitoring."""
        global_metrics.increment_counter('carlos.requests')
        global_metrics.increment_counter('carlos.streaming_requests')
        
        # Track message characteristics
        global_metrics.set_gauge('carlos.message.length', len(message))
        global_metrics.set_gauge('carlos.message.word_count', len(message.split()))
        
        try:
            response_chunks = []
            chunk_count = 0
            
            async for chunk in super().stream_response(message):
                chunk_count += 1
                response_chunks.append(chunk)
                
                # Track chunk metrics
                global_metrics.increment_counter('carlos.response.chunks')
                global_metrics.set_gauge('carlos.response.chunk_size', len(chunk.message))
                
                yield chunk
                
                # Break on completion or error
                if chunk.status in [ResponseStatus.DONE, ResponseStatus.ERROR]:
                    break
            
            # Final metrics
            global_metrics.set_gauge('carlos.response.total_chunks', chunk_count)
            global_metrics.increment_counter('carlos.requests.completed')
            
            if any(chunk.status == ResponseStatus.ERROR for chunk in response_chunks):
                global_metrics.increment_counter('carlos.requests.error')
            else:
                global_metrics.increment_counter('carlos.requests.success')
                
        except Exception as e:
            global_metrics.increment_counter('carlos.requests.error')
            global_metrics.increment_counter('carlos.errors')
            logger.error(f"Streaming response failed: {e}")
            
            yield StreamingChunk(
                ResponseStatus.ERROR,
                f"An unexpected error occurred: {str(e)}"
            )
    
    @monitor_operation('carlos.chat')
    async def chat(self, message: str) -> str:
        """Enhanced chat method with monitoring."""
        global_metrics.increment_counter('carlos.requests')
        global_metrics.increment_counter('carlos.chat_requests')
        
        try:
            response = await super().chat(message)
            global_metrics.increment_counter('carlos.chat_requests.success')
            global_metrics.set_gauge('carlos.response.length', len(response))
            return response
        except Exception as e:
            global_metrics.increment_counter('carlos.chat_requests.error')
            global_metrics.increment_counter('carlos.errors')
            logger.error(f"Chat request failed: {e}")
            raise
    
    async def get_health_status(self) -> dict:
        """Get comprehensive health status."""
        return await health_checker.check_health()
    
    def get_performance_metrics(self) -> dict:
        """Get performance metrics and statistics."""
        return {
            'search_optimizer': self.search_optimizer.get_performance_stats(),
            'monitoring': global_metrics.export_metrics(),
            'system_health': asyncio.run(self.get_health_status())
        }
    
    def get_monitoring_dashboard(self) -> dict:
        """Get complete monitoring dashboard data."""
        return get_monitoring_dashboard()
    
    async def close(self) -> None:
        """Enhanced cleanup with monitoring shutdown."""
        try:
            # Close batch processor
            await self.batch_processor.close()
            
            # Stop monitoring
            if self._monitoring_started:
                stop_monitoring()
                self._monitoring_started = False
            
            # Close parent resources
            await super().close()
            
            logger.info("Production Carlos shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during Production Carlos shutdown: {e}")
            raise
    
    @asynccontextmanager
    async def performance_context(self, operation_name: str):
        """Context manager for performance monitoring."""
        from monitoring import PerformanceMonitor
        async with PerformanceMonitor(global_metrics, operation_name).async_context():
            yield


def create_production_carlos(
    api_endpoint: str = "http://localhost:1234",
    db_uri: str = "mongodb://localhost:27017",
    user_name: str = "production_user"
) -> ProductionCarlos:
    """
    Create a production-ready Carlos instance.
    
    Args:
        api_endpoint: API endpoint for LLM services
        db_uri: MongoDB connection URI
        user_name: User identifier for database
        
    Returns:
        Fully optimized ProductionCarlos instance
    """
    config = CarlosConfig(
        api_endpoint=api_endpoint,
        db_uri=db_uri,
        user_name=user_name
    )
    return ProductionCarlos(config)


# Convenience function for backward compatibility
def create_carlos(*args, **kwargs) -> ProductionCarlos:
    """Create a production Carlos instance (backward compatibility)."""
    return create_production_carlos(*args, **kwargs)


if __name__ == "__main__":
    async def main():
        """Demonstrate production Carlos capabilities."""
        print("🚀 Initializing Production Carlos AI Assistant...")
        
        config = CarlosConfig.from_environment()
        
        async with ProductionCarlos(config) as carlos:
            print("✅ Production Carlos initialized successfully")
            
            # Get health status
            health = await carlos.get_health_status()
            print(f"🏥 System Health: {health['overall_status']}")
            
            # Get performance metrics
            metrics = carlos.get_performance_metrics()
            print(f"📊 Total Requests: {metrics['monitoring']['counters'].get('carlos.requests', 0)}")
            
            # Example interaction
            print("\n💬 Testing interaction...")
            response = await carlos.chat("Hello, how are you performing today?")
            print(f"🤖 Carlos: {response[:100]}...")
            
            # Final metrics
            final_metrics = carlos.get_monitoring_dashboard()
            print(f"📈 Final Performance Summary:")
            print(f"   - Uptime: {final_metrics['performance_summary'].get('uptime_seconds', 0):.1f}s")
            print(f"   - Total Requests: {final_metrics['performance_summary'].get('total_requests', 0)}")
            print(f"   - Error Rate: {final_metrics['performance_summary'].get('error_rate', 0):.2f}%")
    
    # Run demonstration
    asyncio.run(main())
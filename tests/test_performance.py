"""
Performance and benchmarking tests for the enhanced Carlos AI Assistant
Validates that all optimizations work correctly and provide performance benefits
"""
import pytest
import asyncio
import numpy as np
import time
from unittest.mock import Mock, patch, AsyncMock

# Import enhanced modules
from performance import VectorMath, PerformanceOptimizedSearch, AsyncBatchProcessor
from monitoring import MetricsCollector, PerformanceMonitor, HealthChecker
from production_carlos import ProductionCarlos, create_production_carlos


class TestVectorMath:
    """Test suite for optimized vector mathematics."""
    
    def test_cosine_similarity_fast(self):
        """Test fast cosine similarity calculation."""
        a = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        b = np.array([2.0, 3.0, 4.0], dtype=np.float32)
        
        similarity = VectorMath.cosine_similarity_fast(a, b)
        
        # Manual calculation for verification
        expected = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
        
        assert abs(similarity - expected) < 1e-6
        assert -1.0 <= similarity <= 1.0
    
    def test_cosine_similarity_zero_vectors(self):
        """Test cosine similarity with zero vectors."""
        a = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        
        similarity = VectorMath.cosine_similarity_fast(a, b)
        assert similarity == 0.0
    
    def test_batch_cosine_similarity(self):
        """Test vectorized cosine similarity computation."""
        query = np.array([1.0, 0.0, 1.0], dtype=np.float32)
        vectors = np.array([
            [1.0, 0.0, 1.0],  # Identical vector
            [0.0, 1.0, 0.0],  # Orthogonal vector
            [-1.0, 0.0, -1.0]  # Opposite vector
        ], dtype=np.float32)
        
        similarities = VectorMath.batch_cosine_similarity(query, vectors)
        
        assert len(similarities) == 3
        assert abs(similarities[0] - 1.0) < 1e-6  # Identical
        assert abs(similarities[1] - 0.0) < 1e-6  # Orthogonal
        assert abs(similarities[2] - (-1.0)) < 1e-6  # Opposite
    
    def test_euclidean_distance_squared(self):
        """Test squared Euclidean distance calculation."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([4.0, 5.0, 6.0])
        
        distance_sq = VectorMath.euclidean_distance_squared(a, b)
        expected = sum((a[i] - b[i])**2 for i in range(len(a)))
        
        assert abs(distance_sq - expected) < 1e-6


class TestPerformanceOptimizedSearch:
    """Test suite for performance-optimized search functionality."""
    
    @pytest.fixture
    def search_optimizer(self):
        """Create a search optimizer instance for testing."""
        return PerformanceOptimizedSearch(embedding_dim=4)
    
    @pytest.mark.asyncio
    async def test_search_similar_vectors(self, search_optimizer):
        """Test optimized vector similarity search."""
        query_vector = [1.0, 0.0, 1.0, 0.0]
        candidate_vectors = [
            [1.0, 0.0, 1.0, 0.0],  # Identical
            [0.0, 1.0, 0.0, 1.0],  # Different
            [0.5, 0.0, 0.5, 0.0],  # Similar
            [-1.0, 0.0, -1.0, 0.0]  # Opposite
        ]
        
        results = await search_optimizer.search_similar_vectors(
            query_vector, candidate_vectors, top_k=3
        )
        
        assert len(results) == 3
        # First result should be the identical vector
        assert results[0][0] == 0  # Index of identical vector
        assert results[0][1] > 0.9  # High similarity
    
    @pytest.mark.asyncio
    async def test_search_performance_caching(self, search_optimizer):
        """Test that search results are cached for performance."""
        query_vector = [1.0, 0.0, 1.0, 0.0]
        candidate_vectors = [
            [1.0, 0.0, 1.0, 0.0],
            [0.0, 1.0, 0.0, 1.0]
        ]
        
        # First search
        start_time = time.perf_counter()
        results1 = await search_optimizer.search_similar_vectors(
            query_vector, candidate_vectors, top_k=2
        )
        first_search_time = time.perf_counter() - start_time
        
        # Second search (should be cached)
        start_time = time.perf_counter()
        results2 = await search_optimizer.search_similar_vectors(
            query_vector, candidate_vectors, top_k=2
        )
        second_search_time = time.perf_counter() - start_time
        
        assert results1 == results2
        # Second search should be significantly faster due to caching
        # (This test might be flaky on very fast systems)
        assert search_optimizer.performance_metrics['cache_hits'] > 0
    
    def test_performance_stats(self, search_optimizer):
        """Test performance statistics collection."""
        stats = search_optimizer.get_performance_stats()
        
        assert 'search_count' in stats
        assert 'cache_hits' in stats
        assert 'avg_search_time' in stats
        assert all(isinstance(v, (int, float)) for v in stats.values())


class TestAsyncBatchProcessor:
    """Test suite for asynchronous batch processing."""
    
    @pytest.fixture
    def batch_processor(self):
        """Create a batch processor instance for testing."""
        return AsyncBatchProcessor(batch_size=2, max_workers=2)
    
    @pytest.mark.asyncio
    async def test_process_embeddings_batch(self, batch_processor):
        """Test batch processing of embeddings."""
        texts = ["hello", "world", "test", "batch"]
        
        # Mock embedding function
        def mock_embedding_func(batch_texts):
            return [[1.0, 0.0] for _ in batch_texts]
        
        embeddings = await batch_processor.process_embeddings_batch(
            texts, mock_embedding_func
        )
        
        assert len(embeddings) == len(texts)
        assert all(len(emb) == 2 for emb in embeddings)
    
    @pytest.mark.asyncio
    async def test_empty_batch_processing(self, batch_processor):
        """Test batch processing with empty input."""
        def mock_embedding_func(batch_texts):
            return []
        
        embeddings = await batch_processor.process_embeddings_batch(
            [], mock_embedding_func
        )
        
        assert embeddings == []
    
    @pytest.mark.asyncio
    async def test_batch_processor_cleanup(self, batch_processor):
        """Test proper cleanup of batch processor resources."""
        await batch_processor.close()
        # Should not raise an exception


class TestMetricsCollector:
    """Test suite for metrics collection system."""
    
    @pytest.fixture
    def metrics_collector(self):
        """Create a metrics collector for testing."""
        return MetricsCollector(max_metrics=100, retention_hours=1)
    
    def test_counter_operations(self, metrics_collector):
        """Test counter metric operations."""
        metrics_collector.increment_counter('test.counter', 5.0)
        metrics_collector.increment_counter('test.counter', 3.0)
        
        assert metrics_collector.get_counter('test.counter') == 8.0
    
    def test_gauge_operations(self, metrics_collector):
        """Test gauge metric operations."""
        metrics_collector.set_gauge('test.gauge', 42.0)
        assert metrics_collector.get_gauge('test.gauge') == 42.0
        
        metrics_collector.set_gauge('test.gauge', 24.0)
        assert metrics_collector.get_gauge('test.gauge') == 24.0
    
    def test_timer_operations(self, metrics_collector):
        """Test timer metric operations."""
        metrics_collector.record_time('test.timer', 100.0)
        metrics_collector.record_time('test.timer', 200.0)
        metrics_collector.record_time('test.timer', 150.0)
        
        stats = metrics_collector.get_timer_stats('test.timer')
        
        assert stats['count'] == 3
        assert stats['min'] == 100.0
        assert stats['max'] == 200.0
        assert stats['avg'] == 150.0
    
    def test_metrics_export(self, metrics_collector):
        """Test metrics export functionality."""
        metrics_collector.increment_counter('test.requests', 10)
        metrics_collector.set_gauge('test.memory', 75.5)
        metrics_collector.record_time('test.response_time', 125.0)
        
        exported = metrics_collector.export_metrics()
        
        assert 'timestamp' in exported
        assert 'counters' in exported
        assert 'gauges' in exported
        assert 'timers' in exported
        assert exported['counters']['test.requests'] == 10
        assert exported['gauges']['test.memory'] == 75.5


class TestPerformanceMonitor:
    """Test suite for performance monitoring context manager."""
    
    @pytest.fixture
    def metrics_collector(self):
        """Create a metrics collector for testing."""
        return MetricsCollector()
    
    def test_performance_monitor_success(self, metrics_collector):
        """Test performance monitor with successful operation."""
        with PerformanceMonitor(metrics_collector, 'test.operation'):
            time.sleep(0.01)  # Simulate some work
        
        assert metrics_collector.get_counter('test.operation.started') == 1
        assert metrics_collector.get_counter('test.operation.success') == 1
        assert metrics_collector.get_counter('test.operation.error') == 0
        
        timer_stats = metrics_collector.get_timer_stats('test.operation.duration')
        assert timer_stats['count'] == 1
        assert timer_stats['avg'] > 0
    
    def test_performance_monitor_error(self, metrics_collector):
        """Test performance monitor with failed operation."""
        try:
            with PerformanceMonitor(metrics_collector, 'test.error_operation'):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        assert metrics_collector.get_counter('test.error_operation.started') == 1
        assert metrics_collector.get_counter('test.error_operation.success') == 0
        assert metrics_collector.get_counter('test.error_operation.error') == 1
    
    @pytest.mark.asyncio
    async def test_async_performance_monitor(self, metrics_collector):
        """Test async performance monitoring."""
        monitor = PerformanceMonitor(metrics_collector, 'test.async_operation')
        
        async with monitor.async_context():
            await asyncio.sleep(0.01)
        
        assert metrics_collector.get_counter('test.async_operation.started') == 1
        assert metrics_collector.get_counter('test.async_operation.success') == 1


class TestHealthChecker:
    """Test suite for health checking system."""
    
    @pytest.fixture
    def health_checker(self):
        """Create a health checker for testing."""
        from monitoring import MetricsCollector, HealthChecker
        metrics = MetricsCollector()
        return HealthChecker(metrics)
    
    @pytest.mark.asyncio
    async def test_basic_health_check(self, health_checker):
        """Test basic health check functionality."""
        health_status = await health_checker.check_health()
        
        assert 'overall_status' in health_status
        assert 'timestamp' in health_status
        assert 'checks' in health_status
        assert 'metrics' in health_status
        assert health_status['overall_status'] in ['healthy', 'unhealthy']
    
    def test_custom_health_check_registration(self, health_checker):
        """Test custom health check registration."""
        def custom_check():
            return {'status': 'healthy', 'message': 'Custom check passed'}
        
        health_checker.register_health_check('custom', custom_check)
        assert 'custom' in health_checker.health_checks
    
    def test_threshold_configuration(self, health_checker):
        """Test health threshold configuration."""
        health_checker.set_threshold('cpu_percent', 90.0)
        assert health_checker.thresholds['cpu_percent'] == 90.0


class TestProductionCarlos:
    """Test suite for the production Carlos implementation."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        from carlos_enhanced import CarlosConfig
        return CarlosConfig(
            api_endpoint="http://localhost:1234",
            db_uri="mongodb://localhost:27017/test",
            user_name="test_production"
        )
    
    @pytest.mark.asyncio
    async def test_production_carlos_initialization(self, mock_config):
        """Test production Carlos initialization."""
        with patch('carlos_enhanced.CarlosDatabaseHandler'), \
             patch.object(ProductionCarlos, '_load_prompts_and_schemas'), \
             patch.object(ProductionCarlos, '_initialize_agents'), \
             patch('monitoring.start_monitoring'):
            
            carlos = ProductionCarlos(mock_config)
            assert carlos.config == mock_config
            assert hasattr(carlos, 'search_optimizer')
            assert hasattr(carlos, 'batch_processor')
    
    @pytest.mark.asyncio
    async def test_health_checks(self, mock_config):
        """Test production Carlos health checking."""
        with patch('carlos_enhanced.CarlosDatabaseHandler'), \
             patch.object(ProductionCarlos, '_load_prompts_and_schemas'), \
             patch.object(ProductionCarlos, '_initialize_agents'), \
             patch('monitoring.start_monitoring'):
            
            carlos = ProductionCarlos(mock_config)
            
            # Mock the health check methods
            carlos._check_database_health = AsyncMock(return_value={
                'status': 'healthy',
                'message': 'Database connection active'
            })
            carlos._check_api_health = AsyncMock(return_value={
                'status': 'healthy',
                'message': 'API endpoint responsive'
            })
            
            health_status = await carlos.get_health_status()
            assert 'overall_status' in health_status
    
    def test_create_production_carlos(self):
        """Test production Carlos factory function."""
        with patch('carlos_enhanced.CarlosDatabaseHandler'), \
             patch.object(ProductionCarlos, '_load_prompts_and_schemas'), \
             patch.object(ProductionCarlos, '_initialize_agents'), \
             patch('monitoring.start_monitoring'):
            
            carlos = create_production_carlos(
                api_endpoint="http://test:1234",
                db_uri="mongodb://test:27017",
                user_name="test_user"
            )
            
            assert isinstance(carlos, ProductionCarlos)
            assert carlos.config.api_endpoint == "http://test:1234"
            assert carlos.config.user_name == "test_user"


class TestPerformanceBenchmarks:
    """Performance benchmark tests to validate optimizations."""
    
    def test_vector_math_performance(self):
        """Benchmark vector math operations."""
        # Generate test data
        query = np.random.rand(1536).astype(np.float32)
        vectors = np.random.rand(1000, 1536).astype(np.float32)
        
        # Benchmark batch cosine similarity
        start_time = time.perf_counter()
        similarities = VectorMath.batch_cosine_similarity(query, vectors)
        elapsed = time.perf_counter() - start_time
        
        assert len(similarities) == 1000
        assert elapsed < 1.0  # Should complete in under 1 second
        
        # Log performance for monitoring
        print(f"Batch cosine similarity (1000x1536): {elapsed:.4f}s")
    
    @pytest.mark.asyncio
    async def test_search_optimization_performance(self):
        """Benchmark search optimization performance."""
        search_optimizer = PerformanceOptimizedSearch(embedding_dim=128)
        
        # Generate test data
        query_vector = [float(i % 10) for i in range(128)]
        candidate_vectors = [
            [float((i + j) % 10) for i in range(128)]
            for j in range(100)
        ]
        
        # Benchmark search performance
        start_time = time.perf_counter()
        results = await search_optimizer.search_similar_vectors(
            query_vector, candidate_vectors, top_k=10
        )
        elapsed = time.perf_counter() - start_time
        
        assert len(results) == 10
        assert elapsed < 0.5  # Should complete in under 0.5 seconds
        
        # Log performance for monitoring
        print(f"Optimized search (100 candidates): {elapsed:.4f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
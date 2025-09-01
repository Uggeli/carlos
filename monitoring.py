"""
Comprehensive monitoring and observability system for Carlos AI Assistant
Enterprise-grade metrics, logging, and performance monitoring
"""

import asyncio
import time
import psutil
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from contextlib import asynccontextmanager
import json
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics we can track."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class Metric:
    """A single metric measurement."""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class PerformanceSnapshot:
    """System performance snapshot."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    active_threads: int
    response_time_ms: float
    requests_per_second: float
    error_rate: float


class MetricsCollector:
    """
    High-performance metrics collection system.
    
    Thread-safe, low-overhead metrics collection with configurable
    retention policies and aggregation strategies.
    """
    
    def __init__(self, max_metrics: int = 10000, retention_hours: int = 24):
        self.max_metrics = max_metrics
        self.retention_hours = retention_hours
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_metrics))
        self._lock = threading.RLock()
        self._start_time = time.time()
        
        # Performance counters
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        
        # System monitoring
        self._system_snapshots: deque = deque(maxlen=1000)
        self._monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None
    
    def increment_counter(self, name: str, value: float = 1.0, tags: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter metric."""
        with self._lock:
            self._counters[name] += value
            self._add_metric(name, value, MetricType.COUNTER, tags or {})
    
    def set_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge metric value."""
        with self._lock:
            self._gauges[name] = value
            self._add_metric(name, value, MetricType.GAUGE, tags or {})
    
    def record_time(self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a timing measurement."""
        with self._lock:
            self._timers[name].append(duration_ms)
            # Keep only recent measurements
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]
            self._add_metric(name, duration_ms, MetricType.TIMER, tags or {})
    
    def _add_metric(self, name: str, value: float, metric_type: MetricType, tags: Dict[str, str]) -> None:
        """Add a metric to the collection."""
        metric = Metric(
            name=name,
            value=value,
            timestamp=datetime.now(timezone.utc),
            tags=tags,
            metric_type=metric_type
        )
        self._metrics[name].append(metric)
    
    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        with self._lock:
            return self._counters.get(name, 0.0)
    
    def get_gauge(self, name: str) -> float:
        """Get current gauge value."""
        with self._lock:
            return self._gauges.get(name, 0.0)
    
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """Get timer statistics (min, max, avg, p95, p99)."""
        with self._lock:
            times = self._timers.get(name, [])
            if not times:
                return {}
            
            sorted_times = sorted(times)
            n = len(sorted_times)
            
            return {
                'count': n,
                'min': min(sorted_times),
                'max': max(sorted_times),
                'avg': sum(sorted_times) / n,
                'p50': sorted_times[int(n * 0.5)],
                'p95': sorted_times[int(n * 0.95)],
                'p99': sorted_times[int(n * 0.99)]
            }
    
    def start_system_monitoring(self, interval: float = 1.0) -> None:
        """Start system performance monitoring."""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitor_thread = threading.Thread(
            target=self._system_monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("System monitoring started")
    
    def stop_system_monitoring(self) -> None:
        """Stop system performance monitoring."""
        self._monitoring_active = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        logger.info("System monitoring stopped")
    
    def _system_monitor_loop(self, interval: float) -> None:
        """System monitoring loop."""
        while self._monitoring_active:
            try:
                snapshot = PerformanceSnapshot(
                    timestamp=datetime.now(timezone.utc),
                    cpu_percent=psutil.cpu_percent(interval=0.1),
                    memory_percent=psutil.virtual_memory().percent,
                    memory_available_mb=psutil.virtual_memory().available / 1024 / 1024,
                    active_threads=threading.active_count(),
                    response_time_ms=self.get_timer_stats('carlos.response_time').get('avg', 0),
                    requests_per_second=self._calculate_rps(),
                    error_rate=self._calculate_error_rate()
                )
                
                with self._lock:
                    self._system_snapshots.append(snapshot)
                
                # Update gauge metrics
                self.set_gauge('system.cpu_percent', snapshot.cpu_percent)
                self.set_gauge('system.memory_percent', snapshot.memory_percent)
                self.set_gauge('system.memory_available_mb', snapshot.memory_available_mb)
                self.set_gauge('system.active_threads', snapshot.active_threads)
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"System monitoring error: {e}")
                time.sleep(interval)
    
    def _calculate_rps(self) -> float:
        """Calculate requests per second."""
        request_count = self.get_counter('carlos.requests')
        uptime_seconds = time.time() - self._start_time
        return request_count / max(uptime_seconds, 1.0)
    
    def _calculate_error_rate(self) -> float:
        """Calculate error rate percentage."""
        total_requests = self.get_counter('carlos.requests')
        error_requests = self.get_counter('carlos.errors')
        if total_requests == 0:
            return 0.0
        return (error_requests / total_requests) * 100.0
    
    def get_system_summary(self) -> Dict[str, Any]:
        """Get system performance summary."""
        with self._lock:
            if not self._system_snapshots:
                return {}
            
            latest = self._system_snapshots[-1]
            return {
                'latest_snapshot': {
                    'timestamp': latest.timestamp.isoformat(),
                    'cpu_percent': latest.cpu_percent,
                    'memory_percent': latest.memory_percent,
                    'memory_available_mb': latest.memory_available_mb,
                    'active_threads': latest.active_threads,
                    'response_time_ms': latest.response_time_ms,
                    'requests_per_second': latest.requests_per_second,
                    'error_rate': latest.error_rate
                },
                'uptime_seconds': time.time() - self._start_time,
                'total_requests': self.get_counter('carlos.requests'),
                'total_errors': self.get_counter('carlos.errors'),
                'avg_response_time': self.get_timer_stats('carlos.response_time').get('avg', 0)
            }
    
    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics in a structured format."""
        with self._lock:
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'counters': dict(self._counters),
                'gauges': dict(self._gauges),
                'timers': {name: self.get_timer_stats(name) for name in self._timers},
                'system_summary': self.get_system_summary()
            }


class PerformanceMonitor:
    """
    Context manager for monitoring operation performance.
    
    Automatically tracks timing and success/failure rates for operations.
    """
    
    def __init__(self, metrics_collector: MetricsCollector, operation_name: str):
        self.metrics = metrics_collector
        self.operation_name = operation_name
        self.start_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.metrics.increment_counter(f'{self.operation_name}.started')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            duration_ms = (time.perf_counter() - self.start_time) * 1000
            self.metrics.record_time(f'{self.operation_name}.duration', duration_ms)
            
            if exc_type is None:
                self.metrics.increment_counter(f'{self.operation_name}.success')
            else:
                self.metrics.increment_counter(f'{self.operation_name}.error')
                self.metrics.increment_counter('carlos.errors')
    
    @asynccontextmanager
    async def async_context(self):
        """Async context manager version."""
        self.start_time = time.perf_counter()
        self.metrics.increment_counter(f'{self.operation_name}.started')
        try:
            yield self
            duration_ms = (time.perf_counter() - self.start_time) * 1000
            self.metrics.record_time(f'{self.operation_name}.duration', duration_ms)
            self.metrics.increment_counter(f'{self.operation_name}.success')
        except Exception as e:
            duration_ms = (time.perf_counter() - self.start_time) * 1000
            self.metrics.record_time(f'{self.operation_name}.duration', duration_ms)
            self.metrics.increment_counter(f'{self.operation_name}.error')
            self.metrics.increment_counter('carlos.errors')
            raise


def monitor_operation(operation_name: str):
    """Decorator for monitoring function performance."""
    def decorator(func: Callable):
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                async with PerformanceMonitor(global_metrics, operation_name).async_context():
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                with PerformanceMonitor(global_metrics, operation_name):
                    return func(*args, **kwargs)
            return sync_wrapper
    return decorator


class HealthChecker:
    """
    Comprehensive health checking system.
    
    Monitors various aspects of system health and provides
    detailed health reports for operational visibility.
    """
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
        self.health_checks: Dict[str, Callable] = {}
        self.thresholds = {
            'cpu_percent': 80.0,
            'memory_percent': 85.0,
            'response_time_ms': 5000.0,
            'error_rate': 5.0
        }
    
    def register_health_check(self, name: str, check_func: Callable) -> None:
        """Register a custom health check function."""
        self.health_checks[name] = check_func
    
    def set_threshold(self, metric_name: str, threshold: float) -> None:
        """Set health threshold for a metric."""
        self.thresholds[metric_name] = threshold
    
    async def check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        health_status = {
            'overall_status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'checks': {},
            'metrics': self.metrics.get_system_summary()
        }
        
        # System health checks
        system_checks = {
            'cpu_usage': self._check_cpu_usage(),
            'memory_usage': self._check_memory_usage(),
            'response_time': self._check_response_time(),
            'error_rate': self._check_error_rate(),
            'disk_usage': self._check_disk_usage()
        }
        
        # Custom health checks
        custom_checks = {}
        for name, check_func in self.health_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    custom_checks[name] = await check_func()
                else:
                    custom_checks[name] = check_func()
            except Exception as e:
                custom_checks[name] = {
                    'status': 'error',
                    'message': f'Health check failed: {str(e)}'
                }
        
        health_status['checks'].update(system_checks)
        health_status['checks'].update(custom_checks)
        
        # Determine overall status
        unhealthy_checks = [
            name for name, check in health_status['checks'].items()
            if check.get('status') != 'healthy'
        ]
        
        if unhealthy_checks:
            health_status['overall_status'] = 'unhealthy'
            health_status['unhealthy_checks'] = unhealthy_checks
        
        return health_status
    
    def _check_cpu_usage(self) -> Dict[str, Any]:
        """Check CPU usage health."""
        cpu_percent = self.metrics.get_gauge('system.cpu_percent')
        status = 'healthy' if cpu_percent < self.thresholds['cpu_percent'] else 'unhealthy'
        return {
            'status': status,
            'value': cpu_percent,
            'threshold': self.thresholds['cpu_percent'],
            'message': f'CPU usage: {cpu_percent:.1f}%'
        }
    
    def _check_memory_usage(self) -> Dict[str, Any]:
        """Check memory usage health."""
        memory_percent = self.metrics.get_gauge('system.memory_percent')
        status = 'healthy' if memory_percent < self.thresholds['memory_percent'] else 'unhealthy'
        return {
            'status': status,
            'value': memory_percent,
            'threshold': self.thresholds['memory_percent'],
            'message': f'Memory usage: {memory_percent:.1f}%'
        }
    
    def _check_response_time(self) -> Dict[str, Any]:
        """Check response time health."""
        timer_stats = self.metrics.get_timer_stats('carlos.response_time')
        avg_response_time = timer_stats.get('avg', 0)
        status = 'healthy' if avg_response_time < self.thresholds['response_time_ms'] else 'unhealthy'
        return {
            'status': status,
            'value': avg_response_time,
            'threshold': self.thresholds['response_time_ms'],
            'message': f'Avg response time: {avg_response_time:.1f}ms'
        }
    
    def _check_error_rate(self) -> Dict[str, Any]:
        """Check error rate health."""
        total_requests = self.metrics.get_counter('carlos.requests')
        error_requests = self.metrics.get_counter('carlos.errors')
        error_rate = (error_requests / max(total_requests, 1)) * 100
        status = 'healthy' if error_rate < self.thresholds['error_rate'] else 'unhealthy'
        return {
            'status': status,
            'value': error_rate,
            'threshold': self.thresholds['error_rate'],
            'message': f'Error rate: {error_rate:.2f}%'
        }
    
    def _check_disk_usage(self) -> Dict[str, Any]:
        """Check disk usage health."""
        try:
            disk_usage = psutil.disk_usage('/')
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            status = 'healthy' if disk_percent < 90.0 else 'unhealthy'
            return {
                'status': status,
                'value': disk_percent,
                'threshold': 90.0,
                'message': f'Disk usage: {disk_percent:.1f}%'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Failed to check disk usage: {str(e)}'
            }


# Global metrics collector instance
global_metrics = MetricsCollector()
health_checker = HealthChecker(global_metrics)


def get_monitoring_dashboard() -> Dict[str, Any]:
    """Get comprehensive monitoring dashboard data."""
    return {
        'metrics': global_metrics.export_metrics(),
        'health': asyncio.run(health_checker.check_health()),
        'performance_summary': global_metrics.get_system_summary()
    }


def start_monitoring() -> None:
    """Start the monitoring system."""
    global_metrics.start_system_monitoring()
    logger.info("Carlos monitoring system started")


def stop_monitoring() -> None:
    """Stop the monitoring system."""
    global_metrics.stop_system_monitoring()
    logger.info("Carlos monitoring system stopped")

"""메트릭 미들웨어"""
########################################################
# TODO: Implement the actual metrics middleware logic
#       - Collect metrics for HTTP requests
#       - Collect metrics for HTTP request duration
#       - Collect metrics for HTTP request status
#       - Collect metrics for HTTP request endpoint
#       - Collect metrics for HTTP request method
#       - Collect metrics for HTTP request status code
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Metrics middleware logic
# version: 0.1.0
# status: development
# tags: metrics
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import time
from fastapi import Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# 메트릭 정의
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)


async def metrics_middleware(request: Request, call_next):
    """메트릭 수집 미들웨어"""
    # /metrics 엔드포인트는 메트릭 수집에서 제외 (자기 자신의 메트릭 수집 방지)
    if request.url.path == "/metrics":
        return await call_next(request)
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response


def metrics_endpoint():
    """메트릭 엔드포인트 핸들러"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


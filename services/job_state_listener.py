"""Job State Listener Service
PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너
"""
########################################################
# created_at: 2025-11-28
# author: LEEYH205
# description: PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너
# version: 1.0.0
# status: development
# tags: database, listener, notify
# dependencies: asyncpg, fastapi
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import asyncio
import json
import logging
from typing import Optional
import asyncpg
from config import DATABASE_URL, JOB_STATE_LISTENER_RECONNECT_DELAY

logger = logging.getLogger(__name__)

class JobStateListener:
    """PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너"""
    
    def __init__(self):
        self.conn: Optional[asyncpg.Connection] = None
        self.running = False
        self.reconnect_delay = JOB_STATE_LISTENER_RECONNECT_DELAY
        self.pending_tasks: set = set()  # 실행 중인 태스크 추적
    
    async def start(self):
        """리스너 시작"""
        self.running = True
        await self._listen_loop()
    
    async def stop(self):
        """리스너 중지 (실행 중인 태스크 완료 대기)"""
        self.running = False
        
        # 실행 중인 태스크 완료 대기
        if self.pending_tasks:
            logger.info(f"실행 중인 {len(self.pending_tasks)}개 태스크 완료 대기 중...")
            # 최대 30초 대기
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.pending_tasks, return_exceptions=True),
                    timeout=30.0
                )
                logger.info("모든 태스크 완료됨")
            except asyncio.TimeoutError:
                logger.warning("일부 태스크가 30초 내에 완료되지 않아 강제 종료합니다")
                # 타임아웃된 태스크 취소
                for task in self.pending_tasks:
                    if not task.done():
                        task.cancel()
        
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Job State Listener 중지됨")
    
    async def _listen_loop(self):
        """리스너 메인 루프 (재연결 포함)"""
        while self.running:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("리스너가 취소되었습니다")
                break
            except Exception as e:
                logger.error(f"리스너 오류 발생: {e}", exc_info=True)
                if self.running:
                    logger.info(f"{self.reconnect_delay}초 후 재연결 시도...")
                    await asyncio.sleep(self.reconnect_delay)
    
    async def _connect_and_listen(self):
        """PostgreSQL 연결 및 LISTEN 시작"""
        # DATABASE_URL에서 asyncpg 형식으로 변환
        # postgresql://user:pass@host:port/db -> postgres://user:pass@host:port/db
        asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
        
        try:
            self.conn = await asyncpg.connect(asyncpg_url)
            logger.info("PostgreSQL 연결 성공 (Job State Listener)")
            
            # LISTEN 시작
            await self.conn.add_listener('job_state_changed', self._handle_notification)
            logger.info("LISTEN 'job_state_changed' 시작")
            
            # 연결이 끊길 때까지 대기
            while self.running:
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"PostgreSQL 연결 오류: {e}", exc_info=True)
            raise
        finally:
            if self.conn:
                try:
                    await self.conn.remove_listener('job_state_changed', self._handle_notification)
                    await self.conn.close()
                    logger.info("PostgreSQL 연결 종료 (Job State Listener)")
                except Exception as e:
                    logger.error(f"연결 종료 중 오류: {e}")
                finally:
                    self.conn = None
    
    def _handle_notification(self, conn, pid, channel, payload):
        """NOTIFY 이벤트 핸들러"""
        try:
            # JSON 파싱
            data = json.loads(payload)
            job_id = data.get('job_id')
            current_step = data.get('current_step')
            status = data.get('status')
            tenant_id = data.get('tenant_id')
            
            print(f"[LISTENER] Job 상태 변화 감지: job_id={job_id}, current_step={current_step}, status={status}")
            logger.info(
                f"Job 상태 변화 감지: job_id={job_id}, "
                f"current_step={current_step}, status={status}, tenant_id={tenant_id}"
            )
            
            # 비동기로 처리 (이벤트 핸들러는 동기 함수이므로)
            # 태스크를 추적하여 종료 시 완료 대기
            task = asyncio.create_task(
                self._process_job_state_change(job_id, current_step, status, tenant_id)
            )
            self.pending_tasks.add(task)
            # 태스크 완료 시 자동으로 제거
            task.add_done_callback(self.pending_tasks.discard)
            
        except Exception as e:
            logger.error(f"이벤트 처리 오류: {e}", exc_info=True)
    
    async def _process_job_state_change(
        self, 
        job_id: str, 
        current_step: Optional[str], 
        status: str,
        tenant_id: str
    ):
        """Job 상태 변화 처리 및 다음 단계 트리거"""
        try:
            from services.pipeline_trigger import trigger_next_pipeline_stage
            
            await trigger_next_pipeline_stage(
                job_id=job_id,
                current_step=current_step,
                status=status,
                tenant_id=tenant_id
            )
        except Exception as e:
            logger.error(
                f"파이프라인 트리거 오류: job_id={job_id}, error={e}",
                exc_info=True
            )


# 전역 리스너 인스턴스
_listener: Optional[JobStateListener] = None

async def start_listener():
    """리스너 시작 (FastAPI startup에서 호출)"""
    global _listener
    if _listener is None:
        _listener = JobStateListener()
        # 백그라운드 태스크로 시작
        asyncio.create_task(_listener.start())
        logger.info("Job State Listener 시작됨")

async def stop_listener():
    """리스너 중지 (FastAPI shutdown에서 호출)"""
    global _listener
    if _listener:
        await _listener.stop()
        _listener = None


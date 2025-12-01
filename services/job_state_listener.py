"""Job State Listener Service
PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너
"""
########################################################
# created_at: 2025-11-28
# updated_at: 2025-12-01
# author: LEEYH205
# description: PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너
# version: 2.3.0
# changes: iou_eval 단계 수동 복구 로직 추가 (주기적 체크)
# status: development
# tags: database, listener, notify
# dependencies: asyncpg, fastapi
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import asyncio
import json
import logging
import uuid
from typing import Optional
import asyncpg
from config import DATABASE_URL, JOB_STATE_LISTENER_RECONNECT_DELAY

logger = logging.getLogger(__name__)

# 최대 재시도 횟수 (Job 단위)
MAX_JOB_RETRY_COUNT = 3

class JobStateListener:
    """PostgreSQL LISTEN/NOTIFY를 사용한 Job 상태 변화 리스너"""
    
    def __init__(self):
        self.conn: Optional[asyncpg.Connection] = None
        self.running = False
        self.reconnect_delay = JOB_STATE_LISTENER_RECONNECT_DELAY
        self.pending_tasks: set = set()  # 실행 중인 태스크 추적
        self.recovery_check_interval = 60  # 수동 복구 체크 간격 (초, 기본 1분)
        self.recovery_task: Optional[asyncio.Task] = None  # 수동 복구 백그라운드 태스크
    
    async def start(self):
        """리스너 시작"""
        self.running = True
        # 수동 복구 백그라운드 태스크 시작
        self.recovery_task = asyncio.create_task(self._periodic_recovery_check())
        await self._listen_loop()
    
    async def stop(self):
        """리스너 중지 (실행 중인 태스크 완료 대기)"""
        self.running = False
        
        # 수동 복구 태스크 중지
        if self.recovery_task and not self.recovery_task.done():
            self.recovery_task.cancel()
            try:
                await self.recovery_task
            except asyncio.CancelledError:
                logger.info("수동 복구 태스크 중지됨")
        
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
            
            # LISTEN 시작 (jobs 테이블과 jobs_variants 테이블 모두)
            await self.conn.add_listener('job_state_changed', self._handle_notification)
            await self.conn.add_listener('job_variant_state_changed', self._handle_variant_notification)
            logger.info("LISTEN 'job_state_changed' 시작")
            logger.info("LISTEN 'job_variant_state_changed' 시작")
            
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
                    await self.conn.remove_listener('job_variant_state_changed', self._handle_variant_notification)
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
    
    def _handle_variant_notification(self, conn, pid, channel, payload):
        """NOTIFY 이벤트 핸들러 (job_variant_state_changed)"""
        try:
            # JSON 파싱
            data = json.loads(payload)
            job_variants_id = data.get('job_variants_id')
            job_id = data.get('job_id')
            current_step = data.get('current_step')
            status = data.get('status')
            tenant_id = data.get('tenant_id')
            img_asset_id = data.get('img_asset_id')
            
            print(f"[LISTENER] Job Variant 상태 변화 감지: job_variants_id={job_variants_id}, job_id={job_id}, current_step={current_step}, status={status}")
            logger.info(
                f"Job Variant 상태 변화 감지: job_variants_id={job_variants_id}, job_id={job_id}, "
                f"current_step={current_step}, status={status}, tenant_id={tenant_id}, img_asset_id={img_asset_id}"
            )
            
            # 비동기로 처리 (이벤트 핸들러는 동기 함수이므로)
            # 태스크를 추적하여 종료 시 완료 대기
            task = asyncio.create_task(
                self._process_job_variant_state_change(
                    job_variants_id=job_variants_id,
                    job_id=job_id,
                    current_step=current_step,
                    status=status,
                    tenant_id=tenant_id,
                    img_asset_id=img_asset_id
                )
            )
            self.pending_tasks.add(task)
            # 태스크 완료 시 자동으로 제거
            task.add_done_callback(self.pending_tasks.discard)
            
        except Exception as e:
            logger.error(f"이벤트 처리 오류 (variant): {e}", exc_info=True)
    
    async def _process_job_state_change(
        self, 
        job_id: str, 
        current_step: Optional[str], 
        status: str,
        tenant_id: str
    ):
        """Job 상태 변화 처리 및 뒤처진 variants 재시작"""
        try:
            # yh 파트 단계 정의
            YH_STEPS = ['vlm_analyze', 'yolo_detect', 'planner', 'overlay', 
                        'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval']
            
            # 단계 순서 정의
            STEP_ORDER = {
                'img_gen': 0,
                'vlm_analyze': 1,
                'yolo_detect': 2,
                'planner': 3,
                'overlay': 4,
                'vlm_judge': 5,
                'ocr_eval': 6,
                'readability_eval': 7,
                'iou_eval': 8
            }
            
            # 1) Job이 failed인 경우: 재시도 가능하면 현재 단계 재실행
            if status == 'failed' and current_step and current_step in YH_STEPS:
                from services.pipeline_trigger import retry_pipeline_stage
                
                # Job/Variants 상태 확인 및 최대 재시도 횟수 체크
                asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
                conn: Optional[asyncpg.Connection] = None
                try:
                    conn = await asyncpg.connect(asyncpg_url)
                    
                    row = await conn.fetchrow(
                        """
                        SELECT 
                            j.retry_count,
                            COUNT(jv.job_variants_id) AS total_variants,
                            COUNT(*) FILTER (
                                WHERE jv.status = 'failed' 
                                  AND jv.current_step = $2
                            ) AS failed_at_step,
                            COUNT(*) FILTER (
                                WHERE jv.status IN ('running', 'queued')
                            ) AS running_or_queued
                        FROM jobs j
                        LEFT JOIN jobs_variants jv 
                            ON j.job_id = jv.job_id
                        WHERE j.job_id = $1
                        GROUP BY j.retry_count
                        """,
                        uuid.UUID(job_id),
                        current_step,
                    )
                    
                    if row:
                        retry_count = row["retry_count"] or 0
                        total_variants = row["total_variants"] or 0
                        failed_at_step = row["failed_at_step"] or 0
                        running_or_queued = row["running_or_queued"] or 0
                    else:
                        retry_count = 0
                        total_variants = 0
                        failed_at_step = 0
                        running_or_queued = 0
                    
                    # 재시도 조건:
                    # - 최대 재시도 횟수 미만
                    # - 모든 variants가 동일 단계에서 failed
                    # - 진행 중인 variants 없음
                    can_retry = (
                        total_variants > 0
                        and failed_at_step == total_variants
                        and running_or_queued == 0
                        and retry_count < MAX_JOB_RETRY_COUNT
                    )
                    
                    if can_retry:
                        new_retry_count = retry_count + 1
                        
                        # Job을 running으로 되돌리고 retry_count 증가
                        await conn.execute(
                            """
                            UPDATE jobs
                            SET status = 'running',
                                retry_count = retry_count + 1,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE job_id = $1
                              AND status = 'failed'
                              AND current_step = $2
                            """,
                            uuid.UUID(job_id),
                            current_step,
                        )
                        
                        # 해당 단계에서 failed인 variants의 retry_count 증가
                        await conn.execute(
                            """
                            UPDATE jobs_variants
                            SET retry_count = retry_count + 1,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE job_id = $1
                              AND current_step = $2
                              AND status = 'failed'
                            """,
                            uuid.UUID(job_id),
                            current_step,
                        )
                        
                        logger.warning(
                            f"⚠️ Job 실패 재시도: job_id={job_id}, "
                            f"current_step={current_step}, "
                            f"retry_count={new_retry_count}/{MAX_JOB_RETRY_COUNT}, "
                            f"variants={total_variants}"
                        )
                        
                        # 현재 단계 다시 실행 (동일 API 재호출)
                        await retry_pipeline_stage(
                            job_id=job_id,
                            current_step=current_step,
                            tenant_id=tenant_id,
                        )
                        
                        # 재시도 스케줄 후에는 뒤처진 variant 복구 및 다음 단계 트리거는 건너뜀
                        return
                    else:
                        if retry_count >= MAX_JOB_RETRY_COUNT:
                            logger.warning(
                                f"최대 재시도 횟수 초과로 Job 재시도 스킵: "
                                f"job_id={job_id}, current_step={current_step}, "
                                f"retry_count={retry_count}"
                            )
                except Exception as retry_error:
                    logger.error(
                        f"Job 실패 재시도 로직 실행 중 오류: job_id={job_id}, "
                        f"current_step={current_step}, error={retry_error}",
                        exc_info=True,
                    )
                finally:
                    if conn:
                        await conn.close()
            
            # 2) Job이 running 또는 failed 상태이고 yh 파트 단계인 경우 뒤처진 variants 확인
            # (failed 상태도 확인하여 실패한 variants를 재시도)
            if status in ['running', 'failed'] and current_step and current_step in YH_STEPS:
                await self._recover_stuck_variants(job_id, current_step, tenant_id, STEP_ORDER)
            
            # 기존 로직 유지 (하위 호환성)
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
    
    async def _recover_stuck_variants(
        self,
        job_id: str,
        job_current_step: str,
        tenant_id: str,
        step_order: dict
    ):
        """뒤처진 variants 감지 및 재시작"""
        try:
            import asyncpg
            from config import DATABASE_URL
            from services.pipeline_trigger import trigger_next_pipeline_stage_for_variant
            
            job_step_order = step_order.get(job_current_step, -1)
            if job_step_order < 0:
                logger.debug(f"알 수 없는 단계: job_id={job_id}, current_step={job_current_step}")
                return
            
            asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
            conn = await asyncpg.connect(asyncpg_url)
            try:
                # 해당 job의 모든 variants 조회
                variants = await conn.fetch("""
                    SELECT job_variants_id, current_step, status, img_asset_id, creation_order
                    FROM jobs_variants
                    WHERE job_id = $1
                    ORDER BY creation_order
                """, uuid.UUID(job_id))
                
                if not variants:
                    logger.debug(f"Variants를 찾을 수 없음: job_id={job_id}")
                    return
                
                # 뒤처진 variants 찾기
                stuck_count = 0
                recovered_count = 0
                failed_count = 0
                
                for variant in variants:
                    variant_id = variant['job_variants_id']
                    variant_step = variant['current_step']
                    variant_status = variant['status']
                    variant_step_order = step_order.get(variant_step, -1)
                    
                    # Variant가 Job보다 뒤처져 있는 경우
                    if variant_step_order >= 0 and variant_step_order < job_step_order:
                        stuck_count += 1
                        logger.warning(
                            f"뒤처진 variant 감지: job_id={job_id}, "
                            f"job_step={job_current_step} (order: {job_step_order}), "
                            f"variant_id={variant_id}, "
                            f"variant_step={variant_step} (order: {variant_step_order}), "
                            f"variant_status={variant_status}, "
                            f"creation_order={variant['creation_order']}"
                        )
                        
                        # 재시작 전에 variant 상태를 다시 확인 (다른 프로세스가 이미 처리했을 수 있음)
                        current_variant = await conn.fetchrow("""
                            SELECT status, current_step
                            FROM jobs_variants
                            WHERE job_variants_id = $1
                        """, variant_id)
                        
                        if not current_variant:
                            logger.warning(f"Variant를 찾을 수 없음: job_variants_id={variant_id}")
                            continue
                        
                        # 상태가 변경되었으면 스킵 (이미 처리됨)
                        if (current_variant['status'] != variant_status or 
                            current_variant['current_step'] != variant_step):
                            logger.info(
                                f"Variant 상태가 변경되어 스킵: job_variants_id={variant_id}, "
                                f"old: {variant_step} ({variant_status}), "
                                f"new: {current_variant['current_step']} ({current_variant['status']})"
                            )
                            continue
                        
                        # Variant가 done 상태이면 다음 단계 트리거
                        if variant_status == 'done':
                            try:
                                # 트리거 호출 직전에 variant 상태를 다시 확인 (다른 프로세스가 이미 처리했을 수 있음)
                                final_variant = await conn.fetchrow("""
                                    SELECT status, current_step
                                    FROM jobs_variants
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                if not final_variant:
                                    logger.warning(f"Variant를 찾을 수 없음: job_variants_id={variant_id}")
                                    continue
                                
                                # 상태가 변경되었으면 스킵
                                if (final_variant['status'] != variant_status or 
                                    final_variant['current_step'] != variant_step):
                                    logger.info(
                                        f"Variant 상태가 변경되어 스킵: job_variants_id={variant_id}, "
                                        f"old: {variant_step} ({variant_status}), "
                                        f"new: {final_variant['current_step']} ({final_variant['status']})"
                                    )
                                    continue
                                
                                # retry_count 증가
                                await conn.execute("""
                                    UPDATE jobs_variants
                                    SET retry_count = retry_count + 1,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                # 현재 retry_count 조회
                                current_retry = await conn.fetchval("""
                                    SELECT retry_count
                                    FROM jobs_variants
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                logger.info(
                                    f"뒤처진 variant 재시작 시도: job_variants_id={variant_id}, "
                                    f"current_step={variant_step} → 다음 단계, retry_count={current_retry}"
                                )
                                
                                await trigger_next_pipeline_stage_for_variant(
                                    job_variants_id=str(variant_id),
                                    job_id=job_id,
                                    current_step=variant_step,
                                    status='done',
                                    tenant_id=tenant_id,
                                    img_asset_id=str(variant['img_asset_id']) if variant['img_asset_id'] else ''
                                )
                                
                                # 재시작 후 상태 확인 (약간의 지연 후)
                                import asyncio
                                await asyncio.sleep(1)
                                
                                updated_variant = await conn.fetchrow("""
                                    SELECT status, current_step
                                    FROM jobs_variants
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                if updated_variant and updated_variant['current_step'] != variant_step:
                                    recovered_count += 1
                                    logger.info(
                                        f"✅ 뒤처진 variant 재시작 성공: job_variants_id={variant_id}, "
                                        f"{variant_step} → {updated_variant['current_step']}"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️  뒤처진 variant 재시작 후 상태 미변경: job_variants_id={variant_id}, "
                                        f"current_step={variant_step}"
                                    )
                                    
                            except Exception as trigger_error:
                                failed_count += 1
                                logger.error(
                                    f"❌ 뒤처진 variant 재시작 실패: job_variants_id={variant_id}, "
                                    f"current_step={variant_step}, error={trigger_error}",
                                    exc_info=True
                                )
                        
                        # Variant가 failed 상태이면 재시도 (다음 단계로 진행 시도)
                        elif variant_status == 'failed':
                            try:
                                # retry_count 증가 및 failed 상태를 done으로 변경
                                # (실패한 단계를 건너뛰고 다음 단계로 진행)
                                await conn.execute("""
                                    UPDATE jobs_variants
                                    SET status = 'done',
                                        retry_count = retry_count + 1,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                # 현재 retry_count 조회
                                current_retry = await conn.fetchval("""
                                    SELECT retry_count
                                    FROM jobs_variants
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                logger.info(
                                    f"실패한 variant 재시도: job_variants_id={variant_id}, "
                                    f"current_step={variant_step}, retry_count={current_retry}"
                                )
                                
                                # 다음 단계 트리거
                                await trigger_next_pipeline_stage_for_variant(
                                    job_variants_id=str(variant_id),
                                    job_id=job_id,
                                    current_step=variant_step,
                                    status='done',  # done 상태로 변경하여 다음 단계 진행
                                    tenant_id=tenant_id,
                                    img_asset_id=str(variant['img_asset_id']) if variant['img_asset_id'] else ''
                                )
                                
                                # 재시도 후 상태 확인
                                import asyncio
                                await asyncio.sleep(1)
                                
                                updated_variant = await conn.fetchrow("""
                                    SELECT status, current_step
                                    FROM jobs_variants
                                    WHERE job_variants_id = $1
                                """, variant_id)
                                
                                if updated_variant and updated_variant['status'] != 'failed':
                                    recovered_count += 1
                                    logger.info(
                                        f"✅ 실패한 variant 재시도 성공: job_variants_id={variant_id}, "
                                        f"{variant_step} ({variant_status}) → {updated_variant['current_step']} ({updated_variant['status']})"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️  실패한 variant 재시도 후 여전히 failed: job_variants_id={variant_id}"
                                    )
                                    
                            except Exception as retry_error:
                                failed_count += 1
                                logger.error(
                                    f"❌ 실패한 variant 재시도 실패: job_variants_id={variant_id}, "
                                    f"error={retry_error}",
                                    exc_info=True
                                )
                        
                        # Variant가 running 상태이고 오래 실행 중인 경우 (5분 이상)
                        elif variant_status == 'running':
                            from datetime import datetime, timezone
                            updated_at = variant.get('updated_at')
                            if updated_at:
                                if isinstance(updated_at, datetime):
                                    time_diff = (datetime.now(timezone.utc) - updated_at.replace(tzinfo=timezone.utc)).total_seconds()
                                    if time_diff > 300:  # 5분 이상
                                        logger.warning(
                                            f"오래 실행 중인 variant 감지: job_variants_id={variant_id}, "
                                            f"running 시간: {int(time_diff)}초, current_step={variant_step}"
                                        )
                                        
                                        # 상태를 다시 확인하여 필요시 재시도
                                        # (현재는 로깅만, 추후 재시도 로직 추가 가능)
                
                if stuck_count > 0:
                    logger.info(
                        f"뒤처진 variants 복구 완료: job_id={job_id}, "
                        f"job_step={job_current_step}, "
                        f"stuck_count={stuck_count}, "
                        f"recovered_count={recovered_count}, "
                        f"failed_count={failed_count}"
                    )
            finally:
                await conn.close()
        except Exception as e:
            logger.error(
                f"뒤처진 variants 복구 오류: job_id={job_id}, error={e}",
                exc_info=True
            )
    
    async def _process_job_variant_state_change(
        self,
        job_variants_id: str,
        job_id: str,
        current_step: Optional[str],
        status: str,
        tenant_id: str,
        img_asset_id: str
    ):
        """Job Variant 상태 변화 처리 및 다음 단계 트리거"""
        try:
            from services.pipeline_trigger import trigger_next_pipeline_stage_for_variant
            
            # 트리거 실행
            await trigger_next_pipeline_stage_for_variant(
                job_variants_id=job_variants_id,
                job_id=job_id,
                current_step=current_step,
                status=status,
                tenant_id=tenant_id,
                img_asset_id=img_asset_id
            )
            
            # 멈춘 variant 감지 및 재시도: done 상태인데 오래 업데이트되지 않은 variant 확인
            if status == 'done' and current_step:
                import asyncio
                import asyncpg
                from config import DATABASE_URL
                
                # 5분 이상 업데이트되지 않은 done 상태 variant 확인
                asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
                try:
                    conn = await asyncpg.connect(asyncpg_url)
                    try:
                        # 같은 job_id의 다른 variant들이 더 진행된 경우, 멈춘 variant 재시도
                        stuck_variants = await conn.fetch("""
                            SELECT jv1.job_variants_id, jv1.current_step, jv1.updated_at
                            FROM jobs_variants jv1
                            WHERE jv1.job_id = $1
                              AND jv1.status = 'done'
                              AND jv1.current_step != 'iou_eval'
                              AND jv1.updated_at < NOW() - INTERVAL '5 minutes'
                              AND EXISTS (
                                  SELECT 1
                                  FROM jobs_variants jv2
                                  WHERE jv2.job_id = jv1.job_id
                                    AND jv2.current_step > jv1.current_step
                                    AND jv2.status = 'done'
                              )
                        """, uuid.UUID(job_id))
                        
                        for stuck in stuck_variants:
                            stuck_id = str(stuck['job_variants_id'])
                            stuck_step = stuck['current_step']
                            logger.warning(
                                f"멈춘 variant 감지: job_variants_id={stuck_id}, current_step={stuck_step}, "
                                f"updated_at={stuck['updated_at']}"
                            )
                            
                            # retry_count 증가 및 상태를 다시 업데이트하여 트리거 발동
                            await conn.execute("""
                                UPDATE jobs_variants
                                SET retry_count = retry_count + 1,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE job_variants_id = $1
                            """, uuid.UUID(stuck_id))
                            
                            # 현재 retry_count 조회
                            current_retry = await conn.fetchval("""
                                SELECT retry_count
                                FROM jobs_variants
                                WHERE job_variants_id = $1
                            """, uuid.UUID(stuck_id))
                            
                            logger.info(
                                f"멈춘 variant 재시도: job_variants_id={stuck_id}, "
                                f"current_step={stuck_step}, retry_count={current_retry}"
                            )
                    finally:
                        await conn.close()
                except Exception as retry_error:
                    logger.debug(f"멈춘 variant 재시도 확인 중 오류 (무시): {retry_error}")
                    
        except Exception as e:
            logger.error(
                f"파이프라인 트리거 오류 (variant): job_variants_id={job_variants_id}, job_id={job_id}, error={e}",
                exc_info=True
            )
    
    async def _periodic_recovery_check(self):
        """주기적으로 iou_eval 단계에서 모든 variants가 done인데 job이 done이 아닌 경우 수정"""
        logger.info(f"수동 복구 체크 시작 (간격: {self.recovery_check_interval}초)")
        
        while self.running:
            try:
                await asyncio.sleep(self.recovery_check_interval)
                
                if not self.running:
                    break
                
                await self._check_and_fix_iou_eval_jobs()
                
            except asyncio.CancelledError:
                logger.info("수동 복구 체크 취소됨")
                break
            except Exception as e:
                logger.error(f"수동 복구 체크 오류: {e}", exc_info=True)
                # 오류 발생 시에도 계속 실행
                await asyncio.sleep(10)  # 오류 발생 시 10초 대기 후 재시도
    
    async def _check_and_fix_iou_eval_jobs(self):
        """iou_eval 단계에서 모든 variants가 done인데 job이 done이 아닌 경우 수정"""
        try:
            import asyncpg
            from config import DATABASE_URL
            
            asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
            conn = await asyncpg.connect(asyncpg_url)
            
            try:
                # 조건을 만족하는 job 찾기
                # - current_step = 'iou_eval'
                # - status = 'running'
                # - 모든 variants가 iou_eval, done
                # - failed, running, queued variant 없음
                jobs_to_fix = await conn.fetch("""
                    SELECT 
                        j.job_id,
                        j.status,
                        j.current_step,
                        COUNT(jv.job_variants_id) as total_variants,
                        COUNT(*) FILTER (WHERE jv.status = 'done' AND jv.current_step = 'iou_eval') as iou_done_count,
                        COUNT(*) FILTER (WHERE jv.status = 'failed') as failed_count,
                        COUNT(*) FILTER (WHERE jv.status = 'running') as running_count,
                        COUNT(*) FILTER (WHERE jv.status = 'queued') as queued_count
                    FROM jobs j
                    INNER JOIN jobs_variants jv ON j.job_id = jv.job_id
                    WHERE j.current_step = 'iou_eval'
                      AND j.status = 'running'
                    GROUP BY j.job_id, j.status, j.current_step
                    HAVING COUNT(*) FILTER (WHERE jv.status = 'done' AND jv.current_step = 'iou_eval') = COUNT(jv.job_variants_id)
                       AND COUNT(*) FILTER (WHERE jv.status = 'failed') = 0
                       AND COUNT(*) FILTER (WHERE jv.status = 'running') = 0
                       AND COUNT(*) FILTER (WHERE jv.status = 'queued') = 0
                """)
                
                if jobs_to_fix:
                    logger.warning(
                        f"수동 복구 대상 발견: {len(jobs_to_fix)}개 job이 iou_eval, done 조건을 만족하지만 running 상태"
                    )
                    
                    fixed_count = 0
                    for job in jobs_to_fix:
                        job_id = job['job_id']
                        total = job['total_variants']
                        iou_done = job['iou_done_count']
                        
                        try:
                            # Job을 done으로 업데이트 (수동 복구이므로 retry_count 증가)
                            result = await conn.execute("""
                                UPDATE jobs
                                SET status = 'done',
                                    current_step = 'iou_eval',
                                    retry_count = retry_count + 1,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE job_id = $1
                                  AND status = 'running'
                                  AND current_step = 'iou_eval'
                            """, job_id)
                            
                            # 현재 retry_count 조회
                            current_retry = await conn.fetchval("""
                                SELECT retry_count
                                FROM jobs
                                WHERE job_id = $1
                            """, job_id)
                            
                            if result == "UPDATE 1":
                                fixed_count += 1
                                logger.info(
                                    f"✅ 수동 복구 완료: job_id={job_id}, "
                                    f"variants: {iou_done}/{total} 모두 iou_eval, done, retry_count={current_retry}"
                                )
                            else:
                                logger.debug(
                                    f"수동 복구 스킵: job_id={job_id} (이미 처리됨 또는 상태 변경됨)"
                                )
                                
                        except Exception as fix_error:
                            logger.error(
                                f"수동 복구 실패: job_id={job_id}, error={fix_error}",
                                exc_info=True
                            )
                    
                    if fixed_count > 0:
                        logger.info(f"수동 복구 완료: {fixed_count}개 job을 done으로 업데이트")
                else:
                    logger.debug("수동 복구 대상 없음 (모든 job이 정상 상태)")
                    
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"수동 복구 체크 오류: {e}", exc_info=True)


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


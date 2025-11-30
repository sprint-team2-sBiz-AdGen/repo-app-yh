"""뒤처진 Variants 복구 기능 테스트"""
import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncpg
from config import DATABASE_URL

async def test_recover_stuck_variants():
    """뒤처진 variants 복구 테스트"""
    job_id = '392a1989-48c0-46f5-8469-0c0108bd8a23'
    
    asyncpg_url = DATABASE_URL.replace("postgresql://", "postgres://")
    conn = await asyncpg.connect(asyncpg_url)
    try:
        # Job 정보 조회
        job = await conn.fetchrow("""
            SELECT job_id, status, current_step, tenant_id
            FROM jobs
            WHERE job_id = $1
        """, job_id)
        
        if not job:
            print(f"❌ Job을 찾을 수 없습니다: {job_id}")
            return
        
        print(f"📋 Job 정보:")
        print(f"   job_id: {job['job_id']}")
        print(f"   status: {job['status']}")
        print(f"   current_step: {job['current_step']}")
        print(f"   tenant_id: {job['tenant_id']}")
        
        # Variants 조회
        variants = await conn.fetch("""
            SELECT job_variants_id, creation_order, status, current_step, img_asset_id
            FROM jobs_variants
            WHERE job_id = $1
            ORDER BY creation_order
        """, job_id)
        
        print(f"\n📦 Variants ({len(variants)}개):")
        for v in variants:
            print(f"   Variant {v['creation_order']}: {v['current_step']} ({v['status']})")
        
        # NOTIFY 직접 발행하여 리스너 트리거
        print(f"\n🔔 NOTIFY 발행 중...")
        await conn.execute("""
            SELECT pg_notify(
                'job_state_changed',
                json_build_object(
                    'job_id', $1::text,
                    'current_step', $2,
                    'status', $3,
                    'tenant_id', $4,
                    'updated_at', NOW()
                )::text
            )
        """, job_id, job['current_step'], job['status'], job['tenant_id'])
        
        print("✅ NOTIFY 발행 완료")
        print("   리스너가 뒤처진 variants를 감지하고 재시작할 것입니다.")
        print("   로그를 확인하세요: docker logs feedlyai-work-yh | grep -E '뒤처진|recover'")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_recover_stuck_variants())


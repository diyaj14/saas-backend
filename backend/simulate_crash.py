# backend/simulate_crash.py
"""
Two realistic YouTube channel simulation scenarios:
  Scenario A: Algorithm Change (sudden, brutal drop overnight)
  Scenario B: Bad Content Spiral (slow, painful erosion over weeks)

Run with: python simulate_crash.py
"""
import asyncio
import random
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select

from app.database import SessionLocal
from app.models.schema import Creator, User, DailyMetric, Alert, MetricBaseline
from app.services.baseline_service import compute_baselines_for_creator
from app.services.anomaly_service import detect_anomalies_for_creator, detect_changepoint


# ─── Realistic Day-of-Week Multipliers ───────────────────────────────────────
# YouTube traffic is NOT uniform. Weekends are higher, Mondays are always low.
DOW_MULTIPLIERS = {
    0: 0.80,  # Monday   — everyone is back at work/school
    1: 0.88,  # Tuesday
    2: 0.92,  # Wednesday
    3: 0.95,  # Thursday
    4: 1.10,  # Friday   — people wind down early
    5: 1.20,  # Saturday — peak
    6: 1.15,  # Sunday
}

def realistic_views(base: float, date: datetime, noise: float = 0.12) -> int:
    """Generate a realistic view count with day-of-week patterns and random noise."""
    dow = date.weekday()
    multiplier = DOW_MULTIPLIERS[dow]
    # Add gaussian noise (±noise%) to simulate natural variation
    noisy = base * multiplier * (1 + random.gauss(0, noise))
    return max(0, int(noisy))


async def run_scenario(label: str, views_per_day: list, db):
    """Helper: creates a ghost creator, injects data, runs the brain."""
    sim_id = uuid.uuid4()
    user_id = uuid.uuid4()

    db.add(User(id=user_id, email=f"sim_{label.lower().replace(' ', '_')}@crashguard.test"))
    db.add(Creator(id=sim_id, user_id=user_id, niche=f"[TEST] {label}"))
    await db.commit()

    print(f"\n{'='*60}")
    print(f"  SCENARIO: {label}")
    print(f"  Creator ID: {sim_id}")
    print(f"{'='*60}")

    # Inject daily metrics
    batch = []
    start = datetime.now() - timedelta(days=len(views_per_day))
    for i, base_views in enumerate(views_per_day):
        date = start + timedelta(days=i)
        v = realistic_views(base_views, date)
        batch.append(DailyMetric(creator_id=sim_id, date=date, views=v))

    db.add_all(batch)
    await db.commit()
    print(f"  [DATA] Injected {len(batch)} days of data.")

    # Run the brain
    print("  [BRAIN] Computing baselines...")
    await compute_baselines_for_creator(sim_id, db)

    print("  [BRAIN] Checking for anomalies (Z-Score)...")
    await detect_anomalies_for_creator(sim_id, db)

    print("  [BRAIN] Checking for slow decline (Changepoint)...")
    await detect_changepoint(sim_id, db)

    # Report
    stmt = select(Alert).where(Alert.creator_id == sim_id)
    res = await db.execute(stmt)
    alerts = res.scalars().all()

    baseline_stmt = select(MetricBaseline).where(MetricBaseline.creator_id == sim_id)
    baseline_res = await db.execute(baseline_stmt)
    baseline = baseline_res.scalar_one_or_none()

    print("\n  BASELINE COMPUTED:")
    if baseline:
        print(f"    EMA-30 (expected daily views): {baseline.ema_30:,.0f}")
        print(f"    StdDev-30 (typical bounce):   ±{baseline.stddev_30:,.0f}")
    
    print(f"\n  ALERTS RAISED: {len(alerts)}")
    if alerts:
        for a in alerts:
            print(f"    [{a.severity}] {a.alert_type}")
            if a.payload:
                if "drop_percent" in a.payload:
                    print(f"      Slow decline: {a.payload['drop_percent']}% below previous month")
                if "crash_days" in a.payload:
                    for day in a.payload["crash_days"]:
                        print(f"      {day['date'][:10]}: {day['views']:,} views (Z={day['z_score']})")
    else:
        print("    No alerts — system thinks this is normal behaviour.")
    
    return sim_id


async def main():
    async with SessionLocal() as db:

        # ── SCENARIO A: ALGORITHM CHANGE ─────────────────────────────────────
        # Reality: A mid-size gaming channel getting ~8,000 views/day.
        # They were riding a wave from a viral video 3 months ago.
        # YouTube updates its recommendation algorithm → their videos stop
        # being recommended. The drop happens OVERNIGHT.
        #
        # Day  0-59: Healthy. Strong channel. Views oscillate between 7k–9k.
        # Day 60-75: Viral boost — a video blows up! Views spike to 18k.
        # Day 76-86: Viral fades naturally back to ~8k baseline.
        # Day 87-89: ALGORITHM CHANGE → Only 2,200–2,800 views. DOWN 72%.

        healthy_base = 8000
        viral_spike = [18000] * 5 + [15000] * 5 + [11000] * 5  # 15-day viral run
        viral_fade = [9000] * 10                                 # fading back
        post_crash = [2500] * 3                                  # CRASH

        scenario_a = (
            [healthy_base] * 60 +   # 60 days healthy
            viral_spike +           # 15 days viral (confuses the baseline slightly)
            viral_fade +            # 10 days fading
            post_crash              # 3 days CRASH
        )

        await run_scenario("ALGORITHM CHANGE (Gaming Channel)", scenario_a, db)


        # ── SCENARIO B: BAD CONTENT SPIRAL ───────────────────────────────────
        # Reality: A finance creator (30k subs) who's been consistent.
        # They start chasing trends — making "reaction" videos instead of
        # their usual "Personal Finance Tips" style.
        # Their audience slowly stops watching. CTR drops. Views erode.
        # Over 6 weeks, they lose 45% of their traffic. Humans miss it.
        #
        # Day  0-44: Consistent finance content. ~5,000 views/day.
        # Day 45-59: First few "reaction" videos. Slightly lower (~4,200).
        # Day 60-74: More bad content. Audience disengages (~3,500).
        # Day 75-89: Algorithm stops recommending them. (~2,700). DOWN 46%.

        def gradual_decline(start_views, end_views, days):
            """Creates a smooth, realistic declining curve (not a cliff)."""
            result = []
            for i in range(days):
                t = i / (days - 1)  # 0 to 1
                # Ease-in curve makes decline accelerate realistically
                eased = t * t
                v = start_views + (end_views - start_views) * eased
                result.append(v)
            return result

        scenario_b = (
            [5000] * 45 +                          # Healthy content era
            gradual_decline(4200, 3500, 15) +       # First "reaction" phase
            gradual_decline(3500, 2900, 15) +       # Full pivot to bad content
            gradual_decline(2900, 2700, 15)         # Algorithm stops caring
        )

        await run_scenario("BAD CONTENT SPIRAL (Finance Channel)", scenario_b, db)

        print("\n" + "="*60)
        print("  SIMULATION COMPLETE")
        print("  Tip: Check both alerts at http://localhost:8000/api/alerts")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(main())

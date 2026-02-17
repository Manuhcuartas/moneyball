"""Quick analysis of shot zones and their coordinate ranges."""
from app.core.database import SessionLocal
from app.models.shot import Shot
from sqlalchemy import func

db = SessionLocal()

# 1. Zone stats
print("ZONE STATS:")
results = db.query(
    Shot.zone,
    func.avg(Shot.x),
    func.avg(Shot.y),
    func.min(Shot.x),
    func.max(Shot.x),
    func.min(Shot.y),
    func.max(Shot.y),
    func.count(Shot.id),
).group_by(Shot.zone).order_by(Shot.zone).all()

for r in results:
    z, ax, ay, mnx, mxx, mny, mxy, cnt = r
    print(f"{z:<20} avgX={ax:>6.1f} avgY={ay:>6.1f}  X=[{mnx:>5.1f},{mxx:>5.1f}]  Y=[{mny:>5.1f},{mxy:>5.1f}]  n={cnt}")

# 2. Action types per zone
print("\nACTION TYPES PER ZONE:")
results2 = db.query(
    Shot.zone,
    Shot.action_type,
    func.count(Shot.id),
).group_by(Shot.zone, Shot.action_type).order_by(Shot.zone, Shot.action_type).all()

for r in results2:
    print(f"  {r[0]:<20} {r[1]:<20} n={r[2]}")

db.close()

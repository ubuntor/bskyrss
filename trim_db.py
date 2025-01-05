import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fetch import DATABASE, MAX_POSTS_IN_FEED, VALID_FILTERS, CACHE_DIR

log = lambda x: print(f"{datetime.now()}: {x}")

conn = sqlite3.connect(DATABASE)
curs = conn.cursor()
now = datetime.now(timezone.utc)

log("deleting users that haven't been fetched in a while and their feeds...")
old = (now - timedelta(days=7)).isoformat()
curs.execute("DELETE FROM fetches WHERE fetched < ?", (old,))
conn.commit()

curs.execute(
    "DELETE FROM feed_items WHERE did IN (SELECT feed_items.did FROM feed_items LEFT"
    " JOIN fetches ON feed_items.did = fetches.did WHERE fetches.did IS null)"
)
conn.commit()

log("deleting old feed items that will never be served...")
curs.execute(
    "DELETE FROM feed_items WHERE (did, cid) IN (SELECT did, cid FROM (SELECT did,"
    " cid, row_number() OVER (PARTITION BY did ORDER BY updated DESC) AS row_num FROM"
    f" feed_items) WHERE row_num > {MAX_POSTS_IN_FEED*len(VALID_FILTERS)})"
)
conn.commit()

log("deleting unreferenced posts...")
curs.execute(
    "DELETE FROM posts WHERE cid IN (SELECT posts.cid FROM posts LEFT JOIN feed_items"
    " ON posts.cid = feed_items.cid WHERE feed_items.cid IS null)"
)
conn.commit()

log("vacuuming...")
curs.execute("VACUUM")
conn.commit()

log("deleting old cache files...")
old = time.time() - 7 * 86400  # 1 week old
for path in Path(CACHE_DIR).glob("*.xml"):
    if path.stat().st_mtime < old:
        path.unlink()

t = datetime.now(timezone.utc) - now
log(f"done! took {t}")

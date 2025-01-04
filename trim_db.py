import sqlite3
from datetime import datetime, timezone

from fetch import DATABASE, MAX_POSTS_IN_FEED, VALID_FILTERS

log = lambda x: print(f"{datetime.now()}: {x}")

conn = sqlite3.connect(DATABASE)
curs = conn.cursor()
now = datetime.now(timezone.utc)

log("deleting users that haven't been fetched in a while and their feeds...")

# TODO
conn.commit()

log("deleting old feed items that will never be served...")
curs.execute(
    "DELETE FROM feed_items WHERE (did, cid) IN (SELECT did, cid FROM (SELECT did,"
    " cid, row_number() OVER (PARTITION BY did ORDER BY updated DESC) AS row_num FROM"
    f" feed_items) WHERE row_num > {MAX_POSTS_IN_FEED*len(VALID_FILTERS)})"
)
conn.commit()

log("deleting unreferenced posts...")
# TODO
conn.commit()

log("vacuuming...")
curs.execute("VACUUM")
conn.commit()

log("deleting old cache files...")
# TODO

t = datetime.now(timezone.utc) - now
log(f"done! took {t}")

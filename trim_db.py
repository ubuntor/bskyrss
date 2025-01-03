import sqlite3
from datetime import datetime, timezone

from fetch import DATABASE, MAX_POSTS_IN_FEED, VALID_FILTERS

conn = sqlite3.connect(DATABASE)
curs = conn.cursor()
now = datetime.now(timezone.utc)

print(
    f"{datetime.now()}: deleting users that haven't been fetched in a while and their"
    " feeds..."
)
# TODO
conn.commit()

print(f"{datetime.now()}: deleting unused cache files...")
# TODO

print(f"{datetime.now()}: deleting old feed items that will never be served...")
curs.execute(
    "DELETE FROM feed_items WHERE (did, cid) IN (SELECT did, cid FROM (SELECT did,"
    " cid, row_number() OVER (PARTITION BY did ORDER BY updated DESC) AS row_num FROM"
    f" feed_items) WHERE row_num > {MAX_POSTS_IN_FEED*len(VALID_FILTERS)})"
)
conn.commit()

print(f"{datetime.now()}: deleting unreferenced posts...")
# TODO
conn.commit()

print(f"{datetime.now()}: vacuuming...")
curs.execute("VACUUM")
conn.commit()

t = datetime.now(timezone.utc) - now
print(f"{datetime.now()}: done! took {t}")

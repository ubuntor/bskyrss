SELECT
    posts.cid,
    posts.did,
    posts.url,
    posts.html,
    posts.date,
    posts.handle,
    posts.name,
    posts.title,
    feed_items.updated,
    feed_items.is_repost
FROM feed_items
INNER JOIN posts ON feed_items.cid = posts.cid
WHERE feed_items.did = "blah" AND filter_a = 1
ORDER BY updated DESC
LIMIT 100

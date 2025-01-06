## fork tweaks/notes:

usage: `/feed/<did_or_handle>` (did preferred)

this can also take a `?filter=<filter>` param, where `<filter>` can be:
 * `posts_and_author_threads`: posts and threads consisting of only the author (default: this is what you see when viewing someone's profile)
 * `posts_with_replies`: all posts
 * `posts_no_replies`: no replies
 * `posts_with_media`: all posts by the author with media (i.e. the media tab)

misc tidbits:
- post titles are of the form:
  - regular post: `<text>`
  - reply: `Replied to <account>: <text>`, `Self-replied: <text>`, or `Replied to deleted/blocked post: ...`
  - quote: `Quoted <account>: <text>`, `Self-quoted: <text>`, or `Quoted detached/deleted/blocked post: ...` (if not a reply)
  - if a post is a repost, then the title gets prepended with `Reposted <account>: ` or `Self-reposted: `
- posts can have the following categories for ease of filtering: `reply`, `self-reply`, `quote`, `self-quote`, `repost`, `self-repost`, `image`, `video`
  - `reply` means non-self reply, etc.
- videos turn into images using the thumbnail (if your feed reader is hackable or you can have userscripts, you can turn those back into videos with hls.js)
- all embeds (quotes/images/videos/etc.) are above the post since that makes more sense from a reading-order perspective (and i'm cohost-brained)
- this will probably break in exciting ways if post dates are spoofed

deployment notes:
- if needed, use `ProxyFix`: https://flask.palletsprojects.com/en/stable/deploying/proxy_fix/
- run [`trim_db.py`](trim_db.py) regularly

original readme follows below:

# Bluesky to RSS bridge

Bluesky has built in support for RSS feeds on profiles, but these are
pretty much an afterthought.

 * They do not support showing images or videos in posts
 * Links do not work (only the text is shown)
 * External link previews are missing
 * Bluesky doesn't generate an RSS feed for any profile that has the
"require sign-in" option set, even though the full content of every post
is trivially available in JSON form to the public over an open protocol.

This project is intended to solve all of these problems.

There is a demo instance that you may use at
https://bskyrss.liliane.io/. You can subscribe to a Atom feed for any
profile at `https://bskyrss.liliane.io/handle/<fully.qualified.handle>`.

Please note that the demo instance limits downloading new posts to once
per hour - avoid excessively rescraping the feed as it won't get you new
posts any faster. You can always download posts yourself in their
original form using the open API.

## Running the software

This is a Flask application. You should run it behind a reverse proxy
using a WSGI frontend like uwsgi. If you have flask installed locally,
you can run it on your own machine for testing and development purposes
with `flask --app fetch.py run`.

The only dependencies (other than Python itself) are Flask and Requests.

## Limitations

 * Content warnings are not rendered.
 * Posts once downloaded are never updated or deleted.
 * The approach to caching is not very efficient. The best approach to
improving this software would probably be to directly translate it to
Go. It was mostly written on a single weekend so that I could follow
artists who release webcomics via Bluesky.
 * There are undeniably elements of this that are hacked together. I
didn't read more of the very lengthy set of specifications than I had to.
If there's stuff that just doesn't work or corner cases you care about,
please file an issue!

## License

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.

# Copyright 2024: A. Fontenot (https://github.com/afontenot)
# SPDX-License-Identifier: MPL-2.0
import re
import sqlite3
from datetime import datetime, timezone

import requests
from flask import (
    Flask,
    Response,
    abort,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
)
from werkzeug.exceptions import NotFound

MAX_POST_FETCH_SECS = 86400
REFETCH_HANDLES_SECS = 86400 * 7
REFETCH_PROFILES_SECS = 86400 * 7
CACHE_NONEXISTENT_HANDLES_SECS = 86400
CACHE_POSTS_SECS = 3600
CACHE_DIR = "cache"
DATABASE = "bsky.db"

# anti-feature?
SKIP_AUTH_REQ_POSTS = False

# constants
PROFILE_URL = "https://bsky.app/profile"
BSKY_PUBLIC_API = "https://public.api.bsky.app/xrpc"
VALID_HANDLE_REGEX = re.compile(
    r"^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
)
VALID_FILTERS = [
    "posts_and_author_threads",
    "posts_with_replies",
    "posts_no_replies",
    "posts_with_media",
]
DEFAULT_FILTER = "posts_and_author_threads"

app = Flask(__name__)
iso = datetime.fromisoformat


class BskyXrpcClient:
    def __init__(self):
        self.s = requests.Session()

    def get_posts(self, actor, post_filter, server_url=BSKY_PUBLIC_API, last=None):
        url = f"{server_url}/app.bsky.feed.getAuthorFeed"
        params = {
            "actor": actor,
            "filter": post_filter,
            "limit": 30,
        }

        now = datetime.now(timezone.utc)
        posts = {}
        while True:
            r = self.s.get(url, params=params)
            r.raise_for_status()
            earliest_post_date = now
            for post in (x["post"] for x in r.json()["feed"]):
                post_stub = post["uri"].split("/")[-1]
                data = {
                    "author": post["author"]["handle"],
                    "authorName": post["author"]["displayName"],
                    "date": iso(post["record"]["createdAt"]),
                    "text": post["record"]["text"],
                    # FIXME: improve this hardcoded link?
                    "url": f"{PROFILE_URL}/{post['author']['did']}/post/{post_stub}",
                }
                if "embed" in post:
                    data["embed"] = post["embed"]
                if "facets" in post["record"]:
                    data["facets"] = post["record"]["facets"]
                if data["date"] < now:
                    earliest_post_date = data["date"]
                posts[post["cid"]] = data

            if not last:
                return posts

            if (now - earliest_post_date).total_seconds() >= MAX_POST_FETCH_SECS:
                return posts

            params.update(
                {"cursor": earliest_post_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
            )

    def get_actor(self, handle, server_url=BSKY_PUBLIC_API):
        url = f"{server_url}/com.atproto.identity.resolveHandle"
        params = {"handle": handle}
        r = self.s.get(url, params=params)
        r.raise_for_status()
        return r.json()["did"]

    def get_profile(self, actor, server_url=BSKY_PUBLIC_API):
        url = f"{server_url}/app.bsky.actor.getProfile"
        params = {
            "actor": actor,
        }
        r = self.s.get(url, params=params)
        r.raise_for_status()
        return r.json()


def get_media_embeds(embed):
    embeds = []
    if embed["$type"] == "app.bsky.embed.images#view":
        for image in embed["images"]:
            alt = image["alt"]
            src = image["thumb"]
            embeds.append(
                {
                    "type": "image",
                    "url": src,
                    "alt": alt,
                }
            )
    elif embed["$type"] == "app.bsky.embed.video#view":
        embeds.append(
            {
                "type": "video",
                "thumbnail": embed["thumbnail"],
                "playlist": embed["playlist"],
            }
        )
    return embeds


def post_to_html(post, recurse=True):
    segments = []
    if "text" in post:
        text = post["text"]
        cursor = 0
        if "facets" in post:
            # FIXME: round-trip encoding sucks a lot, but is hard to avoid...
            btext = text.encode("utf-8")
            for facet in sorted(post["facets"], key=lambda x: x["index"]["byteStart"]):
                if facet["features"][0]["$type"] == "app.bsky.richtext.facet#link":
                    segments.append(
                        {
                            "type": "text",
                            "value": btext[cursor : facet["index"]["byteStart"]].decode(
                                "utf-8", "surrogateescape"
                            ),
                        }
                    )
                    url = facet["features"][0]["uri"]
                    link_text = btext[
                        facet["index"]["byteStart"] : facet["index"]["byteEnd"]
                    ].decode("utf-8", "surrogateescape")
                    segments.append(
                        {
                            "type": "link",
                            "text": link_text,
                            "url": url,
                        }
                    )
                    cursor = facet["index"]["byteEnd"]
                elif facet["features"][0]["$type"] == "app.bsky.richtext.facet#mention":
                    segments.append(
                        {
                            "type": "text",
                            "value": btext[cursor : facet["index"]["byteStart"]].decode(
                                "utf-8", "surrogateescape"
                            ),
                        }
                    )
                    did = facet["features"][0]["did"]
                    url = f"{PROFILE_URL}/{did}"
                    link_text = btext[
                        facet["index"]["byteStart"] : facet["index"]["byteEnd"]
                    ].decode("utf-8", "surrogateescape")
                    segments.append(
                        {
                            "type": "link",
                            "text": link_text,
                            "url": url,
                        }
                    )
                    cursor = facet["index"]["byteEnd"]
            segments.append(
                {
                    "type": "text",
                    "value": btext[cursor:].decode("utf-8", "surrogateescape"),
                }
            )
        else:
            segments.append({"type": "text", "value": text})

    if "embed" in post:
        media_embeds = get_media_embeds(post["embed"])
        if media_embeds:
            segments.extend(media_embeds)
        elif post["embed"]["$type"] == "app.bsky.embed.external#view":
            segments.append(
                {
                    "type": "extlink",
                    "thumbnail": post["embed"]["external"].get("thumb", ""),
                    "url": post["embed"]["external"]["uri"],
                    "text": post["embed"]["external"]["title"],
                    "description": post["embed"]["external"]["description"],
                }
            )
        elif (
            recurse
            and (
                post["embed"]["$type"] == "app.bsky.embed.record#view"
                or post["embed"]["$type"] == "app.bsky.embed.recordWithMedia#view"
            )
            and (
                "notFound" not in post["embed"]["record"]
                or not post["embed"]["record"]["notFound"]
            )
        ):
            # image or video quoted-posted
            if post["embed"]["$type"] == "app.bsky.embed.recordWithMedia#view":
                segments.extend(get_media_embeds(post["embed"]["media"]))
                post["embed"]["record"] = post["embed"]["record"]["record"]
            # some unhandled embeds, like starter packs, don't have authors
            if "author" in post["embed"]["record"]:
                author = post["embed"]["record"]["author"]
                post_stub = post["embed"]["record"]["uri"].split("/")[-1]
                segments.append(
                    {
                        "type": "quotepost",
                        "handle": author["handle"],
                        "date": post["embed"]["record"]["value"]["createdAt"],
                        # FIXME: improve this hardcoded link?
                        "url": f"{PROFILE_URL}/{author['did']}/post/{post_stub}",
                        "html": post_to_html(post["embed"]["record"]["value"], False),
                    }
                )

    return render_template("post.html", segments=segments)


def actorfeed(actor: str) -> Response:
    client = get_client()

    post_filter = request.args.get("filter", DEFAULT_FILTER)
    if post_filter not in VALID_FILTERS:
        abort(400)

    conn = get_db()
    curs = conn.cursor()
    now = datetime.now(timezone.utc)

    res = curs.execute(
        "SELECT fetched FROM fetches WHERE did = ? AND filter = ?", (actor, post_filter)
    ).fetchone()
    if res:
        fetched = iso(res[0])
        # if fetched less than an hour ago, return cached file
        post_age = (now - fetched).total_seconds()
        if post_age < CACHE_POSTS_SECS:
            try:
                return send_from_directory(
                    CACHE_DIR,
                    f"{actor}.{post_filter}.atom.xml",
                    max_age=CACHE_POSTS_SECS - post_age + 1,
                    mimetype="application/atom+xml",
                )
            except NotFound:
                pass

    # check last time actor feed was updated
    res = curs.execute("SELECT * FROM profiles WHERE did = ?", (actor,))
    res = res.fetchone()
    fetched = None

    # we know about this actor already
    if res:
        profile = {
            "did": res[0],
            "handle": res[1],
            "name": res[2],
            "avatar": res[3],
            "description": res[4],
            "updated": res[5],
        }

    # never fetched before, verify actor and fetch posts
    if (
        not res
        or (now - iso(profile["updated"])).total_seconds() > REFETCH_PROFILES_SECS
    ):
        try:
            print("fetching profile for", actor)
            profile = client.get_profile(actor)
        except requests.HTTPError:
            abort(404)

        # option: don't allow fetching "login-required" profiles
        if SKIP_AUTH_REQ_POSTS and "labels" in profile:
            for label in profile["labels"]:
                if (
                    label.get("src") == profile["did"]
                    and label.get("val") == "!no-unauthenticated"
                ):
                    abort(404)

        author = profile["displayName"]
        avatar = profile["avatar"]
        # descriptions can be missing
        description = profile.get("description", "")
        profile = {
            "did": actor,
            "handle": profile["handle"],
            "name": author,
            "avatar": avatar,
            "description": description,
            "updated": now.isoformat(),
        }
        curs.execute(
            "INSERT OR REPLACE INTO profiles VALUES(:did, :handle, :name, :avatar, :description, :updated)",
            profile,
        )
        conn.commit()

    # add additional metadata not saved in database
    profile["url"] = f"{PROFILE_URL}/{profile['did']}"

    try:
        posts = client.get_posts(actor, post_filter, last=fetched)
    except requests.HTTPError:
        abort(404)

    if not posts:
        abort(404)

    data = {"did": actor, "filter": post_filter, "fetched": now}
    curs.execute("INSERT OR REPLACE INTO fetches VALUES(:did, :filter, :fetched)", data)
    conn.commit()

    for cid, post in posts.items():
        # FIXME: look into updating edited posts
        postdata = curs.execute(
            "SELECT EXISTS(SELECT 1 FROM posts WHERE cid = ?)", (cid,)
        )
        postdata = postdata.fetchone()
        if not postdata[0]:
            html = post_to_html(post)
            data = {
                "cid": cid,
                "did": actor,
                "url": post["url"],
                "html": html,
                "date": post["date"].isoformat(),
                "handle": post["author"],
                "name": post["authorName"],
            }
            curs.execute(
                "INSERT INTO posts VALUES(:cid, :did, :url, :html, :date, :handle, :name)",
                data,
            )
            conn.commit()

    posts = curs.execute(
        "SELECT * FROM posts WHERE did = ? ORDER BY date DESC LIMIT 100", (actor,)
    )
    posts = posts.fetchall()

    posts_data = []

    for post in posts:
        posts_data.append(
            {
                "cid": post[0],
                "url": post[2],
                "html": post[3],
                "date": post[4],
                "author": post[6],
            }
        )

    feed_data = {
        "post_filter": post_filter,
        "url": request.url_root + f"actor/{actor}?filter={post_filter}",
    }

    ofs = render_template(
        "atom.xml", profile=profile, posts=posts_data, feed=feed_data
    ).encode("utf-8")

    with open(f"{CACHE_DIR}/{actor}.{post_filter}.atom.xml", "wb") as f:
        f.write(ofs)

    return send_from_directory(
        CACHE_DIR,
        f"{actor}.{post_filter}.atom.xml",
        max_age=CACHE_POSTS_SECS + 1,
        mimetype="application/atom+xml",
    )


def handlefeed(handle) -> Response:
    conn = get_db()
    curs = conn.cursor()
    res = curs.execute("SELECT did,updated FROM handles WHERE handle = ?", (handle,))
    res = res.fetchone()
    now = datetime.now(timezone.utc)

    if res:
        actor, updated = res
        if not actor:
            if (now - iso(updated)).total_seconds() < CACHE_NONEXISTENT_HANDLES_SECS:
                abort(404)
                # raise ValueError("requested cached non-existent handle too soon")

    if not res or (now - iso(updated)).total_seconds() > REFETCH_HANDLES_SECS:
        try:
            actor = get_client().get_actor(handle)
            updated = now
        except requests.HTTPError:
            abort(404)

        if actor:
            data = {"actor": actor, "handle": handle, "now": now}
            curs.execute(
                "INSERT OR REPLACE INTO handles VALUES(:handle, :actor, :now)", data
            )
            conn.commit()
        else:
            data = {"handle": handle, "now": now}
            curs.execute("INSERT OR REPLACE INTO handles VALUES(:handle, :now)", data)
            conn.commit()

    if actor:
        return actorfeed(actor)
    abort(404)


def get_client():
    client = getattr(g, "_client", None)
    if client is None:
        client = g._client = BskyXrpcClient()
    return client


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        with open("bsky.schema") as f:
            schema = f.read()
        db.executescript(schema)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


@app.route("/handle/<handle>")
def handle(handle):
    if len(handle) > 253 or not VALID_HANDLE_REGEX.match(handle):
        abort(404)
    return handlefeed(handle)


@app.route("/handle")
def bare_handle():
    handle = request.args.get("handle")
    if not handle:
        abort(404)
    if len(handle) > 253 or not VALID_HANDLE_REGEX.match(handle):
        abort(404)
    return redirect(f"/handle/{handle}")


@app.route("/actor/<actor>")
def actor(actor):
    if len(actor) != 32 or not actor.startswith("did:plc:") or not actor[8:].isalnum():
        abort(404)
    return actorfeed(actor)


@app.route("/")
def root():
    return render_template("root.html")

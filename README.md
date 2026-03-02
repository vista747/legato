# legato (beta)

Terminal-first Last.fm client (now playing + scrobble + top lists + pace + YouTube).

## Install (dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## Configure

You need a Last.fm API key. Create one on Last.fm (API account) and set:

```bash
legato config set lastfm_api_key YOUR_KEY
export LEGATO_LASTFM_SECRET="YOUR_LASTFM_SHARED_SECRET"
```

Then authenticate:

```bash
legato setup
```

Optional: YouTube first-result search requires a YouTube Data API v3 key:

```bash
legato config set youtube_api_key YOUR_YT_KEY
```

## Commands

- `legato setup`
- `legato current`
- `legato np "Artist" "Track" [--album "..."]`
- `legato scrobble "Artist" "Track" [--album "..."] [--ts now|<unix>]`
- `legato yt [Artist] [Track] [--open]`
- `legato top artist|album|track [-p day|week|month|quarter|year] [-n 10]`
- `legato artist|album|track [--name ...] [--artist ...] [-p ...]`
- `legato pace [-i 5000] [--target N] [-p ...]`
- `legato doctor`
- `legato config ...`

## Notes

- Last.fm "period" does not natively support `day`; this beta implements `day` by aggregating recent tracks from the last 24h.
- Secrets: Last.fm secret is read from `LEGATO_LASTFM_SECRET` by default (recommended).

from __future__ import annotations

MIN_HELP = """Usage:
  legato <command> [args] [options]

Core:
  setup                 authenticate with Last.fm
  current               show now playing / last scrobble
  np <artist> <track>   update now playing
  scrobble <a> <t>      submit scrobble
  yt [a] [t]            YouTube first result (needs youtube_api_key)

Lists:
  top artist|album|track   top 10 for period (default week)
  artist|album|track       info + plays (week + overall)

Other:
  pace                  ETA to next milestone
  config ...             config management
  doctor                 sanity checks

Common options:
  -p, --period  day|week|month|quarter|year
  -n, --limit   number of rows (top commands)
  --json        machine output on supported commands
"""

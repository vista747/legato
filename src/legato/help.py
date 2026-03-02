from __future__ import annotations

MIN_HELP = """Usage:
  legato <command> [args] [options]

Setup:
  legato setup                 connect your Last.fm account (browser approve)

Core:
  legato current               show now playing / last scrobble
  legato np <artist> <track>   update now playing
  legato scrobble <a> <t>      submit a scrobble
  legato yt [a] [t]            best YouTube match (optional key)

Lists:
  legato top artist|album|track   top 10 for period (default: week)
  legato artist|album|track       info + plays (week + overall)

Other:
  legato pace                  ETA to next milestone (default increment 5000)
  legato config ...             view/set optional config
  legato doctor                 sanity checks

Options:
  -p, --period  day|week|month|quarter|year
  -n, --limit   rows for top commands
  --json        machine output on supported commands
"""


#!/bin/sh
# Normalizes a posting URL for the "is this the same posting with a rotated
# URL" check, replacing the stable-prefix algorithm previously spelled out in
# prose in site-change-check.md, prompt.md and prompt-v2.md. Some ATS
# platforms mint a fresh random suffix on the last path segment on every
# crawl or publish without the posting itself changing.
#
# Usage: sh scripts/strip-url-tail.sh "<url>"
#
# Prints the URL with a trailing short (3-8 char) lowercase-alphanumeric
# hyphenated tail stripped from its last path segment, up to twice (some
# platforms append more than one). Compare two URLs' script output for
# equality to tell a rotated URL from a genuinely different posting.
#
# A stripped tail must contain at least one digit (real hash-like tails such
# as f16d/f3ee/a1b2c3 always do; ordinary words like "trainee" or "title"
# never do) - without this, a pure-letter word that happens to be 3-8 chars
# gets misread as a second hash tail and over-stripped. Confirmed against the
# joinus.hu worked example: "...-trainee-f16d" and "...-trainee-f16d-f3ee"
# must both reduce to "...-trainee", not "..." with "trainee" also gone.

set -eu

url="$1"
url="${url%/}"

case "$url" in
  */*) prefix="${url%/*}"; last="${url##*/}" ;;
  *)   prefix=""; last="$url" ;;
esac

strip_once() {
  input="$1"
  tail=$(printf '%s' "$input" | sed -E -n 's/.*-([a-z0-9]{3,8})$/\1/p')
  case "$tail" in
    *[0-9]*) printf '%s' "$input" | sed -E 's/-[a-z0-9]{3,8}$//' ;;
    *)       printf '%s' "$input" ;;
  esac
}

stripped=$(strip_once "$last")
if [ "$stripped" != "$last" ]; then
  again=$(strip_once "$stripped")
  if [ "$again" != "$stripped" ]; then
    stripped="$again"
  fi
fi

if [ -n "$prefix" ]; then
  printf '%s/%s\n' "$prefix" "$stripped"
else
  printf '%s\n' "$stripped"
fi

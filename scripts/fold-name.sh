#!/bin/sh
# Normalizes a company name or job title for duplicate matching against
# activeTitlesByCompany / knownActiveTitles, replacing the fold algorithm
# previously spelled out in prose in prompt.md, prompt-v2.md and
# site-processor.md. Must match the server's own normalization exactly
# (_ai_dupe_guard.mjs) or a real duplicate will silently miss.
#
# Usage:
#   sh scripts/fold-name.sh company "Knorr-Bremse Fékrendszerek Kft."
#   sh scripts/fold-name.sh title   "Junior PHP fejlesztő (Power BI)"
#
# Steps:
#   1. (title only) strip any (...) parenthetical first
#   2. strip Hungarian diacritics, lowercase
#   3. collapse every run of non [a-z0-9] characters to a single space, trim
#   4. (company only) drop bare legal-form suffix words

set -eu

mode="$1"
text="$2"

if [ "$mode" = "title" ]; then
  text=$(printf '%s' "$text" | sed -E 's/\([^)]*\)//g')
fi

folded=$(printf '%s' "$text" \
  | sed -e 's/á/a/g' -e 's/é/e/g' -e 's/í/i/g' -e 's/ó/o/g' -e 's/ö/o/g' -e 's/ő/o/g' \
        -e 's/ú/u/g' -e 's/ü/u/g' -e 's/ű/u/g' \
        -e 's/Á/A/g' -e 's/É/E/g' -e 's/Í/I/g' -e 's/Ó/O/g' -e 's/Ö/O/g' -e 's/Ő/O/g' \
        -e 's/Ú/U/g' -e 's/Ü/U/g' -e 's/Ű/U/g' \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/ /g; s/^ +//; s/ +$//')

if [ "$mode" = "company" ]; then
  result=""
  for word in $folded; do
    case " zrt nyrt kft bt kkt kht nonprofit ev zartkoruen mukodo reszvenytarsasag gmbh ag ltd limited llc inc plc sa srl bv nv oy ab as spa co " in
      *" $word "*) ;;
      *) result="$result $word" ;;
    esac
  done
  folded=$(printf '%s' "$result" | sed -E 's/^ +//; s/ +$//')
fi

printf '%s\n' "$folded"

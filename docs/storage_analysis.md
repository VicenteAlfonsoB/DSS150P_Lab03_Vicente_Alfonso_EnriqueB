# Goal 3 Storage Analysis

Medians of 5 repetitions, measured on this machine (MacBook Air, Apple
Silicon arm64, macOS), over 49,897 curated rows. These are measurements
from this hardware, not universal claims.

| storage_type | size_bytes | write_s  | full_read_s | filtered_read_s |
|--------------|-----------:|---------:|------------:|----------------:|
| csv          | 14,193,582 | 0.316258 |    0.114239 |        0.107082 |
| jsonl        | 29,891,684 | 0.340771 |    0.238224 |        0.273112 |
| parquet      |  5,433,864 | 0.129019 |    0.031575 |        0.009790 |
| postgresql   | 13,639,680 | 0.386492 |    0.192824 |        0.037187 |

Filtered read = rows where status = DELIVERED.

## The short version

Parquet should be the default for the curated layer, and it isn't close.
It won every axis at once: smallest file, fastest write, fastest full
read, fastest filtered read. Formats usually trade size against speed.
Parquet didn't have to.

JSONL should not have been a candidate for this dataset at all, and the
numbers say so bluntly.

## 1. Storage: Parquet wins, and the reason is structural

5.43 MB against CSV's 14.19 MB and JSONL's 29.89 MB. Identical content.

This is not compression cleverness bolted onto a text format — it falls
out of storing columns instead of rows. Put all 49,897 `status` values
next to each other and you have 6 distinct strings repeated endlessly,
which dictionary encoding collapses to small integer codes. Same for
`category` with 8 values. Numbers stay binary, so 86572.35 costs 8 bytes
rather than 8 characters and a delimiter.

JSONL being **more than double CSV** is the finding worth dwelling on.
Every record re-states all twenty column names as text. That's roughly
200 bytes of key names per row — about 10 MB of a 29 MB file spent
describing structure that CSV states once in a header and Parquet states
once in a schema. You are paying 10 MB to repeat yourself 49,897 times.

## 2. Full read: the text formats are paying a parsing tax

Parquet at 0.0316 s. CSV is 3.6x slower, JSONL 7.5x, PostgreSQL 6.1x.

Reading CSV or JSONL means parsing characters and inferring types for a
million individual values. Parquet values are already in their final
binary form with the schema in the footer, so the read is closer to
copying memory than to parsing. The smaller file compounds it a third
the bytes off disk before any decoding starts.

The lesson I'd draw: "CSV is simple" is a claim about human convenience,
not machine cost. The simplicity is paid for on every single read,
forever.

## 3. Filtered read: this is where the formats stop being comparable

Parquet at 0.0098 s 10.9x faster than CSV, 27.9x faster than JSONL.

The mechanism is predicate pushdown. Parquet keeps min/max statistics per
column per row group, so the reader discards whole row groups that cannot
contain `DELIVERED` without decoding them. Its filtered read is **3.2x
faster than its own full read**, which is the measurable fingerprint of
pushdown actually working.

CSV filtered (0.1071 s) versus CSV full (0.1142 s) is the control case:
no difference worth the name. There is no pushdown to have; the file is
parsed in full either way.

JSONL is the result I'd put in front of anyone still defending it here.
Filtered (0.2731 s) is **slower than full** (0.2382 s). Filtering a
format with no pushdown is strictly additional work. You pay for the
privilege of asking a narrower question.

PostgreSQL filtered (0.0372 s) is 5.2x faster than full (0.1928 s), and
I want to be precise about why, because it is easy to get wrong: there is
no index. `status` is unindexed and the benchmark table is created
without one. The planner still sequentially scans all 49,897 rows. The
entire saving is in materializing and shipping ~8,300 rows instead of
49,897. Anyone reading this table and concluding "the database used an
index" has read it wrong.

## 4. PostgreSQL's slow write is the correct trade, not a defect

0.3865 s, the slowest of the four and 3x Parquet.

A file write appends bytes to the filesystem and stops. A COPY crosses
the wire protocol, type-checks and converts every value, enforces NOT
NULL on fourteen columns, and writes both heap pages and the
write-ahead log. The WAL is the expensive part and it is the point: it
buys crash recovery. Parquet's 0.129 s buys nothing of the kind kill
the process mid-write and you have a corrupt file and no way to know it.

So I'd resist reading this row as "PostgreSQL is slow." The benchmark
measures the one thing databases are worst at and none of the things
they exist for: concurrency, transactions, constraints, indexed lookups.
I kept the table unindexed specifically to make the write comparison
honest; a primary key would have made it slower still, and would have
been worth it.

## 5. What I would actually use, and what I would argue against

**Parquet for the curated layer.** It wins every axis here and its
advantage widens with scale, because column pruning and pushdown improve
as data grows while text parsing does not. This is the default and the
burden of proof is on anyone proposing otherwise.

**PostgreSQL for serving.** Not because of these numbers because of
what these numbers don't measure. Bulk sequential read is not what a
warehouse gets asked for. Point lookups, joins, concurrent readers,
transactional correctness, and constraint enforcement are why you pay the
write cost, and every one of them is invisible in this table.

**CSV for interchange, and nothing else.** It is the format you hand
someone who has a spreadsheet and no Parquet reader. It loses types on
every round trip — reading back the CSV in this benchmark turns NUMERIC
into float and timestamps into strings. Using it as a storage layer means
re-inferring your own schema every time you open your own data.

**JSONL: not for this dataset, and I'd push back on anyone proposing it.**
It costs double CSV's storage, posts the worst query time of the four,
and gets *worse* when you filter. Its one real strength nested and
irregular structure — is worth nothing here, because this data is flat
and rectangular. Paying for flexibility you cannot use is the whole
argument against it.

And one disqualifier that outranks every performance number above: **JSON
has no decimal type.** The money columns are NUMERIC in PostgreSQL and
decimal128 in Parquet, both exact. The JSONL benchmark had to convert
them to float. For currency that is not a tuning consideration, it is a
correctness failure, and it would rule JSONL out even if it had won on
speed and size.

## Caveats

These are measurements, and I want to be honest about their limits:

- Medians of 5 runs on one machine under ordinary desktop load, not a
  controlled benchmark environment.
- Repeated reads benefit from the OS page cache. Cold-cache numbers
  would be slower across the board and would favour the smallest file
  more strongly, which strengthens the Parquet conclusion rather than
  weakening it.
- The PostgreSQL instance is local and unindexed, so no network latency
  is included and no index maintenance cost either.
- One dataset, one shape, ~50k rows. I would not extrapolate these ratios
  to a billion rows without re-measuring, and neither should anyone
  reading this.
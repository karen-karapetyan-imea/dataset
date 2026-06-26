# Artsy table mapping

Importer: `import_artsy_to_db.py`  
DDL reference: `sql/006_artsy.sql`

| JSONL `entity_type` | Postgres table | Primary key (`id`) |
|---------------------|----------------|--------------------|
| `artist` | `artsy_artists` | slug from `/artist/{slug}` |
| `artwork` | `artsy_artworks` | slug from `/artwork/{slug}` |
| `partner` | `artsy_partners` | slug from `/partner/{slug}` |
| `show` | `artsy_shows` | slug from `/show/{slug}` |
| `fair` | `artsy_fairs` | slug from `/fair/{slug}` |

Junction table `artsy_artwork_artist` is populated when an artwork row includes `artist_external_id` and that artist exists in `artsy_artists`.

If your Render database already has `artsy_*` tables with different columns, run `\d artsy_artists` (etc.) and adjust `import_artsy_to_db.py` upsert column lists to match.

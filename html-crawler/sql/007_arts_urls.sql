-- Add explicit page URL columns to legacy Artsper tables.
-- Safe to re-run (IF NOT EXISTS).

ALTER TABLE public.arts_artists
  ADD COLUMN IF NOT EXISTS artist_url TEXT;

ALTER TABLE public.arts_artworks
  ADD COLUMN IF NOT EXISTS artwork_url TEXT;

CREATE INDEX IF NOT EXISTS idx_arts_artists_artist_url
  ON public.arts_artists (artist_url);

CREATE INDEX IF NOT EXISTS idx_arts_artworks_artwork_url
  ON public.arts_artworks (artwork_url);

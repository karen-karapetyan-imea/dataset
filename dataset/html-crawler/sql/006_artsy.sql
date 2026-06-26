-- Artsy HTML import tables (align with existing artsy_* schema when present).

CREATE TABLE IF NOT EXISTS public.artsy_artists (
  id TEXT PRIMARY KEY,
  name TEXT,
  biography TEXT,
  image_url TEXT,
  profile_url TEXT,
  canonical_url TEXT,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.artsy_artworks (
  id TEXT PRIMARY KEY,
  title TEXT,
  artist_name TEXT,
  artist_external_id TEXT,
  description TEXT,
  medium TEXT,
  year TEXT,
  price TEXT,
  currency TEXT,
  image_url TEXT,
  image_urls TEXT[],
  canonical_url TEXT,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.artsy_partners (
  id TEXT PRIMARY KEY,
  name TEXT,
  description TEXT,
  image_url TEXT,
  profile_url TEXT,
  canonical_url TEXT,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.artsy_shows (
  id TEXT PRIMARY KEY,
  name TEXT,
  description TEXT,
  start_date TEXT,
  end_date TEXT,
  canonical_url TEXT,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.artsy_fairs (
  id TEXT PRIMARY KEY,
  name TEXT,
  description TEXT,
  start_date TEXT,
  end_date TEXT,
  canonical_url TEXT,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.artsy_artwork_artist (
  artwork_id TEXT NOT NULL REFERENCES public.artsy_artworks (id) ON DELETE CASCADE,
  artist_id TEXT NOT NULL REFERENCES public.artsy_artists (id) ON DELETE CASCADE,
  PRIMARY KEY (artwork_id, artist_id)
);

CREATE INDEX IF NOT EXISTS idx_artsy_artworks_artist_external_id ON public.artsy_artworks (artist_external_id);
CREATE INDEX IF NOT EXISTS idx_artsy_artworks_updated_at ON public.artsy_artworks (updated_at);

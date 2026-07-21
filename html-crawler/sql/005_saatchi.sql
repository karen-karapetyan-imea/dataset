-- Saatchi Art HTML import tables (artists + artworks).

CREATE TABLE IF NOT EXISTS public.saatchi_artists (
  id BIGINT PRIMARY KEY,
  user_name TEXT,
  artist_name TEXT,
  first_name TEXT,
  last_name TEXT,
  profile_image_url TEXT,
  biography TEXT,
  education TEXT,
  exhibitions TEXT,
  country TEXT,
  city TEXT,
  state TEXT,
  profile_url TEXT UNIQUE,
  canonical_url TEXT,
  joined_date DATE,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saatchi_artists_user_name
  ON public.saatchi_artists (user_name);
CREATE INDEX IF NOT EXISTS idx_saatchi_artists_artist_name
  ON public.saatchi_artists (artist_name);
CREATE INDEX IF NOT EXISTS idx_saatchi_artists_country
  ON public.saatchi_artists (country);
CREATE INDEX IF NOT EXISTS idx_saatchi_artists_updated_at
  ON public.saatchi_artists (updated_at);

CREATE TABLE IF NOT EXISTS public.saatchi_artworks (
  id BIGINT PRIMARY KEY,
  artist_id BIGINT REFERENCES public.saatchi_artists (id),
  title TEXT,
  artist_name TEXT,
  artist_profile_url TEXT,
  category TEXT,
  medium TEXT,
  materials TEXT[],
  styles TEXT[],
  subject TEXT,
  description TEXT,
  price NUMERIC(12, 2),
  currency TEXT,
  availability TEXT,
  artwork_year INTEGER,
  image_url TEXT,
  image_urls TEXT[],
  dimensions JSONB,
  sku TEXT,
  keywords TEXT[],
  canonical_url TEXT UNIQUE,
  html_path TEXT,
  raw_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saatchi_artworks_artist_id
  ON public.saatchi_artworks (artist_id);
CREATE INDEX IF NOT EXISTS idx_saatchi_artworks_artist_name
  ON public.saatchi_artworks (artist_name);
CREATE INDEX IF NOT EXISTS idx_saatchi_artworks_category
  ON public.saatchi_artworks (category);
CREATE INDEX IF NOT EXISTS idx_saatchi_artworks_price
  ON public.saatchi_artworks (price);
CREATE INDEX IF NOT EXISTS idx_saatchi_artworks_updated_at
  ON public.saatchi_artworks (updated_at);

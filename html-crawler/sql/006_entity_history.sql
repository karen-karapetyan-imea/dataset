-- Entity history tracking: activity type lookup + change events.
--
-- This file is intended to be applied after the base schema (e.g. 005_saatchi.sql).

CREATE TABLE IF NOT EXISTS public.activity_types (
  id SERIAL PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  label TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.entity_history (
  id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,                -- 'saatchi' | 'artsper' | 'artsy'
  entity_type TEXT NOT NULL,          -- 'artwork' | 'artist'
  entity_id BIGINT NOT NULL,
  activity_type_id INT NOT NULL REFERENCES public.activity_types(id),
  field_name TEXT,
  old_value TEXT,
  new_value TEXT,
  metadata JSONB,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_history_lookup
  ON public.entity_history (source, entity_type, entity_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_history_activity
  ON public.entity_history (activity_type_id, observed_at DESC);

-- Seed common activity codes so imports don't need to create them one-by-one.
INSERT INTO public.activity_types (code, label) VALUES
  ('created', 'Created'),
  ('price_changed', 'Price changed'),
  ('currency_changed', 'Currency changed'),
  ('availability_changed', 'Availability changed'),
  ('title_changed', 'Title changed'),
  ('category_changed', 'Category changed'),
  ('medium_changed', 'Medium changed'),
  ('image_changed', 'Image changed'),
  ('artist_name_changed', 'Artist name changed'),
  ('biography_changed', 'Biography changed'),
  ('profile_image_changed', 'Profile image changed'),
  ('country_changed', 'Country changed'),
  ('city_changed', 'City changed'),
  ('state_changed', 'State changed'),
  ('description_changed', 'Description changed'),
  ('year_changed', 'Year changed'),
  ('artwork_year_changed', 'Artwork year changed')
ON CONFLICT (code) DO NOTHING;


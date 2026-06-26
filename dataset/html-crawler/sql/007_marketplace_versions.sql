-- Version history for marketplace entities (price and field changes across weekly syncs).

CREATE TABLE IF NOT EXISTS public.marketplace_entity_versions (
  id BIGSERIAL PRIMARY KEY,
  marketplace TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  version_no INT NOT NULL,
  previous_snapshot JSONB NOT NULL,
  current_snapshot JSONB NOT NULL,
  changed_fields TEXT[] NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  sync_source TEXT NOT NULL DEFAULT 'weekly_cron',
  UNIQUE (marketplace, entity_type, entity_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_mev_lookup
  ON public.marketplace_entity_versions (marketplace, entity_type, entity_id, observed_at DESC);

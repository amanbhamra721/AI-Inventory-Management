-- Multi-brand ledger schema upgrades for wholesale document diversity.

ALTER TABLE inventory_ledger
ADD COLUMN IF NOT EXISTS brand_name VARCHAR(100) DEFAULT 'BR',
ADD COLUMN IF NOT EXISTS party_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS reference_no VARCHAR(100);

CREATE TABLE IF NOT EXISTS product_catalog (
  id BIGSERIAL PRIMARY KEY,
  sender_phone VARCHAR(20),
  canonical_name VARCHAR(150) NOT NULL,
  aliases TEXT[] DEFAULT '{}',
  brand_name VARCHAR(100),
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(sender_phone, canonical_name)
);

CREATE INDEX IF NOT EXISTS idx_ledger_brand_party ON inventory_ledger(sender_phone, brand_name, party_name);
CREATE INDEX IF NOT EXISTS idx_catalog_sender_canonical ON product_catalog(sender_phone, canonical_name);

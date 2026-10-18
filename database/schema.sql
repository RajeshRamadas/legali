-- Initial schema draft for PostgreSQL. Use migrations for evolving environments.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE,
  phone TEXT UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT,
  account_status TEXT NOT NULL DEFAULT 'active'
    CHECK (account_status IN ('active','pending_verification','suspended','deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS user_roles (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS customers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL,
  full_name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  preferred_contact_channel TEXT CHECK (preferred_contact_channel IN ('email','phone','sms','whatsapp','in_app')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS properties (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
  property_type TEXT NOT NULL CHECK (property_type IN ('apartment','independent_house','commercial','residential_plot','agricultural_land','other')),
  address_line TEXT,
  locality TEXT,
  city TEXT,
  district TEXT,
  state TEXT,
  postal_code TEXT,
  project_or_apartment_name TEXT,
  flat_or_unit_number TEXT,
  property_id_or_pid TEXT,
  survey_number TEXT,
  subdivision_or_surnoc TEXT,
  village TEXT,
  hobli TEXT,
  taluk TEXT,
  country_code TEXT NOT NULL DEFAULT 'IN',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  description TEXT NOT NULL,
  supported_property_types TEXT[] NOT NULL DEFAULT '{}',
  required_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
  required_documents JSONB NOT NULL DEFAULT '[]'::jsonb,
  indicative_fee_min NUMERIC(12,2),
  indicative_fee_max NUMERIC(12,2),
  currency CHAR(3) NOT NULL DEFAULT 'INR',
  estimated_turnaround_hours INTEGER,
  location_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
  disclaimer TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
  property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
  service_type_id UUID REFERENCES service_types(id) ON DELETE SET NULL,
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','submitted','closed','abandoned')),
  intake_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  consent_notice_version TEXT,
  consented_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  sender_type TEXT NOT NULL CHECK (sender_type IN ('customer','assistant','system','agent')),
  body TEXT NOT NULL,
  structured_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_number TEXT NOT NULL UNIQUE,
  customer_id UUID NOT NULL REFERENCES customers(id),
  property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
  service_type_id UUID NOT NULL REFERENCES service_types(id),
  conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'submitted'
    CHECK (status IN ('draft','submitted','under_review','waiting_for_customer','approved_for_processing','assigned','in_progress','quality_review','completed','cancelled','rejected','on_hold','reopened')),
  priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high','urgent')),
  source TEXT NOT NULL DEFAULT 'website' CHECK (source IN ('website','chatbot','phone','whatsapp','admin','referral')),
  structured_answers JSONB NOT NULL DEFAULT '{}'::jsonb,
  estimated_fee_min NUMERIC(12,2),
  estimated_fee_max NUMERIC(12,2),
  due_at TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  agent_user_id UUID NOT NULL REFERENCES users(id),
  assigned_by_user_id UUID REFERENCES users(id),
  assignment_note TEXT,
  assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  unassigned_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ticket_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  event_type TEXT NOT NULL,
  old_value JSONB,
  new_value JSONB,
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ticket_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  visibility TEXT NOT NULL DEFAULT 'customer' CHECK (visibility IN ('customer','internal')),
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_request_id UUID NOT NULL REFERENCES service_requests(id) ON DELETE CASCADE,
  uploaded_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  original_filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  byte_size BIGINT NOT NULL CHECK (byte_size >= 0),
  storage_key TEXT NOT NULL UNIQUE,
  checksum_sha256 TEXT,
  document_category TEXT,
  scan_status TEXT NOT NULL DEFAULT 'pending' CHECK (scan_status IN ('pending','clean','infected','failed')),
  access_classification TEXT NOT NULL DEFAULT 'confidential' CHECK (access_classification IN ('internal','confidential','restricted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_request_id UUID REFERENCES service_requests(id) ON DELETE SET NULL,
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
  channel TEXT NOT NULL CHECK (channel IN ('email','sms','whatsapp','in_app')),
  template_key TEXT NOT NULL,
  delivery_status TEXT NOT NULL DEFAULT 'queued' CHECK (delivery_status IN ('queued','sent','delivered','failed','cancelled')),
  provider_reference TEXT,
  error_code TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS consents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
  conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
  purpose TEXT NOT NULL,
  notice_version TEXT NOT NULL,
  consented BOOLEAN NOT NULL,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  request_id TEXT,
  ip_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_requests_status_created ON service_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_customer_created ON service_requests(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_service ON service_requests(service_type_id);
CREATE INDEX IF NOT EXISTS idx_assignments_agent_active ON assignments(agent_user_id, assigned_at DESC) WHERE unassigned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_events_request_created ON ticket_events(service_request_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_request_created ON ticket_messages(service_request_id, created_at);
CREATE INDEX IF NOT EXISTS idx_documents_request ON documents(service_request_id);

INSERT INTO roles(name) VALUES ('customer'), ('agent'), ('admin'), ('super_admin')
ON CONFLICT (name) DO NOTHING;

INSERT INTO service_types
(slug, name, category, description, supported_property_types, disclaimer)
VALUES
('home-apartment-assistance','Home & Apartment Assistance','Homes','Help coordinating common home and apartment property-service requests.', ARRAY['apartment','independent_house','commercial'], 'Availability and requirements depend on location and service scope.'),
('ec-assistance','Encumbrance Certificate Assistance','Legal & Documents','Assistance understanding and requesting EC-related records through authorized channels.', ARRAY['apartment','independent_house','residential_plot','agricultural_land','commercial'], 'This is assistance, not a guarantee of title or legal clearance.'),
('khata-property-records','Khata & Property Records','Legal & Documents','Assistance with khata and property account documentation.', ARRAY['apartment','independent_house','residential_plot','commercial'], 'Requirements and eligibility vary by jurisdiction.'),
('rtc-mutation-assistance','RTC / Mutation Assistance','Land & Plots','Assistance organizing details for RTC/Pahani and mutation record requests.', ARRAY['agricultural_land','residential_plot'], 'Record availability and interpretation must be verified with the relevant authority.'),
('plot-maintenance','Plot Cleaning & Maintenance','Maintenance','Request plot cleaning, inspection, fencing or related maintenance where available.', ARRAY['residential_plot'], 'Service area and quote must be confirmed before acceptance.'),
('property-inspection','Property Inspection & Report','Inspection','Request a property visit and photo/video condition report.', ARRAY['apartment','independent_house','residential_plot','commercial'], 'Inspection scope and limitations will be confirmed before work begins.')
ON CONFLICT (slug) DO NOTHING;

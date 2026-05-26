-- ============================================================
-- codencode LMS — Workshop Portal Schema
-- Run this once against your Railway PostgreSQL database
-- ============================================================

-- Core workshop table
CREATE TABLE IF NOT EXISTS workshops (
    id              SERIAL PRIMARY KEY,
    title           TEXT NOT NULL,
    emoji           TEXT DEFAULT '📚',
    description     TEXT DEFAULT '',
    workshop_date   DATE NOT NULL,
    time_start      TIME DEFAULT '09:00',
    time_end        TIME DEFAULT '17:00',
    location        TEXT DEFAULT '',
    location_type   TEXT DEFAULT 'physical',  -- 'physical' | 'online' | 'hybrid'
    language        TEXT DEFAULT 'English',
    color_theme     TEXT DEFAULT 'python',     -- 'python' | 'ml' | 'vibe' | 'data'
    recurrence      TEXT DEFAULT 'none',       -- 'none' | 'weekly' | custom label
    published       BOOLEAN DEFAULT FALSE,     -- draft until you flip this to TRUE
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

-- Materials per workshop (slides, PDFs, videos, code, quizzes, links)
CREATE TABLE IF NOT EXISTS workshop_materials (
    id              SERIAL PRIMARY KEY,
    workshop_id     INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    material_type   TEXT NOT NULL DEFAULT 'pdf',  -- 'pdf' | 'slide' | 'video' | 'code' | 'quiz' | 'link'
    icon            TEXT DEFAULT '📄',
    file_size       TEXT DEFAULT '',   -- e.g. '2.3 MB' or '' for links
    duration        TEXT DEFAULT '',   -- e.g. '12 pages', '15 min', '5 exercises'
    section         TEXT DEFAULT 'Materials',  -- section heading, e.g. 'Pre-reading', 'Materials', 'Bonus'
    download_url    TEXT DEFAULT '#',  -- S3/Drive/Railway static URL
    sort_order      INTEGER DEFAULT 1
);

-- Day schedule items
CREATE TABLE IF NOT EXISTS workshop_schedule (
    id              SERIAL PRIMARY KEY,
    workshop_id     INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    time_slot       TEXT NOT NULL,     -- e.g. '09:00 AM'
    title           TEXT NOT NULL,
    description     TEXT DEFAULT '',
    sort_order      INTEGER DEFAULT 1
);

-- Pinned announcements per workshop
CREATE TABLE IF NOT EXISTS workshop_announcements (
    id              SERIAL PRIMARY KEY,
    workshop_id     INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    icon            TEXT DEFAULT '📢',
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Student registrations (who signed up + their form data)
CREATE TABLE IF NOT EXISTS workshop_registrations (
    id                  SERIAL PRIMARY KEY,
    workshop_id         INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    student_name        TEXT NOT NULL,
    email               TEXT NOT NULL,
    phone               TEXT,
    age_range           TEXT,
    occupation          TEXT,
    industry            TEXT,
    experience_level    TEXT,
    motivation          TEXT,
    preferred_language  TEXT DEFAULT 'English',
    referral_source     TEXT,
    registered_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workshop_id, email)  -- one registration per email per workshop
);

-- Progress tracking (which materials each student has completed)
CREATE TABLE IF NOT EXISTS workshop_progress (
    id              SERIAL PRIMARY KEY,
    workshop_id     INTEGER NOT NULL REFERENCES workshops(id) ON DELETE CASCADE,
    material_id     INTEGER NOT NULL REFERENCES workshop_materials(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    completed_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (material_id, email)
);

-- ── Indexes for performance ──────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_workshop_materials_workshop ON workshop_materials(workshop_id);
CREATE INDEX IF NOT EXISTS idx_workshop_registrations_email ON workshop_registrations(email);
CREATE INDEX IF NOT EXISTS idx_workshop_progress_email ON workshop_progress(email);
CREATE INDEX IF NOT EXISTS idx_workshop_progress_material ON workshop_progress(material_id);

-- ── Seed: example workshop (set published=TRUE to make it visible) ───────
-- INSERT INTO workshops (title, emoji, description, workshop_date, time_start, time_end, location, location_type, language, color_theme, published)
-- VALUES ('Python for Beginners — One Day Bootcamp', '🐍', 'A full-day hands-on Python workshop for absolute beginners.', '2026-05-31', '09:00', '17:00', 'KL', 'physical', 'English', 'python', TRUE);

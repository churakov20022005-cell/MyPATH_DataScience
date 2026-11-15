ALTER TABLE materials ADD COLUMN IF NOT EXISTS content_format varchar(10) NOT NULL DEFAULT 'text'
    CHECK (content_format IN ('text', 'html'));
CREATE TABLE IF NOT EXISTS images (
    id uuid PRIMARY KEY,
    mime_type varchar(30) NOT NULL CHECK (mime_type IN ('image/png', 'image/jpeg', 'image/webp', 'image/gif')),
    data bytea NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 5242880),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS material_images (
    material_id bigint NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    image_id uuid NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    PRIMARY KEY (material_id, image_id)
);
CREATE INDEX IF NOT EXISTS material_images_image_idx ON material_images(image_id);

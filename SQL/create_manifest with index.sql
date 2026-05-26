-- Table: public.manifest

DROP TABLE IF EXISTS public.manifest;

CREATE TABLE IF NOT EXISTS public.manifest
(
    id integer NOT NULL DEFAULT nextval('c2m_logistic_id_seq'::regclass),
    itemid character varying(50) COLLATE pg_catalog."default",
	masterno character varying(50) COLLATE pg_catalog."default",
    weight_g bigint,
    country character varying(50) COLLATE pg_catalog."default",
    service character varying(50) COLLATE pg_catalog."default",
    dt_package date,
    package_num character varying(50) COLLATE pg_catalog."default",
    dtflow timestamp without time zone,
    source_file_name text COLLATE pg_catalog."default",
    id_registry bigint,
    CONSTRAINT manifest_pkey PRIMARY KEY (id),
    CONSTRAINT manifest_itemid_key UNIQUE (itemid)
)

TABLESPACE pg_default;

ALTER TABLE IF EXISTS public.manifest
    OWNER to postgres;
-- Index: idx_c2m_logistic_itemid

-- DROP INDEX IF EXISTS public.idx_c2m_logistic_itemid;

CREATE UNIQUE INDEX IF NOT EXISTS idx_manifest_itemid
    ON public.manifest USING btree
    (itemid COLLATE pg_catalog."default" ASC NULLS LAST)
    TABLESPACE pg_default;
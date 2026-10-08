CREATE TYPE "public"."action_origin" AS ENUM('llm', 'fallback');--> statement-breakpoint
CREATE TYPE "public"."evidence_source_type" AS ENUM('event', 'alert', 'user_history', 'ip_reputation', 'related_logs', 'mitre', 'knowledge');--> statement-breakpoint
CREATE TYPE "public"."incident_status" AS ENUM('open', 'investigating', 'resolved');--> statement-breakpoint
CREATE TYPE "public"."reputation_level" AS ENUM('known_good', 'unknown', 'suspicious', 'malicious');--> statement-breakpoint
CREATE TYPE "public"."investigation_run_status" AS ENUM('queued', 'running', 'completed', 'failed');--> statement-breakpoint
CREATE TYPE "public"."severity" AS ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');--> statement-breakpoint
CREATE TABLE "alerts" (
	"id" text PRIMARY KEY DEFAULT 'alt_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"event_id" text NOT NULL,
	"risk_score" smallint NOT NULL,
	"anomaly_score" double precision NOT NULL,
	"model_version" text NOT NULL,
	"severity" "severity" NOT NULL,
	"reasons_json" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "alerts_event_id_unique" UNIQUE("event_id"),
	CONSTRAINT "alerts_risk_score_ck" CHECK (risk_score BETWEEN 0 AND 100)
);
--> statement-breakpoint
CREATE TABLE "analysts" (
	"id" text PRIMARY KEY DEFAULT 'an_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"email" text NOT NULL,
	"name" text NOT NULL,
	"password_hash" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "analysts_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "detection_signals" (
	"id" text PRIMARY KEY DEFAULT 'sig_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"event_id" text NOT NULL,
	"rule_name" text NOT NULL,
	"rule_score" smallint NOT NULL,
	"severity" "severity" NOT NULL,
	"reason" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "detection_signals_event_rule_uq" UNIQUE("event_id","rule_name"),
	CONSTRAINT "detection_signals_rule_score_ck" CHECK (rule_score BETWEEN 0 AND 100)
);
--> statement-breakpoint
CREATE TABLE "evidence" (
	"id" text PRIMARY KEY DEFAULT 'ev_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"investigation_run_id" text NOT NULL,
	"source_type" "evidence_source_type" NOT NULL,
	"source_id" text NOT NULL,
	"claim" text NOT NULL,
	"data_json" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "incident_alerts" (
	"incident_id" text NOT NULL,
	"alert_id" text NOT NULL,
	CONSTRAINT "incident_alerts_incident_id_alert_id_pk" PRIMARY KEY("incident_id","alert_id")
);
--> statement-breakpoint
CREATE TABLE "incident_events" (
	"incident_id" text NOT NULL,
	"event_id" text NOT NULL,
	CONSTRAINT "incident_events_incident_id_event_id_pk" PRIMARY KEY("incident_id","event_id")
);
--> statement-breakpoint
CREATE TABLE "incidents" (
	"id" text PRIMARY KEY DEFAULT 'inc_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"title" text NOT NULL,
	"status" "incident_status" DEFAULT 'open' NOT NULL,
	"risk_score" smallint NOT NULL,
	"severity" "severity" NOT NULL,
	"primary_user_id" text,
	"primary_ip" "inet",
	"started_at" timestamp with time zone NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "incidents_risk_score_ck" CHECK (risk_score BETWEEN 0 AND 100)
);
--> statement-breakpoint
CREATE TABLE "investigation_runs" (
	"id" text PRIMARY KEY DEFAULT 'run_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"incident_id" text NOT NULL,
	"status" "investigation_run_status" DEFAULT 'queued' NOT NULL,
	"requires_review" boolean DEFAULT false NOT NULL,
	"verdict_json" jsonb,
	"raw_output_json" jsonb,
	"validation_errors_json" jsonb,
	"model_name" text,
	"prompt_version" text,
	"error_message" text,
	"started_at" timestamp with time zone,
	"completed_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "investigation_trace" (
	"id" text PRIMARY KEY DEFAULT 'trc_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"investigation_run_id" text NOT NULL,
	"step_index" integer NOT NULL,
	"action_type" text NOT NULL,
	"action_origin" "action_origin",
	"tool_name" text,
	"input_json" jsonb,
	"result_json" jsonb,
	"evidence_ids_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"retrieval_refs_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "investigation_trace_run_step_uq" UNIQUE("investigation_run_id","step_index"),
	CONSTRAINT "investigation_trace_step_index_ck" CHECK ("investigation_trace"."step_index" >= 0)
);
--> statement-breakpoint
CREATE TABLE "ip_reputation" (
	"ip" "inet" PRIMARY KEY NOT NULL,
	"reputation" "reputation_level" NOT NULL,
	"score" smallint NOT NULL,
	"tags_json" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"source" text NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "ip_reputation_score_ck" CHECK (score BETWEEN 0 AND 100)
);
--> statement-breakpoint
CREATE TABLE "knowledge_documents" (
	"id" text PRIMARY KEY DEFAULT 'kd_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"source" text NOT NULL,
	"external_id" text NOT NULL,
	"title" text NOT NULL,
	"content_hash" text NOT NULL,
	"qdrant_point_id" text,
	"metadata_json" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "knowledge_documents_source_external_uq" UNIQUE("source","external_id")
);
--> statement-breakpoint
CREATE TABLE "mitre_techniques" (
	"technique_id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"tactics_json" jsonb NOT NULL,
	"description" text NOT NULL,
	"attack_version" text NOT NULL,
	CONSTRAINT "mitre_techniques_id_ck" CHECK ("mitre_techniques"."technique_id" ~ '^T[0-9]{4}(\.[0-9]{3})?$')
);
--> statement-breakpoint
CREATE TABLE "security_events" (
	"id" text PRIMARY KEY DEFAULT 'se_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"external_event_id" text NOT NULL,
	"occurred_at" timestamp with time zone NOT NULL,
	"user_id" text NOT NULL,
	"source_ip" "inet" NOT NULL,
	"event_type" text NOT NULL,
	"action" text NOT NULL,
	"resource" text NOT NULL,
	"status" text NOT NULL,
	"metadata_json" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "security_events_external_event_id_unique" UNIQUE("external_event_id")
);
--> statement-breakpoint
ALTER TABLE "alerts" ADD CONSTRAINT "alerts_event_id_security_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."security_events"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "detection_signals" ADD CONSTRAINT "detection_signals_event_id_security_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."security_events"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "evidence" ADD CONSTRAINT "evidence_investigation_run_id_investigation_runs_id_fk" FOREIGN KEY ("investigation_run_id") REFERENCES "public"."investigation_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "incident_alerts" ADD CONSTRAINT "incident_alerts_incident_id_incidents_id_fk" FOREIGN KEY ("incident_id") REFERENCES "public"."incidents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "incident_alerts" ADD CONSTRAINT "incident_alerts_alert_id_alerts_id_fk" FOREIGN KEY ("alert_id") REFERENCES "public"."alerts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "incident_events" ADD CONSTRAINT "incident_events_incident_id_incidents_id_fk" FOREIGN KEY ("incident_id") REFERENCES "public"."incidents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "incident_events" ADD CONSTRAINT "incident_events_event_id_security_events_id_fk" FOREIGN KEY ("event_id") REFERENCES "public"."security_events"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "investigation_runs" ADD CONSTRAINT "investigation_runs_incident_id_incidents_id_fk" FOREIGN KEY ("incident_id") REFERENCES "public"."incidents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "investigation_trace" ADD CONSTRAINT "investigation_trace_investigation_run_id_investigation_runs_id_fk" FOREIGN KEY ("investigation_run_id") REFERENCES "public"."investigation_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "evidence_run_idx" ON "evidence" USING btree ("investigation_run_id");--> statement-breakpoint
CREATE INDEX "incident_alerts_alert_idx" ON "incident_alerts" USING btree ("alert_id");--> statement-breakpoint
CREATE INDEX "incident_events_event_idx" ON "incident_events" USING btree ("event_id");--> statement-breakpoint
CREATE INDEX "incidents_status_updated_idx" ON "incidents" USING btree ("status","updated_at");--> statement-breakpoint
CREATE INDEX "investigation_runs_incident_idx" ON "investigation_runs" USING btree ("incident_id");--> statement-breakpoint
CREATE INDEX "knowledge_documents_content_hash_idx" ON "knowledge_documents" USING btree ("content_hash");--> statement-breakpoint
CREATE INDEX "security_events_occurred_at_idx" ON "security_events" USING btree ("occurred_at");--> statement-breakpoint
CREATE INDEX "security_events_user_time_idx" ON "security_events" USING btree ("user_id","occurred_at");--> statement-breakpoint
CREATE INDEX "security_events_ip_time_idx" ON "security_events" USING btree ("source_ip","occurred_at");
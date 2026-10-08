CREATE TABLE "analyst_sessions" (
	"id" text PRIMARY KEY DEFAULT 'ses_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 16) NOT NULL,
	"analyst_id" text NOT NULL,
	"token_hash" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"revoked_at" timestamp with time zone,
	CONSTRAINT "analyst_sessions_token_hash_unique" UNIQUE("token_hash")
);
--> statement-breakpoint
ALTER TABLE "analyst_sessions" ADD CONSTRAINT "analyst_sessions_analyst_id_analysts_id_fk" FOREIGN KEY ("analyst_id") REFERENCES "public"."analysts"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "analyst_sessions_analyst_idx" ON "analyst_sessions" USING btree ("analyst_id");
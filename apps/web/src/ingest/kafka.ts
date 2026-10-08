// Kafka producer for normalized events (D-040, D-043). No `server-only` so integration tests can import it;
// the native client cannot be bundled for the browser anyway.
import { KafkaJS } from "@confluentinc/kafka-javascript";
import { SCHEMA_VERSION, type NormalizedEvent } from "../contracts/security-event.ts";

/** Production topic (created by Compose `kafka-init`). Tests use their own topics so they never feed the worker. */
export const SECURITY_EVENTS_TOPIC = "security-events";
export const eventsTopic = (): string => process.env.KAFKA_EVENTS_TOPIC || SECURITY_EVENTS_TOPIC;
export const PRODUCE_TIMEOUT_MS = 8_000;

export interface EventMessage {
  key: string;
  value: string;
  headers: Record<string, string>;
}

/** Keyed by user_id so one user's events stay ordered within a partition (D-014). */
export function toKafkaMessage(event: NormalizedEvent): EventMessage {
  return {
    key: event.user_id,
    value: JSON.stringify(event),
    headers: { "schema-version": SCHEMA_VERSION, "content-type": "application/json" },
  };
}

export function parseBrokers(value: string | undefined): string[] {
  const brokers = (value ?? "").split(",").map((b) => b.trim()).filter(Boolean);
  if (brokers.length === 0) throw new Error("KAFKA_BROKERS is not set (copy .env.example to .env at the repo root)");
  return brokers;
}

/** Client config shared by the producer and tests: IPv4 only, client logging off (D-040). */
export function kafkaClient(brokers: string[]): KafkaJS.Kafka {
  return new KafkaJS.Kafka({
    kafkaJS: { brokers, logLevel: KafkaJS.logLevel.NOTHING },
    "broker.address.family": "v4",
  });
}

export class EventProducer {
  private readonly brokers: string[];
  private readonly topic: string;
  private producer: KafkaJS.Producer | undefined;
  private connecting: Promise<void> | undefined;

  constructor(brokers: string[], topic: string = SECURITY_EVENTS_TOPIC) {
    this.brokers = brokers;
    this.topic = topic;
  }

  private async connected(): Promise<KafkaJS.Producer> {
    if (!this.producer) {
      this.producer = kafkaClient(this.brokers).producer({
        kafkaJS: { acks: -1, idempotent: true },
        "message.timeout.ms": PRODUCE_TIMEOUT_MS,
      });
    }
    this.connecting ??= this.producer.connect().catch((error: unknown) => {
      this.connecting = undefined; // retry the connection on the next request
      throw error;
    });
    await this.connecting;
    return this.producer;
  }

  /** Resolves once the broker acknowledged the message (acks=all); rejects after PRODUCE_TIMEOUT_MS. */
  async publish(event: NormalizedEvent): Promise<void> {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Kafka did not acknowledge within ${PRODUCE_TIMEOUT_MS} ms`)), PRODUCE_TIMEOUT_MS);
    });
    try {
      await Promise.race([
        (async () => {
          const producer = await this.connected();
          await producer.send({ topic: this.topic, messages: [toKafkaMessage(event)] });
        })(),
        timeout,
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  async close(): Promise<void> {
    if (this.producer && this.connecting) await this.producer.disconnect().catch(() => undefined);
    this.producer = undefined;
    this.connecting = undefined;
  }
}

let shared: EventProducer | undefined;

/** Process-wide producer for the web server, created on first use from KAFKA_BROKERS / KAFKA_EVENTS_TOPIC. */
export function eventProducer(): EventProducer {
  shared ??= new EventProducer(parseBrokers(process.env.KAFKA_BROKERS), eventsTopic());
  return shared;
}

/** Creates a topic if it does not exist (test setup; the production topic comes from Compose). */
export async function ensureTopic(brokers: string[], topic: string): Promise<void> {
  const admin = kafkaClient(brokers).admin();
  await admin.connect();
  try {
    await admin.createTopics({ topics: [{ topic, numPartitions: 3, replicationFactor: 1 }] });
  } catch (error) {
    if (!String(error).includes("already exists")) throw error;
  } finally {
    await admin.disconnect();
  }
}

export interface ConsumedMessage {
  key: string | null;
  headers: Record<string, string>;
  value: unknown;
}

/** Test helper: reads `topic` from the beginning until every wanted event_id was seen or the timeout elapses. */
export async function consumeEventIds(
  brokers: string[],
  topic: string,
  wanted: string[],
  timeoutMs = 20_000,
): Promise<Map<string, ConsumedMessage>> {
  const found = new Map<string, ConsumedMessage>();
  const consumer = kafkaClient(brokers).consumer({
    kafkaJS: { groupId: `sentinelx-test-${Date.now()}-${Math.random().toString(36).slice(2)}`, fromBeginning: true },
  });
  await consumer.connect();
  try {
    await consumer.subscribe({ topic });
    await new Promise<void>((resolve) => {
      const timer = setTimeout(resolve, timeoutMs);
      void consumer.run({
        eachMessage: async ({ message }) => {
          let value: unknown;
          try {
            value = JSON.parse(message.value?.toString() ?? "null");
          } catch {
            return; // not one of ours
          }
          const id = (value as { event_id?: unknown } | null)?.event_id;
          if (typeof id === "string" && wanted.includes(id)) {
            const headers = Object.fromEntries(
              Object.entries(message.headers ?? {}).map(([k, v]) => [k, Buffer.isBuffer(v) ? v.toString() : String(v)]),
            );
            found.set(id, { key: message.key?.toString() ?? null, headers, value });
            if (found.size === wanted.length) {
              clearTimeout(timer);
              resolve();
            }
          }
        },
      });
    });
  } finally {
    await consumer.disconnect();
  }
  return found;
}

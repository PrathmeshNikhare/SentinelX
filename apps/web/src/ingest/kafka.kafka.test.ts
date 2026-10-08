// Phase 03 integration: a normalized event travels into Kafka through the real producer and is read back.
// Uses its own topic so test traffic never reaches the detection worker's `security-events` topic.
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { normalizedEvent } from "../contracts/security-event.ts";
import { requireEnv } from "../db/env.ts";
import { consumeEventIds, ensureTopic, EventProducer, parseBrokers, PRODUCE_TIMEOUT_MS } from "./kafka.ts";
import { normalizeEvent } from "./normalize.ts";

const TOPIC = "security-events-test";
const brokers = parseBrokers(requireEnv("KAFKA_BROKERS"));
const producer = new EventProducer(brokers, TOPIC);

const event = (id: string) => {
  const result = normalizeEvent(
    {
      event_id: id,
      timestamp: new Date().toISOString(),
      user_id: "Kafka.Test",
      source_ip: "192.0.2.44",
      event_type: "authentication",
      action: "login",
      resource: "vpn-portal",
      status: "failed",
      metadata: { attempt: 1 },
    },
    new Date(),
  );
  if (!result.ok) throw new Error("fixture event invalid");
  return result.event;
};

beforeAll(async () => {
  await ensureTopic(brokers, TOPIC);
});

afterAll(async () => {
  await producer.close();
});

describe("EventProducer against the Compose broker", () => {
  it("publishes events that can be consumed with key, headers and a contract-valid value", async () => {
    const ids = [`kafka-test-${Date.now()}-1`, `kafka-test-${Date.now()}-2`];
    for (const id of ids) await producer.publish(event(id));

    const found = await consumeEventIds(brokers, TOPIC, ids);
    expect([...found.keys()].sort()).toEqual([...ids].sort());
    for (const message of found.values()) {
      expect(message.key).toBe("kafka.test");
      expect(message.headers).toMatchObject({ "schema-version": "v1", "content-type": "application/json" });
      expect(normalizedEvent.safeParse(message.value).success).toBe(true);
    }
  });

  it("rejects within the produce timeout when no broker is reachable", async () => {
    const unreachable = new EventProducer(["127.0.0.1:1"], TOPIC);
    const started = Date.now();
    await expect(unreachable.publish(event(`kafka-test-unreachable-${Date.now()}`))).rejects.toThrow();
    expect(Date.now() - started).toBeLessThan(PRODUCE_TIMEOUT_MS + 3_000);
    await unreachable.close();
  });
});

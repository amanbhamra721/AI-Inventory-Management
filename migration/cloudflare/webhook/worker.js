export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET") {
      return verifyWebhook(url, env);
    }

    if (request.method === "POST") {
      return receiveWebhook(request, env, ctx);
    }

    return new Response("Method not allowed", { status: 405 });
  }
};

function verifyWebhook(url, env) {
  const mode = url.searchParams.get("hub.mode");
  const challenge = url.searchParams.get("hub.challenge");
  const token = url.searchParams.get("hub.verify_token");

  if (mode === "subscribe" && token === env.VERIFY_TOKEN) {
    return new Response(challenge, { status: 200 });
  }

  return new Response("Forbidden", { status: 403 });
}

async function receiveWebhook(request, env, ctx) {
  let payload;
  try {
    payload = await request.json();
  } catch {
    return new Response(JSON.stringify({ ok: false, error: "invalid_json" }), {
      status: 400,
      headers: { "content-type": "application/json" }
    });
  }

  // Always acknowledge quickly to avoid webhook retries.
  const ack = new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "content-type": "application/json" }
  });

  // Fire-and-forget forwarding to your async processing API.
  ctx.waitUntil(forwardEvent(payload, env));
  return ack;
}

async function forwardEvent(payload, env) {
  if (!env.PROCESSOR_URL) return;

  await fetch(env.PROCESSOR_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-worker-secret": env.PROCESSOR_SHARED_SECRET || ""
    },
    body: JSON.stringify(payload)
  });
}

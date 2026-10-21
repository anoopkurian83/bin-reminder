export default {
  async fetch(request) {
    const url = new URL(request.url);

    // Forward the path (/trigger or /announce) and query string to Voice Monkey
    const vmUrl = "https://api-v3.voicemonkey.io" + url.pathname + url.search;

    const response = await fetch(vmUrl, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      },
      body: request.method === "POST" ? await request.text() : undefined,
    });

    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};

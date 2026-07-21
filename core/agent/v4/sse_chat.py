

# ══════════ SSE — Streaming chat (primary, industry standard) ══════════

@app.post("/v3/sse/{session_id}")
async def sse_stream(session_id: str, req: Request):
    """SSE streaming endpoint — primary chat path.
    
    Client: POST json {content: "..."}
    Server: SSE stream of AI response tokens
    """
    body = await req.json()
    text = body.get("content", "")
    
    async def generate():
        try:
            # Route through gateway for streaming
            import urllib.request
            api_data = json.dumps({
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": text}],
                "max_tokens": 2000,
                "stream": True,
            })
            gw_req = urllib.request.Request(
                "http://127.0.0.1:8080/v1/chat/completions",
                api_data.encode(),
                {"Content-Type": "application/json", "Authorization": "Bearer not-needed"}
            )
            r = urllib.request.urlopen(gw_req, timeout=60)
            # Read SSE from gateway
            for line in r:
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    yield f"data: {decoded}\n\n"
            yield f"data: [DONE]\n\n"
        except Exception as e:
            logger.exception("SSE stream failed")
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx proxy buffering off
        }
    )

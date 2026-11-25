"""Request-body size limit (pure ASGI middleware).

The body is read up front, so an oversized request is rejected with 413 before any handler
(or JSON parser) sees it, whether or not the client sent a Content-Length header.
"""
import json

_NO_BODY_METHODS = {"GET", "HEAD", "OPTIONS", "DELETE"}


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.max_bytes <= 0:
            return await self.app(scope, receive, send)

        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > self.max_bytes
            except ValueError:
                too_large = True
            if too_large:
                return await self._reject(send)

        if scope.get("method") in _NO_BODY_METHODS and length is None:
            return await self.app(scope, receive, send)

        # Buffer the body (bounded), then replay it to the app.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                return await self._reject(send)
            chunks.append(body)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    async def _reject(self, send):
        mb = self.max_bytes / (1024 * 1024)
        body = json.dumps({"detail": f"Request body too large (limit {mb:g} MB)."}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

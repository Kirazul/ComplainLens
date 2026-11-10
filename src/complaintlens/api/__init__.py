"""HTTP API used by the LunaGo website and the ComplaintLens console.

Run locally:  uv run complaintlens serve   (then open http://localhost:8000/docs)

- ``public``: what anyone can use (send a message, follow and continue a conversation);
- ``account``: customer accounts on the website (sign-in, rides, bookings, conversations);
- ``staff``: the console, signed in (sign-in, team, inbox, tickets, live events);
- ``research``: the console's Insights and Annotate pages, signed in;
- ``relay``: machine endpoints for the forum relay (channel token);
- ``inbox``: the email poller;
- ``main``: the application (startup, middleware, routers).
"""

from complaintlens.api.main import app

__all__ = ["app"]

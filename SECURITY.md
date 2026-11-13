# Security and publication boundary

The public repository contains neutral integration code and fictional examples. Original corporate documents, personal profiles, voices, build outputs, generated SDK checkout, indexes, identifiers, `.env` files, and historical instructions are not tracked. The code does not load those private local files implicitly.

External provider operations and microphone capture are disabled by default. Opting in can send approved text, reference excerpts, and audio to providers. Configure only your own authorized credentials; never paste them into source or issues. No key is supplied by this repository. Removing a secret from source does not revoke an earlier exposed credential.

HTTP and WebSocket controls bind to loopback, but are intended for a trusted local environment. They do not implement internet-facing authentication or tenant isolation. Keep untrusted clients away from them. The application builds retrieval state from reviewed Markdown instead of deserializing local pickle indexes. Prompt labeling reduces instruction confusion but does not establish prompt-injection immunity.

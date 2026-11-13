# Operator guide

## Offline review

Create a dedicated virtual environment, install `requirements-checks.txt`, and run `python offline_demo.py` followed by `python -m unittest discover -s tests -v`. No API key, microphone, viewer, or network service is needed. Start `python start.py` only when you intend to open the loopback API and WebSocket listener.

## Optional live session

Install `requirements-providers.txt` in a compatible Python 3.11/3.12 environment and provision system FFmpeg. Configure your own process-environment credentials and permitted models. Inspect the knowledge document and provider data-handling terms before setting `AVATAR_ENABLE_PROVIDERS=1`. The first question can send approved knowledge chunks for embedding; questions, reference excerpts, text, and audio can be sent to their configured providers. No local production corpus is selected automatically.

For microphone use, install PyAudio with the platform's audio prerequisites and set `AVATAR_ENABLE_MICROPHONE=1`. Capture is mono 48 kHz, ends after approximately two seconds below its amplitude threshold, and is bounded to 30 seconds. The threshold is a simple heuristic and is not a trained voice-activity detector.

Connect a viewer to `ws://127.0.0.1:9999`, implement the numeric states in `mappings.py`, and handle `phonemes` as approximate character intervals. Broadcasts share one local avatar state. HTTP voice input returns WAV; a viewer must separately receive/play that audio if required by its architecture.

## Optional Telegram transport

Install `requirements-bot.txt`, configure your own `BOT_TOKEN` and a comma-separated `AVATAR_ALLOWED_USER_IDS`, and run `python start.py --with-bot`. An empty allowlist denies all users. The bridge does not export Telegram histories or embed account IDs in source. Bot polling is never part of CI.

## Shutdown and maintenance

Stop the launcher with Ctrl+C. Keep local environment files, recordings, provider responses, and generated indexes outside Git. Run offline checks and the secret scan after edits. Review compatibility separately before changing cloud SDKs; passing protocol tests does not prove a live voice pipeline or avatar rendering session works.

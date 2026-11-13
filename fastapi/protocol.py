"""Offline avatar wire protocol. Character timings are a uniform heuristic."""
import json
import math
from mappings import phoneme_mappings, anim_mappings, emotion_mappings

def character_timings(text, duration):
    if not math.isfinite(duration) or duration < 0:
        raise ValueError('Duration must be finite and nonnegative')
    if not text:
        return []
    step = duration / len(text)
    return [f'{phoneme_mappings.get(char.lower(), 0)}_{i * step}_{(i + 1) * step}'
            for i, char in enumerate(text)]

def avatar_payload(text, duration, emotion='Neutral'):
    codes = {key.lower(): value for key, value in emotion_mappings.items()}
    return {'phonemes': character_timings(text, duration),
            'anim_state': anim_mappings['talk'],
            'emotion_state': codes.get(str(emotion).lower(), codes['neutral'])}

async def broadcast(connections, data):
    """Iterate a snapshot: disconnects must not mutate an active set iterator."""
    encoded = json.dumps(data, ensure_ascii=False)
    for connection in tuple(connections):
        try:
            await connection.send(encoded)
        except (ConnectionError, OSError):
            connections.discard(connection)
        except Exception as exc:
            # WebSocket versions expose different closed-connection subclasses.
            if type(exc).__name__.startswith('ConnectionClosed'):
                connections.discard(connection)
            else:
                raise

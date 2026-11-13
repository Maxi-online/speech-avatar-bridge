"""Loopback speech, retrieval and avatar bridge. All providers are opt-in."""
import asyncio
from contextlib import asynccontextmanager, suppress
from io import BytesIO
import json
import logging
import os
import wave
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from chunks import Chunk
from mappings import anim_mappings
from protocol import avatar_payload, character_timings, broadcast

logger = logging.getLogger(__name__)
ws_connections = set()
chunk = Chunk()
usr_key = 'generic'
mic_ready = True
audio_lock = asyncio.Lock()

def providers_enabled():
    return os.environ.get('AVATAR_ENABLE_PROVIDERS') == '1'

async def send_ws_data(data):
    await broadcast(ws_connections, data)

async def parse_swebsocket_message(message):
    global usr_key
    try:
        data = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return {'error':'Message must be valid JSON'}
    if not isinstance(data, dict):
        return {'error':'Message must be a JSON object'}
    if data.get('action') == 'usr_key':
        usr_key = 'generic'
        return {'profile':'generic'}
    if data.get('action') == 'a_input' and data.get('value') == 1:
        if os.environ.get('AVATAR_ENABLE_MICROPHONE') != '1':
            return {'error':'Microphone capture is disabled'}
        if not providers_enabled():
            return {'error':'External providers are disabled'}
        if audio_lock.locked():
            return {'error':'Audio processing is busy'}
        async with audio_lock:
            await record_audio_and_send()
        return {'status':'complete'}
    return {'error':'Unknown action'}

async def websocket_handler(websocket):
    ws_connections.add(websocket)
    try:
        async for message in websocket:
            result = await parse_swebsocket_message(message)
            await websocket.send(json.dumps(result))
    finally:
        ws_connections.discard(websocket)

@asynccontextmanager
async def lifespan(app):
    # Serving is a deliberate action. Importing this module opens no socket.
    import websockets
    server = await websockets.serve(websocket_handler, '127.0.0.1', int(os.environ.get('AVATAR_WS_PORT', '9999')),
                                    origins=[None, 'http://127.0.0.1:8000', 'http://localhost:8000'], max_size=65536)
    try:
        yield
    finally:
        server.close()
        await server.wait_closed()

app = FastAPI(title='Speech Avatar Bridge', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
    allow_origins=os.environ.get('AVATAR_CORS_ORIGINS', 'http://127.0.0.1:8000,http://localhost:8000').split(','),
    allow_credentials=False, allow_methods=['GET','POST'], allow_headers=['Content-Type'])

class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    user_id: int = 0
    history: list[str] = Field(default_factory=list, max_length=20)

class AnimationRequest(BaseModel):
    anim_state: str = Field(max_length=32)

@app.get('/health')
async def health():
    return {'status':'ok', 'providers_enabled':providers_enabled(), 'knowledge_initialized':chunk.db is not None}

@app.post('/api/get_answer_async')
async def get_answer(request: ChatRequest):
    if not providers_enabled():
        raise HTTPException(503, 'External providers are disabled')
    try:
        answer = await chunk.async_get_answer(request.text, request.history, usr_key)
        return {'message':answer['response_text'], **answer}
    except Exception:
        logger.warning('Text provider operation failed')
        raise HTTPException(502, 'Text provider operation failed') from None

@app.post('/api/set_anim_state')
async def set_anim_state(request: AnimationRequest):
    key = request.anim_state.lower()
    if key not in anim_mappings:
        raise HTTPException(422, 'Unknown animation state')
    result = {'anim_state':anim_mappings[key]}
    await send_ws_data(result)
    return result

def speech_session():
    if not providers_enabled():
        raise RuntimeError('External providers are disabled')
    from speechkit import Session
    token, folder = os.environ.get('SK_TOKEN'), os.environ.get('CATALOG_ID')
    if not token or not folder:
        raise RuntimeError('Speech credentials are not configured')
    return Session.from_yandex_passport_oauth_token(token, folder)

def recognize_audio(content):
    from speechkit import ShortAudioRecognition
    return ShortAudioRecognition(speech_session()).recognize(BytesIO(content), sampleRateHertz='48000')

def synthesize_audio(text):
    import grpc
    import requests
    from yandex.cloud.ai.tts.v3 import tts_pb2, tts_service_pb2_grpc
    from pydub import AudioSegment
    if not providers_enabled():
        raise RuntimeError('External providers are disabled')
    response = requests.post('https://iam.api.cloud.yandex.net/iam/v1/tokens',
        json={'yandexPassportOauthToken':os.environ['SK_TOKEN']}, timeout=20)
    response.raise_for_status()
    token = response.json()['iamToken']
    output = AudioSegment.silent(duration=0)
    with grpc.secure_channel('tts.api.cloud.yandex.net:443', grpc.ssl_channel_credentials()) as channel:
        stub = tts_service_pb2_grpc.SynthesizerStub(channel)
        for offset in range(0, len(text), 200):
            request = tts_pb2.UtteranceSynthesisRequest(text=text[offset:offset+200],
                output_audio_spec=tts_pb2.AudioFormatOptions(container_audio=tts_pb2.ContainerAudio(
                    container_audio_type=tts_pb2.ContainerAudio.WAV)),
                hints=[tts_pb2.Hints(voice=os.environ.get('AVATAR_VOICE','lera'))],
                loudness_normalization_type=tts_pb2.UtteranceSynthesisRequest.LUFS)
            parts = stub.UtteranceSynthesis(request, metadata=(('authorization', f'Bearer {token}'),
                ('x-folder-id', os.environ['CATALOG_ID'])), timeout=45)
            output += AudioSegment.from_wav(BytesIO(b''.join(part.audio_chunk.data for part in parts)))
    stream = BytesIO()
    output.export(stream, format='wav')
    return stream.getvalue(), len(output)/1000

async def process_audio(content):
    await send_ws_data({'anim_state':anim_mappings['think']})
    text = await asyncio.to_thread(recognize_audio, content)
    answer = await chunk.async_get_answer(text, [], usr_key)
    audio, duration = await asyncio.to_thread(synthesize_audio, answer['response_text'])
    payload = avatar_payload(answer['response_text'], duration, answer['emotion_state'])
    await send_ws_data(payload)
    return audio, payload

@app.post('/api/recognize_and_synthesize')
async def audio_endpoint(request: Request):
    if not providers_enabled():
        raise HTTPException(503, 'External providers are disabled')
    content = bytearray()
    async for part in request.stream():
        content.extend(part)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, 'Audio exceeds 10 MiB')
    if not content:
        raise HTTPException(400, 'Audio body is empty')
    if audio_lock.locked():
        raise HTTPException(409, 'Audio processing is busy')
    try:
        async with audio_lock:
            audio, payload = await process_audio(bytes(content))
        return Response(audio, media_type='audio/wav')
    except Exception:
        logger.warning('Speech provider operation failed')
        raise HTTPException(502, 'Speech provider operation failed') from None

def capture_microphone():
    """Explicit hardware operation: 48 kHz mono, bounded to 30 seconds."""
    if os.environ.get('AVATAR_ENABLE_MICROPHONE') != '1':
        raise RuntimeError('Microphone capture is disabled')
    import pyaudio
    import numpy as np
    device = pyaudio.PyAudio()
    stream = None
    frames, quiet = [], 0
    try:
        stream = device.open(format=pyaudio.paInt16, channels=1, rate=48000, input=True, frames_per_buffer=1024)
        for _ in range(int(30 * 48000 / 1024)):
            frame = stream.read(1024, exception_on_overflow=False)
            frames.append(frame)
            amplitude = np.abs(np.frombuffer(frame, dtype=np.int16).astype(np.int32)).max()
            quiet = quiet + 1 if amplitude < 500 else 0
            if quiet > int(2 * 48000 / 1024):
                break
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        device.terminate()
    from pydub import AudioSegment
    stream = BytesIO()
    AudioSegment(data=b''.join(frames), sample_width=2, frame_rate=48000, channels=1).export(stream, format='ogg')
    return stream.getvalue()

async def record_audio_and_send():
    global mic_ready
    mic_ready = False
    try:
        await send_ws_data({'anim_state':anim_mappings['listen']})
        content = await asyncio.to_thread(capture_microphone)
        return await process_audio(content)
    finally:
        mic_ready = True

def calculate_timing_for_characters(audio_path, text):
    with wave.open(str(audio_path), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    return character_timings(text, duration)

def extract_character_timing(text, audio, sr):
    if sr <= 0:
        raise ValueError('Sample rate must be positive')
    return character_timings(text, len(audio)/sr)

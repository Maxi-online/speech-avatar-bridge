import asyncio
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'fastapi'))
from protocol import character_timings, avatar_payload, broadcast
from chunks import select_documents, validate_answer, build_messages, Chunk
from fastapi.testclient import TestClient
import main

class ProtocolTests(unittest.TestCase):
    def test_empty_text_and_invalid_duration(self):
        self.assertEqual(character_timings('', 1), [])
        for duration in [-1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):character_timings('a', duration)

    def test_wire_mapping_and_total_duration(self):
        entries = character_timings('аa?', 1.2)
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].split('_')[0], '1')
        self.assertEqual(entries[1].split('_')[0], '1')
        self.assertEqual(entries[2].split('_')[0], '0')
        self.assertAlmostEqual(float(entries[-1].split('_')[2]), 1.2)

    def test_emotion_case_and_safe_fallback(self):
        self.assertEqual(avatar_payload('a',1,'hApPy')['emotion_state'],1)
        self.assertEqual(avatar_payload('a',1,'unknown')['emotion_state'],7)

    def test_disconnect_during_broadcast_keeps_other_peers(self):
        closed = SimpleNamespace()
        class Peer:
            def __init__(self,fail=False):self.fail,self.messages=fail,[]
            async def send(self,message):
                if self.fail:raise ConnectionError('closed')
                self.messages.append(json.loads(message))
        bad,good=Peer(True),Peer()
        peers={bad,good}
        asyncio.run(broadcast(peers, {'anim_state':6}))
        self.assertEqual(peers,{good})
        self.assertEqual(good.messages,[{'anim_state':6}])

    def test_retrieval_uses_lower_l2_distance(self):
        near,far=SimpleNamespace(page_content='supported'),SimpleNamespace(page_content='unrelated')
        selected=select_documents([(near,0.2),(far,0.9)],0.5)
        self.assertEqual(selected,[near])
        messages=build_messages('question',selected,[],'generic instructions')
        self.assertIn('supported',messages[1]['content'])
        self.assertNotIn('unrelated',messages[1]['content'])

    def test_structured_answer_validation(self):
        answer={'response_text':'Demo','emotion_state':'Neutral','emotion_intensity':0.1}
        self.assertEqual(validate_answer(answer),answer)
        for change in [{'emotion_intensity':2},{'emotion_state':'unsupported'},{'extra':'field'}]:
            with self.assertRaises(ValueError):validate_answer({**answer,**change})

class OfflineBoundaryTests(unittest.TestCase):
    def test_provider_initialization_is_explicitly_disabled(self):
        with patch.dict(os.environ,{'AVATAR_ENABLE_PROVIDERS':'0'}):
            with self.assertRaisesRegex(RuntimeError,'disabled'):asyncio.run(Chunk().initialize())

    def test_microphone_and_old_profile_are_not_activated(self):
        with patch.dict(os.environ,{'AVATAR_ENABLE_MICROPHONE':'0'}), patch.object(main,'record_audio_and_send',new_callable=AsyncMock) as record:
            result=asyncio.run(main.parse_swebsocket_message('{"action":"a_input","value":1}'))
            self.assertIn('disabled',result['error'])
            record.assert_not_awaited()
            self.assertEqual(asyncio.run(main.parse_swebsocket_message('{"action":"usr_key","value":"1"}')),{'profile':'generic'})
            self.assertIn('error',asyncio.run(main.parse_swebsocket_message('[]')))

    def test_http_health_and_disabled_providers(self):
        # No context manager: test HTTP routes without starting the real WS listener.
        with patch.dict(os.environ,{'AVATAR_ENABLE_PROVIDERS':'0'}):
            client=TestClient(main.app)
            self.assertFalse(client.get('/health').json()['providers_enabled'])
            self.assertEqual(client.post('/api/get_answer_async',json={'text':'Demo'}).status_code,503)
            self.assertEqual(client.post('/api/recognize_and_synthesize',content=b'audio').status_code,503)
            self.assertEqual(client.post('/api/set_anim_state',json={'anim_state':'unknown'}).status_code,422)
            self.assertEqual(client.post('/api/set_anim_state',json={'anim_state':'Talk'}).json(),{'anim_state':6})
            client.close()

if __name__=='__main__':unittest.main()

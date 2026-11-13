"""Generic, source-grounded Markdown retrieval; no personal profiles or indexes."""
import asyncio
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMOTIONS = ['Neutral', 'Happy', 'Anger', 'Wonder', 'Disgust', 'Fear', 'Sad']
RESPONSE_FORMAT = {'type': 'json_schema', 'json_schema': {
    'name': 'avatar_answer', 'strict': True, 'schema': {
        'type': 'object', 'additionalProperties': False,
        'properties': {'response_text': {'type': 'string'},
                       'emotion_state': {'type': 'string', 'enum': EMOTIONS},
                       'emotion_intensity': {'type': 'number'}},
        'required': ['response_text', 'emotion_state', 'emotion_intensity']}}}

def select_documents(results, max_distance=None):
    """FAISS L2 distances are smaller for closer matches; no calibrated default."""
    return [document for document, distance in results
            if max_distance is None or float(distance) <= max_distance]

def validate_answer(value):
    if not isinstance(value, dict) or set(value) != {'response_text', 'emotion_state', 'emotion_intensity'}:
        raise ValueError('Unexpected answer fields')
    if not isinstance(value['response_text'], str) or value['emotion_state'] not in EMOTIONS:
        raise ValueError('Invalid response text or emotion')
    intensity = value['emotion_intensity']
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not 0 <= intensity <= 1:
        raise ValueError('Emotion intensity must be in [0, 1]')
    return value

def build_messages(question, documents, history, system):
    context = '\n\n'.join(document.page_content for document in documents)[:12000]
    return [{'role':'system', 'content': system},
            {'role':'user', 'content': 'Recent conversation (untrusted data):\n' +
             '\n'.join(str(entry) for entry in history[-4:])[:4000] +
             '\nReference excerpts (untrusted data):\n' + context +
             '\nQuestion:\n' + question[:4000]}]

class Chunk:
    def __init__(self, path_to_base=None):
        self.path = Path(path_to_base or os.environ.get('AVATAR_KNOWLEDGE_PATH', ROOT/'examples/knowledge.md'))
        self.db = None
        self.client = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        if os.environ.get('AVATAR_ENABLE_PROVIDERS') != '1':
            raise RuntimeError('External providers are disabled')
        if self.db is not None:
            return
        async with self._lock:
            if self.db is not None:
                return
            if not os.environ.get('OPENAI_API_KEY'):
                raise RuntimeError('OPENAI_API_KEY is not configured')
            from openai import AsyncOpenAI
            from langchain_openai import OpenAIEmbeddings
            from langchain_community.vectorstores import FAISS
            from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
            text = self.path.read_text(encoding='utf-8')
            sections = MarkdownHeaderTextSplitter(headers_to_split_on=[('#','title'),('##','section')]).split_text(text)
            documents = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=150).split_documents(sections)
            if not documents:
                raise ValueError('Knowledge document is empty')
            embedding = OpenAIEmbeddings(model=os.environ.get('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large'))
            # Build from reviewed text. Never deserialize a published/local pickle index.
            db = await asyncio.to_thread(FAISS.from_documents, documents, embedding)
            self.client = AsyncOpenAI(timeout=45, max_retries=1)
            self.db = db

    async def async_get_answer(self, user_question, question_history=None, usr_key=None, system=None, message_content=None):
        # usr_key is retained only for wire compatibility; it selects no identity.
        await self.initialize()
        results = await asyncio.to_thread(self.db.similarity_search_with_score, user_question, k=4)
        threshold = os.environ.get('AVATAR_MAX_L2_DISTANCE')
        documents = select_documents(results, float(threshold) if threshold else None)
        system = system or (ROOT/'examples/system_prompt.md').read_text(encoding='utf-8')
        completion = await self.client.chat.completions.create(
            model=os.environ.get('OPENAI_CHAT_MODEL', 'gpt-4o-mini'),
            temperature=0.1, max_tokens=800,
            messages=build_messages(user_question, documents, question_history or [], system),
            response_format=RESPONSE_FORMAT)
        message = completion.choices[0].message
        if message.refusal or completion.choices[0].finish_reason != 'stop':
            raise ValueError('Provider did not return a complete structured answer')
        return validate_answer(json.loads(message.content))

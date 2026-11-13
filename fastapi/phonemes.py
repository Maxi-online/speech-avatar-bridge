"""Compatibility helpers for the historical character-to-avatar mapping.

These are character markers, not acoustic phoneme recognition or forced alignment.
"""
from protocol import character_timings

def text_to_phonemes(text):
    return character_timings(text, len(text) * 0.1)

def analyze_phonemes(audio_file_path):
    """Explicit optional Google recognition call; never invoked during import."""
    import os
    if os.environ.get('AVATAR_ENABLE_PROVIDERS') != '1':
        raise RuntimeError('External providers are disabled')
    import speech_recognition as sr
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_file_path) as source:
        audio = recognizer.record(source)
    return text_to_phonemes(recognizer.recognize_google(audio, language='ru-RU'))

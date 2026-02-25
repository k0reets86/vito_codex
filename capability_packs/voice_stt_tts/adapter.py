# Voice STT/TTS capability (stub)

def run(input_data: dict) -> dict:
    text = input_data.get("text")
    audio = input_data.get("audio")
    if not text and not audio:
        return {"status": "error", "error": "text_or_audio_required"}
    if text:
        return {"status": "ok", "output": {"audio_out": "generated", "text": text}}
    return {"status": "ok", "output": {"transcript": "unknown", "audio": "received"}}

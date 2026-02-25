# Voice streaming capability (stub)

def run(input_data: dict) -> dict:
    stream = input_data.get("audio_stream")
    if not stream:
        return {"status": "error", "error": "audio_stream_required"}
    return {"status": "ok", "output": {"partial_transcript": "...", "final_transcript": ""}}

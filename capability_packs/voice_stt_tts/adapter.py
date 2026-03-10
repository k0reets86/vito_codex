from modules.capability_pack_runtime import error_result, success_result


def run(input_data: dict) -> dict:
    if not input_data.get("text") and not input_data.get("audio"):
        return error_result("text_or_audio_required", capability="voice_stt_tts", missing=["text_or_audio"])
    language = str(input_data.get("language") or "auto")
    if input_data.get("text"):
        text = str(input_data.get("text") or "")
        return success_result(
            "voice_stt_tts",
            output={
                "text": text,
                "audio_out": "generated",
                "language": language,
                "mode": "tts",
            },
            evidence={"id": f"tts:{language}:{len(text)}"},
            next_actions=["stream_audio", "cache_voice_asset"],
            recovery_hints=["switch_voice_profile", "shorten_input_text"],
        )
    audio = str(input_data.get("audio") or "")
    return success_result(
        "voice_stt_tts",
        output={
            "transcript": str(input_data.get("transcript") or "transcription_pending_review"),
            "audio": audio,
            "language": language,
            "mode": "stt",
        },
        evidence={"id": f"stt:{language}"},
        next_actions=["review_transcript", "store_audio_fact"],
        recovery_hints=["retry_transcription", "switch_language_profile"],
    )

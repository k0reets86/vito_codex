from modules.capability_pack_runtime import error_result, missing_fields, success_result


def run(input_data: dict) -> dict:
    missing = missing_fields(input_data, ["audio_stream"])
    if missing:
        return error_result("audio_stream_required", capability="voice_streaming", missing=missing)
    lang = str(input_data.get("language") or "auto")
    return success_result(
        "voice_streaming",
        output={
            "partial_transcript": str(input_data.get("partial_transcript") or "stream_ready"),
            "final_transcript": str(input_data.get("final_transcript") or ""),
            "language": lang,
            "stream_state": "active",
        },
        evidence={"id": f"voice_stream:{lang}"},
        next_actions=["continue_stream", "flush_final_transcript"],
        recovery_hints=["reconnect_stream", "switch_language_to_auto"],
    )

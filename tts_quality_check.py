import asyncio
import json
from pathlib import Path

from voice_service import close_http_client, generate_tts_audio_bytes


async def main() -> int:
    cases_path = Path(__file__).with_name("tts_quality_cases.json")
    output_dir = Path(__file__).with_name("tts-quality-output")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    output_dir.mkdir(exist_ok=True)
    failures = 0

    try:
        for case in cases:
            audio = await generate_tts_audio_bytes(case["text"])
            if not audio:
                failures += 1
                print(f"FAIL {case['id']}")
                continue
            (output_dir / f"{case['id']}.mp3").write_bytes(audio)
            print(f"OK {case['id']} ({len(audio)} bytes)")
    finally:
        await close_http_client()

    print(f"Complete: {len(cases) - failures}/{len(cases)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

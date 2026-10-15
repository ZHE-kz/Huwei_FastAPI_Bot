import base64
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from voice_service import (
    MAX_AUDIO_BYTES,
    generate_tts_audio_bytes,
    get_audio_duration_ms,
    get_tts_cache_key,
    prepare_text_for_speech,
    split_text_gracefully,
    decode_audio_response,
)


class DecodeAudioResponseTests(unittest.TestCase):
    def test_accepts_valid_audio_base64(self):
        audio = b"a" * 256

        self.assertEqual(
            decode_audio_response({"audio_data": base64.b64encode(audio).decode()}),
            audio,
        )

    def test_rejects_invalid_payloads(self):
        invalid_payloads = [
            None,
            [],
            {},
            {"audio_data": 123},
            {"audio_data": "not-base64"},
            {"audio_data": base64.b64encode(b"small").decode()},
            {"audio_data": "A" * ((((MAX_AUDIO_BYTES + 2) // 3) * 4) + 1)},
        ]

        for payload in invalid_payloads:
            with self.subTest(payload_type=type(payload).__name__):
                self.assertIsNone(decode_audio_response(payload))

    def test_cache_key_is_stable_and_ignores_edge_whitespace(self):
        self.assertEqual(get_tts_cache_key(" 相同內容 "), get_tts_cache_key("相同內容"))
        self.assertNotEqual(get_tts_cache_key("內容 A"), get_tts_cache_key("內容 B"))

    @patch("mutagen.File")
    def test_reads_actual_audio_duration(self, mutagen_file):
        mutagen_file.return_value.info.length = 1.234
        self.assertEqual(get_audio_duration_ms(b"audio"), 1234)

    def test_prepares_display_text_for_natural_speech(self):
        text = "## 參觀 API\n2026-10-15 請看 [導覽](https://example.com) 🚀"
        self.assertEqual(
            prepare_text_for_speech(text),
            "參觀 應用程式介面。二零二六年十月十五日 請看 導覽",
        )

    def test_splits_only_at_complete_sentence_boundary(self):
        text = "第一句。第二句比較長。第三句。"
        current, remaining = split_text_gracefully(text, max_length=8)
        self.assertEqual(current, "第一句。")
        self.assertEqual(current + remaining, text)

    def test_long_single_sentence_is_not_cut_mid_sentence(self):
        text = "這是一個沒有中間標點的完整長句子。"
        self.assertEqual(split_text_gracefully(text, max_length=5), (text, ""))

    def test_fixed_archive_quality_corpus_has_10_to_20_cases(self):
        cases = json.loads(
            Path(__file__).with_name("tts_quality_cases.json").read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(cases), 10)
        self.assertLessEqual(len(cases), 20)
        for case in cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(prepare_text_for_speech(case["text"]))


class TtsRetryTests(unittest.TestCase):
    @patch.dict("os.environ", {"TTS_MODAL_URL": "https://tts.example.test"})
    @patch("builtins.print")
    @patch("voice_service.asyncio.sleep", new_callable=AsyncMock)
    @patch("voice_service.get_http_client")
    def test_retries_twice_for_retryable_status(self, get_client, sleep, _print):
        audio = b"a" * 256
        responses = []
        for status in (429, 503, 200):
            response = MagicMock(status_code=status)
            response.json.return_value = {
                "audio_data": base64.b64encode(audio).decode()
            }
            responses.append(response)
        get_client.return_value.post = AsyncMock(side_effect=responses)

        coroutine = generate_tts_audio_bytes("測試")
        try:
            while True:
                coroutine.send(None)
        except StopIteration as completed:
            result = completed.value

        self.assertEqual(result, audio)
        self.assertEqual(get_client.return_value.post.await_count, 3)
        self.assertEqual(sleep.await_count, 2)

    @patch.dict("os.environ", {"TTS_MODAL_URL": "https://tts.example.test"})
    @patch("builtins.print")
    @patch("voice_service.get_http_client")
    def test_modal_payload_includes_voice_options(self, get_client, _print):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "audio_data": base64.b64encode(b"a" * 256).decode()
        }
        get_client.return_value.post = AsyncMock(return_value=response)
        coroutine = generate_tts_audio_bytes(
            "**API** 🚀", speaker="huwei", speed=1.1, pitch=-1
        )
        try:
            while True:
                coroutine.send(None)
        except StopIteration as completed:
            self.assertIsNotNone(completed.value)

        payload = get_client.return_value.post.await_args.kwargs["json"]
        self.assertEqual(
            payload,
            {
                "text": "應用程式介面",
                "speaker": "huwei",
                "speed": 1.1,
                "pitch": -1,
            },
        )

if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preza_check_speech", ROOT / "skills/preza/scripts/check_speech.py"
)
check_speech = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_speech)


def speech(body):
    return f"## Слайд 1. А\n{body}\n"


def docx(path, body):
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(
            f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in body.split("\n")
        )
        + "</w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)


class SpeechTests(unittest.TestCase):
    def test_topic_words_pass_and_origin_phrases_warn(self):
        errors, warnings, _ = check_speech.check(
            speech("Объём информации о компании растёт."), 1, 1, 50
        )
        self.assertEqual((errors, warnings), ([], []))
        errors, warnings, _ = check_speech.check(
            speech("Рисунок сгенерирован нейросетью."), 1, 1, 50
        )
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 1)
        errors, _, _ = check_speech.check(
            speech("Рисунок сгенерирован нейросетью."), 1, 1, 50, strict=True
        )
        self.assertEqual(len(errors), 1)
        errors, warnings, _ = check_speech.check(
            speech("Рисунок сгенерирован нейросетью."),
            1,
            1,
            50,
            strict=True,
            allow="нейросет",
        )
        self.assertEqual((errors, warnings), ([], []))

    def test_word_dashes_and_yo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "speech.docx"
            docx(path, "Слайд 1. А\nЕщё один довод — рост.")
            text = speech("Ещё один довод — рост.")
            errors, warnings, _ = check_speech.check(text, 1, 1, 50, word=path)
            self.assertEqual((len(errors), len(warnings)), (0, 2))
            errors, _, _ = check_speech.check(text, 1, 1, 50, word=path, strict=True)
            self.assertEqual(len(errors), 2)

    def test_word_must_match_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "speech.docx"
            docx(
                path,
                "Текст выступления · около 1 минуты · 1 слайд\nСлайд 1. А\nДовод без конца",
            )
            head = "# Текст выступления · около 1 минуты · 1 слайд\n\n"
            errors, _, _ = check_speech.check(
                head + speech("Довод без конца. Вопрос?"), 1, 1, 50, word=path
            )
            self.assertEqual(errors, ["Word: слайд 1 не совпадает с речью"])

    def test_user_edits_in_word_header_and_titles_are_found(self):
        # сданный Word правили руками: ФИО, длительность и заголовок слайда — пересборка их не затрёт
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "speech.docx"
            docx(
                path,
                "Текст выступления · около 8 минут · 1 слайд\nИванов Иван, Петров Пётр\nСлайд 1. Новый заголовок\nДовод.",
            )
            text = "# Текст выступления · около 7 минут · 1 слайд\nИванов И.\n\n## Слайд 1. А\nДовод.\n"
            errors, _, _ = check_speech.check(text, 1, None, None, word=path)
            self.assertEqual(
                errors,
                [
                    "Word: шапка не совпадает с речью",
                    "Word: заголовок слайда 1 не совпадает с речью",
                ],
            )

    def test_words_accepts_target_or_range(self):
        self.assertEqual(check_speech.words_range("720-860"), (720, 860))
        self.assertEqual(check_speech.words_range("800"), (720, 880))
        with self.assertRaises(ValueError):
            check_speech.words_range("около 800")


if __name__ == "__main__":
    unittest.main()

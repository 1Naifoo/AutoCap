import unittest

from logic import should_capitalize, standalone_i, char_for_vk


class ShouldCapitalize(unittest.TestCase):
    def yes(self, before, start=False):
        self.assertTrue(should_capitalize(before, start), repr(before))

    def no(self, before, start=False):
        self.assertFalse(should_capitalize(before, start), repr(before))

    def test_field_start(self):
        self.yes("", True)
        self.yes("   ", True)
        self.no("", False)          # we don't know what's before -> leave it alone

    def test_sentence_end(self):
        self.yes("Hello. ")
        self.yes("Really? ")
        self.yes("Wow! ")
        self.yes("Done.  ")
        self.yes('He said "hi." ')
        self.yes("(see above.) ")

    def test_new_line(self):
        self.yes("Hello\n")
        self.yes("Hello\r")
        self.yes("Hello\n   ")

    def test_mid_sentence(self):
        self.no("hello ")
        self.no("hello, ")
        self.no("hello")

    def test_no_space_after_dot(self):
        self.no("google.")
        self.no("3.")
        self.no("file.")

    def test_abbreviations_and_ellipsis(self):
        self.no("for e.g. ")
        self.no("talk to Dr. ")
        self.no("wait... ")
        self.no("this vs. ")


class StandaloneI(unittest.TestCase):
    def test_cases(self):
        self.assertTrue(standalone_i("and i", False))
        self.assertTrue(standalone_i("i", True))
        self.assertTrue(standalone_i("Yes\ni", False))
        self.assertTrue(standalone_i("(i", False))
        self.assertFalse(standalone_i("i", False))
        self.assertFalse(standalone_i("hi", False))
        self.assertFalse(standalone_i("wiki", False))


class CharForVk(unittest.TestCase):
    def test_cases(self):
        self.assertEqual(char_for_vk(0xBE, False), ".")
        self.assertEqual(char_for_vk(0x31, True), "!")
        self.assertEqual(char_for_vk(0xBF, True), "?")
        self.assertEqual(char_for_vk(0x20, False), " ")
        self.assertEqual(char_for_vk(0xDE, False), "'")
        self.assertIsNone(char_for_vk(0x25, False))   # arrow key


if __name__ == "__main__":
    unittest.main()

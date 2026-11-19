"""Behaviour tests for the Menura engine. Run with: python -m unittest -v"""

import unittest

from menura import MenuraBot
from menura.engine import extract_items
from menura.formatting import to_markdown


class MenuraBotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = MenuraBot(seed=7)

    def assertTopic(self, query, topic, fuzzy=False):
        reply = self.bot.reply(query)
        self.assertEqual(reply.kind, "topic", f"{query!r} -> {reply}")
        self.assertEqual(reply.topic, topic)
        self.assertEqual(reply.fuzzy, fuzzy, f"{query!r} -> {reply}")

    def assertItem(self, query, item, fuzzy=False):
        reply = self.bot.reply(query)
        self.assertEqual(reply.kind, "item", f"{query!r} -> {reply}")
        self.assertEqual(reply.item, item)
        self.assertEqual(reply.fuzzy, fuzzy, f"{query!r} -> {reply}")
        self.assertIn(item, reply.text)

    def assertFallback(self, query):
        reply = self.bot.reply(query)
        self.assertEqual(reply.kind, "fallback", f"{query!r} -> {reply}")

    # Queries the original v1 bot already answered keep the same answers.
    def test_original_topics_still_match(self):
        cases = {
            "merhaba": "Merhaba",
            "kahveler": "Kahveler",
            "menü": "Menü",
            "burger var mı": "Burgerler",
            "tatlı ne var": "Tatlılar",
            "kahvaltı": "Kahvaltılar",
            "makarna": "Makarnalar",
            "milkshake istiyorum": "Milkshake",
            "ekmek arası ne var": "Ekmek Arası",
            "tost": "Tostlar",
        }
        for query, topic in cases.items():
            with self.subTest(query=query):
                self.assertTopic(query, topic)

    def test_synonyms_and_new_topics(self):
        cases = {
            "salatalar": "Salata",
            "neler var": "Menü",
            "kola": "Meşrubatlar",
            "soğuk içecekler": "Meşrubatlar",
            "sıcak içecek": "Kahveler",
            "pasta": "Tatlılar",
            "teşekkürler": "Teşekkürler",
            "sağ ol": "Teşekkürler",
            "görüşürüz": "Görüşürüz",
            "kaç para": "Fiyatlar",
            "hesap lütfen": "Hesap",
        }
        for query, topic in cases.items():
            with self.subTest(query=query):
                self.assertTopic(query, topic)

    def test_products_resolve_to_their_category(self):
        self.assertItem("latte var mı", "Latte")
        self.assertItem("künefe", "Künefe")
        self.assertItem("coca cola", "Coca-Cola")
        self.assertItem("sucuklu yumurta", "Sucuklu Yumurta")
        self.assertIn("Evet, Latte menümüzde var.", self.bot.reply("latte var mı").text)

    def test_partial_product_match_is_labelled_approximate(self):
        # "sıcak çikolata": only "çikolata" (a milkshake flavour) is a product, so the answer
        # must not claim the guest's exact request is on the menu.
        self.assertItem("sıcak çikolata", "Çikolata", fuzzy=True)
        self.assertIn("en yakın sonuç: Çikolata", self.bot.reply("sıcak çikolata").text)

    def test_typos_and_missing_turkish_letters(self):
        self.assertItem("magnolya", "Magnolia", fuzzy=True)
        self.assertItem("kapuçino", "Cappuccino", fuzzy=True)
        self.assertItem("espreso", "Espresso", fuzzy=True)
        self.assertItem("kunefe", "Künefe", fuzzy=True)
        self.assertItem("cay", "Bardak Çay", fuzzy=True)
        self.assertTopic("tatlilar", "Tatlılar", fuzzy=True)
        self.assertTopic("kahvalti", "Kahvaltılar", fuzzy=True)

    def test_unknown_questions_get_fallback(self):
        for query in ["uzaylı", "pizza", "wifi şifresi", "kebap", "lahmacun", "döner", "", "   ", "?!"]:
            with self.subTest(query=query):
                self.assertFallback(query)

    def test_recommendation_uses_real_menu_items(self):
        reply = self.bot.reply("ne önerirsin")
        self.assertEqual(reply.topic, "Ne önerirsin?")
        menu = self.bot.reply("menü").text
        picked = [item for item in extract_items(menu) if item in reply.text]
        self.assertGreaterEqual(len(picked), 3, reply.text)

    def test_answers_vary_but_stay_on_topic(self):
        greetings = {self.bot.reply("merhaba").text for _ in range(30)}
        self.assertGreater(len(greetings), 1)
        self.assertTrue(all(g in self.bot._by_topic["Merhaba"]["bot_response"] for g in greetings))

    def test_small_talk(self):
        cases = {"naber": "Nasılsın?", "nasılsın": "Nasılsın?", "iyiyim": "İyiyim", "kimsin": "Kimsin?",
                 "acıktım": "Acıktım", "selam": "Merhaba", "iyi günler": "Merhaba"}
        for query, topic in cases.items():
            with self.subTest(query=query):
                self.assertTopic(query, topic)

    def test_option_with_category_adds_note_and_list(self):
        reply = self.bot.reply("şekersiz kahve")
        self.assertEqual((reply.kind, reply.topic, reply.option), ("topic", "Kahveler", "şekersiz"))
        self.assertTrue(reply.text.startswith("Tüm kahvelerimizi şekersiz"))
        self.assertIn("Espresso", reply.text)

    def test_option_with_product(self):
        reply = self.bot.reply("ice latte")
        self.assertEqual((reply.kind, reply.item, reply.option), ("item", "Latte", "buzlu"))

    def test_option_follow_up_uses_last_topic(self):
        reply = self.bot.reply("şekersiz mi peki", last_topic="Meşrubatlar")
        self.assertEqual((reply.kind, reply.topic, reply.option), ("option", "Meşrubatlar", "şekersiz"))
        self.assertIn("Coca-Cola Zero", reply.text)
        reply = self.bot.reply("sütsüz olur mu", last_topic="Kahveler")
        self.assertIn("laktozsuz", reply.text)

    def test_option_without_context_uses_default(self):
        reply = self.bot.reply("vejetaryen ne var")
        self.assertEqual(reply.kind, "option")
        self.assertIn("Etsiz seçeneklerimiz", reply.text)

    def test_option_patterns_do_not_fire_inside_other_words(self):
        # "=ice" is a whole-word pattern, so "içecek" must not trigger the iced option.
        self.assertIsNone(self.bot.reply("soğuk içecekler").option)
        self.assertIsNone(self.bot.reply("acıktım").option)

    def test_invisible_characters_are_ignored(self):
        self.assertTopic("﻿merhaba", "Merhaba")
        self.assertTopic("Kahveler?!", "Kahveler")

    def test_get_response_is_backward_compatible(self):
        self.assertEqual(self.bot.get_response("kahveler"), self.bot.reply("kahveler").text)


class HelperTests(unittest.TestCase):
    def test_extract_items_skips_titles_and_notes(self):
        text = "\n ★★★ Burger Listesi ★★★ \n Cheeseburger\n\n【Not】\n"
        self.assertEqual(extract_items(text), ["Cheeseburger"])

    def test_markdown_formats_lists(self):
        md = to_markdown("\n ★★★ Tost Listesi ★★★ \n Kaşarlı Tost\n Karışık Tost\n")
        self.assertEqual(md, "**Tost Listesi**\n\n- Kaşarlı Tost\n- Karışık Tost")

    def test_markdown_keeps_sentences(self):
        self.assertEqual(to_markdown("Rica ederim!"), "Rica ederim!")

    def test_item_answer_intro_stays_a_sentence(self):
        reply = MenuraBot().reply("künefe")
        first_line = to_markdown(reply.text).splitlines()[0]
        self.assertEqual(first_line, "Evet, Künefe menümüzde var. Tatlılar listemiz aşağıda.")


if __name__ == "__main__":
    unittest.main()

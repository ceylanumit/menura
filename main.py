"""Menura terminal interface. Run with: python main.py"""

from menura import MenuraBot

BANNER = r"""
 __  __ _____ _   _ _   _ ____      _
|  \/  | ____| \ | | | | |  _ \    / \
| |\/| |  _| |  \| | | | | |_) |  / _ \
| |  | | |___| |\  | |_| |  _ <  / ___ \
|_|  |_|_____|_| \_|\___/|_| \_\/_/   \_\
"""

EXIT_WORDS = {"çıkış", "cikis", "exit", "quit", "q"}


def main() -> None:
    bot = MenuraBot()
    print(BANNER)
    print(bot.welcome)
    print("Çıkmak için 'çıkış' yazın.\n")
    last_topic = None  # remembered so follow-ups like "şekersiz mi peki?" know the category
    try:
        while True:
            text = input("Sen: ").strip()
            if text.lower() in EXIT_WORDS:
                break
            reply = bot.reply(text, last_topic=last_topic)
            if reply.topic in bot.categories:
                last_topic = reply.topic
            print(f"{bot.name}: {reply.text}\n")
    except (KeyboardInterrupt, EOFError):
        print()
    print("Görüşmek üzere!")


if __name__ == "__main__":
    main()

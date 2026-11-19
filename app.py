"""Menura web interface (Gradio Blocks). Run locally with: python app.py

This file is also the entry point for the Hugging Face Spaces demo.
"""

from html import escape
from pathlib import Path

import gradio as gr

from menura import MenuraBot, Reply
from menura.engine import extract_items
from menura.formatting import to_markdown

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
LOGO = ASSETS / "logo.svg"

gr.set_static_paths(paths=[ASSETS])
bot = MenuraBot()

QUICK_QUESTIONS = ["Naber?", "Ne önerirsin?", "Şekersiz kahve", "Magnolya", "Vejetaryen ne var?", "Acıktım"]


def image_url(topic: str | None) -> str | None:
    entry = bot._by_topic.get(topic or "")
    if not entry or "image" not in entry:
        return None
    return "/gradio_api/file=" + (ROOT / entry["image"]).as_posix()


def menu_grid() -> str:
    """The full menu as photo cards."""
    cards = []
    for topic in bot.categories:
        entry = bot._by_topic[topic]
        items = extract_items(entry["bot_response"])
        preview = ", ".join(items[:3]) + (f" +{len(items) - 3}" if len(items) > 3 else "")
        cards.append(
            f"<div class='menu-card'><img src='{image_url(topic)}' alt='{escape(topic)}'>"
            f"<div class='mc-body'><div class='mc-title'>{escape(topic)}</div>"
            f"<div class='mc-items'>{escape(preview)}</div></div></div>"
        )
    return ("<div class='menu-intro'>Tam menümüz aşağıda. Bir kategorinin tamamını görmek için adını yazmanız yeterli.</div>"
            "<div class='menu-grid'>" + "".join(cards) + "</div>")


def match_note(reply: Reply) -> str:
    """A small pill under menu answers that explains how the answer was found."""
    if reply.kind == "item":
        label = "Yaklaşık eşleşme" if reply.fuzzy else "Ürün"
        target = reply.item
    elif reply.kind == "topic" and reply.topic in bot.categories:
        label = "Yaklaşık eşleşme" if reply.fuzzy else "Kategori"
        target = reply.topic
    else:
        return ""
    option = f" · {reply.option}" if reply.option else ""
    return f"\n\n<span class='match-note'>{label}: {target}{option} · benzerlik {reply.score:.2f}</span>"


def render(reply: Reply) -> str:
    if reply.kind == "topic" and reply.topic == "Menü":
        return menu_grid()
    body = to_markdown(reply.text)
    url = image_url(reply.topic) if reply.kind in ("topic", "item") else None
    if url:
        body = f"<img class='cat-img' src='{url}' alt='{escape(reply.topic)}'>\n\n" + body
    return body + match_note(reply)


def answer(message: str, history: list, last_topic: str | None):
    message = (message or "").strip()
    if not message:
        return history, "", last_topic
    reply = bot.reply(message, last_topic=last_topic)
    if reply.topic in bot.categories:
        last_topic = reply.topic
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": render(reply)},
    ]
    return history, "", last_topic


def ask(question: str):
    return lambda history, last_topic: answer(question, history, last_topic)


HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script>
  // Menura is designed for the light palette; open it in light mode even on dark systems.
  (() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("__theme") !== "light") {
      url.searchParams.set("__theme", "light");
      window.location.replace(url.toString());
    }
  })();
</script>
"""

BRAND = """
<div class="brand">
  <div class="logo">M</div>
  <div>
    <h1>Menura</h1>
    <p>Türkçe menü asistanı</p>
  </div>
</div>
"""

WELCOME = """
<div class="welcome">
  <div class="welcome-title">Hoş geldiniz!</div>
  <div class="welcome-text">Menüdeki her şeyi sorabilirsiniz: “tatlı ne var?”, “latte var mı?”,
  “şekersiz olur mu?” ya da sadece “naber?”</div>
</div>
"""

FOOTER = """
<footer class="foot">Menura · Snowball kök bulma, TF-IDF ve kosinüs benzerliği ile çalışan bilgi erişim asistanı ·
<a href="https://github.com/ceylanumit/menura" target="_blank" rel="noopener">GitHub</a> ·
Fotoğraflar: <a href="https://unsplash.com" target="_blank" rel="noopener">Unsplash</a></footer>
"""

CSS = """
:root {
  --bg: #ffffff; --soft: #f6f7f8; --line: #e6e8eb; --ink: #0b0c0e; --text: #1f2328;
  --muted: #6b7280; --accent: #0e9f6e; --accent-ink: #08724f; --accent-soft: #e7f6ef;
}
body, .gradio-container, .main, .wrap, .contain { background: var(--bg) !important; }
.gradio-container {
  max-width: 920px !important; margin: 0 auto !important; padding: 24px 20px 8px !important;
  font-family: 'Inter', system-ui, sans-serif !important; color: var(--text);
}
footer:not(.foot) { display: none !important; }

/* Header */
#topbar { align-items: center !important; margin-bottom: 14px !important; gap: 10px !important; flex-wrap: nowrap !important; }
#chat .bubble-wrap { padding: 16px 18px !important; }
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  width: 44px; height: 44px; border-radius: 13px; background: var(--ink); color: #fff;
  display: grid; place-items: center; font-weight: 800; font-size: 22px;
}
.brand h1 { margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.4px; color: var(--ink); line-height: 1.1; }
.brand p { margin: 2px 0 0; color: var(--muted); font-size: 13.5px; }
#menu-btn {
  background: var(--ink) !important; color: #fff !important; border: none !important; border-radius: 12px !important;
  font-weight: 700 !important; font-size: 14px !important; padding: 10px 16px !important;
}
#clear-btn {
  background: #fff !important; color: var(--muted) !important; border: 1px solid var(--line) !important;
  border-radius: 12px !important; font-weight: 600 !important; font-size: 14px !important; box-shadow: none !important;
}

/* Chat */
#chat {
  background: #fff !important; border: 1px solid var(--line) !important; border-radius: 20px !important;
}
#chat .message-row { margin: 8px 0 !important; }
#chat .message.user {
  background: var(--ink) !important; color: #fff !important; border: none !important;
  border-radius: 18px 18px 4px 18px !important;
}
#chat .message.user * { color: #fff !important; }
#chat .message.bot {
  background: var(--soft) !important; border: 1px solid var(--line) !important; color: var(--text) !important;
  border-radius: 18px 18px 18px 4px !important; line-height: 1.6 !important; box-shadow: none !important;
  max-width: 88% !important;
}
#chat .message.bot strong { color: var(--ink); }
#chat ul { margin: 6px 0 4px !important; padding-left: 18px !important; }
#chat ul:has(li:nth-child(7)) { columns: 2; column-gap: 36px; }
#chat li { margin: 2px 0 !important; break-inside: avoid; }
#chat li::marker { color: var(--accent); }
#chat p { margin: 4px 0 !important; }
#chat img.cat-img {
  display: block; width: 100%; max-width: 520px; height: 170px; object-fit: cover;
  border-radius: 14px; margin: 2px 0 10px;
}
.match-note {
  display: inline-block; margin-top: 10px; font-size: 11.5px; font-weight: 600; color: var(--accent-ink);
  background: var(--accent-soft); padding: 3px 10px; border-radius: 999px;
}

/* Full menu grid */
.menu-intro { margin-bottom: 12px; }
.menu-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.menu-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.menu-card img { display: block; width: 100%; height: 96px; object-fit: cover; margin: 0 !important; border-radius: 0 !important; }
.mc-body { padding: 9px 11px 11px; }
.mc-title { font-weight: 700; color: var(--ink); font-size: 14px; }
.mc-items { color: var(--muted); font-size: 12px; line-height: 1.45; margin-top: 2px; }

.welcome { text-align: center; padding: 24px; }
.welcome-title { font-size: 22px; font-weight: 800; color: var(--ink); margin-bottom: 6px; }
.welcome-text { color: var(--muted); font-size: 15px; max-width: 480px; margin: 0 auto; line-height: 1.6; }

/* Composer */
#composer { margin-top: 12px !important; gap: 10px !important; align-items: stretch !important; }
#composer textarea {
  background: #fff !important; border: 1px solid var(--line) !important; border-radius: 14px !important;
  font-size: 15px !important; padding: 13px 16px !important; color: var(--text) !important;
}
#composer textarea:focus { border-color: var(--ink) !important; box-shadow: none !important; }
#send {
  background: var(--accent) !important; color: #fff !important; border: none !important; border-radius: 14px !important;
  font-weight: 700 !important; font-size: 15px !important;
}
#chips { margin-top: 10px !important; gap: 8px !important; flex-wrap: wrap !important; }
button.chip {
  background: #fff !important; border: 1px solid var(--line) !important; color: var(--text) !important;
  border-radius: 999px !important; font-size: 13px !important; font-weight: 600 !important;
  padding: 6px 14px !important; min-height: 0 !important; box-shadow: none !important;
}
button.chip:hover { border-color: var(--ink) !important; }
button.chip, #menu-btn, #clear-btn {
  flex: 0 0 auto !important; width: auto !important; min-width: max-content !important; white-space: nowrap !important;
}
#topbar > div:first-child { flex: 1 1 auto !important; }

.foot { text-align: center; color: var(--muted); font-size: 12px; margin: 16px 0 6px; line-height: 1.6; }
.foot a { color: var(--text); font-weight: 600; text-underline-offset: 3px; }

@media (max-width: 720px) {
  .menu-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  #chat ul:has(li:nth-child(7)) { columns: 1; }
  .gradio-container { padding: 14px 10px 6px !important; }
}
"""

with gr.Blocks(title="Menura · Türkçe menü asistanı") as demo:
    last_topic = gr.State(None)
    with gr.Row(elem_id="topbar"):
        gr.HTML(BRAND)
        menu_btn = gr.Button("Tam menüyü gör", elem_id="menu-btn", scale=0, min_width=0)
        clear_btn = gr.Button("Temizle", elem_id="clear-btn", scale=0, min_width=0)
    chatbot = gr.Chatbot(elem_id="chat", show_label=False, height="64vh", placeholder=WELCOME, buttons=[])
    with gr.Row(elem_id="composer"):
        msg = gr.Textbox(show_label=False, container=False, scale=8, autofocus=True,
                         placeholder="Bir şey sorun… örneğin “şekersiz latte var mı?”")
        send = gr.Button("Gönder", elem_id="send", scale=1, min_width=110)
    with gr.Row(elem_id="chips"):
        chips = [(gr.Button(q, elem_classes=["chip"], size="sm", scale=0, min_width=0), q) for q in QUICK_QUESTIONS]
    gr.HTML(FOOTER)

    io = dict(inputs=[msg, chatbot, last_topic], outputs=[chatbot, msg, last_topic])
    msg.submit(answer, **io)
    send.click(answer, **io)
    menu_btn.click(ask("Menü"), [chatbot, last_topic], [chatbot, msg, last_topic])
    for button, question in chips:
        button.click(ask(question), [chatbot, last_topic], [chatbot, msg, last_topic])
    clear_btn.click(lambda: ([], "", None), None, [chatbot, msg, last_topic])

if __name__ == "__main__":
    demo.launch(
        theme=gr.themes.Base(font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"]),
        css=CSS,
        head=HEAD,
        favicon_path=str(LOGO),
    )

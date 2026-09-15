"""
Keep-alive / health-check web server لأغراض Render فقط.
================================================================

لا علاقة لهذا الملف بمنطق Discord Bot أو الأوامر أو الـ extensions
(مثل bot4.py) — مستقل تمامًا. غرضه الوحيد هو تلبية شرط Render بأن يستمع
الـ Web Service على بورت، حتى لا يعتبر الخدمة "غير صحية" ويعيد تشغيلها.

لماذا لا نستخدم gunicorn هنا مباشرة كـ Start Command؟
------------------------------------------------------
النمط الشائع لاستضافة Discord Bot + health-check في خدمة Render واحدة هو:
    - discord bot يعمل بشكل Blocking في الـ Thread الرئيسي عبر bot.run(...)
    - Flask يعمل في Thread منفصل (Background Thread) فقط عشان يفتح بورت.

لو خلّينا Render يشغّل "gunicorn keep_alive:app" كـ Start Command، فسيصبح
gunicorn هو العملية الرئيسية، ولن يبدأ تشغيل البوت نفسه إطلاقًا (لأن أحد
لا يستدعي bot.run() في هذا السيناريو). لتجنّب تغيير طريقة تشغيل البوت
كليًا، نستخدم بدلاً من ذلك waitress: سيرفر WSGI إنتاجي حقيقي (وليس
Development Server)، لكنه Pure-Python ويعمل بشكل طبيعي داخل Thread عادي
تمامًا مثل app.run() القديم — بدون أي تغيير في بنية تشغيل البوت.

هذا يزيل تحذير:
    WARNING: This is a development server. Do not use it in a production
    deployment. Use a production WSGI server instead.
من اللوق نهائيًا، دون المساس بنظام الـ Discord Bot.

طريقة الدمج مع main.py الحالي عندك
-----------------------------------
إذا كان عندك حاليًا شيء يشبه هذا (النمط الشائع):

    from keep_alive import keep_alive
    keep_alive()
    bot.run(DISCORD_TOKEN)

فقط استبدل ملف keep_alive.py القديم بهذا الملف — التوقيع نفسه
(دالة keep_alive() تُستدعى مرة واحدة قبل bot.run()) بقي كما هو، فلا حاجة
لتعديل أي سطر آخر في main.py.

إن كان اسم الدالة أو الملف عندك مختلف، فقط أخبرني باسمه الحالي
واستدعاءه في main.py حتى أطابق التوقيع بالضبط بدل الافتراض.
"""

from __future__ import annotations

import os
import threading

from flask import Flask

app = Flask(__name__)


@app.route("/")
def health_check():
    return "OK", 200


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


def _run_production_server() -> None:
    # waitress بدل app.run(): سيرفر WSGI إنتاجي حقيقي، يعمل داخل Thread
    # عادي بدون الحاجة لإعادة هيكلة طريقة تشغيل البوت.
    from waitress import serve

    port = int(os.getenv("PORT", "8080"))
    serve(app, host="0.0.0.0", port=port)


def keep_alive() -> None:
    """يشغّل سيرفر الـ health-check في Thread منفصل، بدون حجب البوت."""
    thread = threading.Thread(target=_run_production_server, daemon=True)
    thread.start()


# ----------------------------------------------------------------------
# بديل: لو تفضّل تشغيل Flask عبر gunicorn فعليًا (Start Command منفصل)
# ----------------------------------------------------------------------
# هذا مناسب فقط لو صار عندك خدمتان منفصلتان على Render:
#   1) Background Worker لتشغيل البوت (bot.run() بشكل طبيعي).
#   2) Web Service منفصل لهذا الملف فقط، بـ Start Command:
#        gunicorn keep_alive:app --bind 0.0.0.0:$PORT --workers 1 --threads 4
# في هذه الحالة لا تستدعي keep_alive() إطلاقًا من داخل البوت؛ gunicorn
# نفسه هو من يستورد "app" ويشغّله. أخبرني إذا كان هذا هو الترتيب الذي
# تريده وسأرسل لك Start Command / render.yaml مضبوطة على هذا الأساس.

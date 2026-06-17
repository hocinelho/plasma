"""PA-55 — Joke skill: "tell me a joke" / "erzähl mir einen Witz"."""
from __future__ import annotations
import random

META = {
    "name": "joke",
    "description": "Tells a random short joke in English or German.",
    "triggers": [
        "tell me a joke",
        "say a joke",
        "give me a joke",
        "make me laugh",
        "tell a joke",
        "joke",
        "erzähl mir einen witz",
        "sag mir einen witz",
        "mach mich lachen",
        "witz",
        "احك لي نكتة",
        "قل لي نكتة",
        "نكتة",
        "أضحكني",
    ],
}

_JOKES_EN = [
    "Why don't scientists trust atoms? Because they make up everything.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call a fake noodle? An impasta.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "I'm reading a book about anti-gravity. It's impossible to put down.",
    "What do you call cheese that isn't yours? Nacho cheese.",
    "Why can't you give Elsa a balloon? Because she'll let it go.",
    "I used to hate facial hair, but then it grew on me.",
    "What do you call a sleeping dinosaur? A dino-snore.",
    "Why did the bicycle fall over? Because it was two-tired.",
    "What do you call a bear with no teeth? A gummy bear.",
    "I only know 25 letters of the alphabet. I don't know why.",
    "What do you call a fish without eyes? A fsh.",
    "Why do cows wear bells? Because their horns don't work.",
    "I asked my dog what two minus two is. He said nothing.",
]

_JOKES_DE = [
    "Warum nehmen Taucher immer rückwärts vom Boot ins Wasser? Weil sie sonst ins Boot fallen würden.",
    "Was sagt ein Clown zu einem anderen? Ich finde deinen Job zum Lachen.",
    "Ich habe heute meinen Hausarzt angerufen. Er war nicht da. Seine Praxis auch nicht.",
    "Was ist der Unterschied zwischen einem Snowboard und einem Skateboard? Das Snowboard.",
    "Wie nennt man einen Bumerang, der nicht zurückkommt? Stock.",
    "Was macht ein Pirat am Computer? Er drückt die Entertaste.",
    "Ich wollte eigentlich einen Witz über Butter machen, aber ich schmiere ihn lieber.",
    "Was ist grün und steht vor der Tür? Ein Klopfsalat.",
    "Warum hat der Maler die Schule abgebrochen? Er konnte sich nicht konzentrieren.",
    "Ich habe gerade ein Buch über Stockholm-Syndrom gelesen. Anfangs hasste ich es, aber am Ende mochte ich es.",
]


_JOKES_AR = [
    "ما الشيء الذي يمكنك إمساكه بيدك اليسرى ولا تستطيع إمساكه بيدك اليمنى؟ يدك اليمنى!",
    "لماذا لا تثق بالذرة؟ لأنها تخترع كل شيء!",
    "ما الفرق بين القطار والمعلم؟ القطار يقول توووت والمعلم يقول اهدأوا!",
    "كيف تعرف أن الفيل كان في ثلاجتك؟ بصماته في الزبدة!",
    "لماذا النجوم لا تذهب للمدرسة؟ لأنها بالفعل نجوم!",
    "ما هو أبرد حرف في الأبجدية؟ حرف الثلج — لا وجود له لكنه بارد!",
    "كم مبرمجاً يلزم لتغيير لمبة؟ لا أحد، هذه مشكلة مستخدم!",
]


def run(args: dict | None = None) -> str:
    language = (args or {}).get("language", "en")
    if language == "de":
        return random.choice(_JOKES_DE)
    if language == "ar":
        return random.choice(_JOKES_AR)
    return random.choice(_JOKES_EN)


def self_test() -> bool:
    return isinstance(run({}), str) and len(run({})) > 10

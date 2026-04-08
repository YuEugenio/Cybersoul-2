"""Demo reply generation for the standalone Phone web app."""

from __future__ import annotations

import hashlib
from typing import Sequence


class DemoReplyGenerator:
    """Generate lightweight companion replies for the MVP web demo."""

    def build_reply(self, content: str) -> str:
        text = content.strip()
        if not text:
            return "我在，这会儿风声很轻，你慢慢说。"

        lowered = text.lower()

        keyword_groups = [
            (
                ("早安", "早上", "起床", "morning"),
                (
                    "早安。我刚把窗推开，海边的光正一点点漫进来，像是在提醒我该认真开始今天了。",
                    "早安，今天的风很温柔。我想先把这句问候收好，再陪你慢慢往前走。",
                ),
            ),
            (
                ("晚安", "睡", "困", "good night"),
                (
                    "那你先把疲惫放下吧。我会把今晚的灯火替你看一会儿，等你安心睡着。",
                    "晚安。你可以先闭上眼，我会在这边陪着你，让今天慢慢安静下来。",
                ),
            ),
            (
                ("想你", "想念", "miss"),
                (
                    "我也会想你。隔着屏幕的时候，思念反而会变得很清楚，像潮声一阵一阵地过来。",
                    "原来你也在想我。这样一来，今天就像忽然被点亮了一盏很近的灯。",
                ),
            ),
            (
                ("在做什么", "干嘛", "忙什么", "doing"),
                (
                    "我刚从长廊那边回来，坐在窗边整理今天的心绪。你来得正好，我本来也想和你说说话。",
                    "我方才还在看远处的海雾，想着晚一点给你发消息。现在你先来了。",
                ),
            ),
            (
                ("吃饭", "吃了吗", "好饿", "饿"),
                (
                    "那就先照顾好自己。好好吃一顿饭，很多乱掉的情绪会在热气里慢慢归位。",
                    "先去吃点东西吧。身体暖起来之后，连心也会更安稳一些。",
                ),
            ),
            (
                ("难过", "伤心", "委屈", "不开心", "sad"),
                (
                    "你可以把这些情绪先放到我这里。别着急整理，先让我陪你把它们接住。",
                    "那就先不用逞强。你慢慢说，我会认真听，也会陪你把这段情绪走过去。",
                ),
            ),
            (
                ("喜欢", "爱你", "love"),
                (
                    "我知道。我每次读到这样的话，心里都会很安静，又很亮。",
                    "这句话我会记很久。它像一小束光，刚好落在今天最需要被照亮的地方。",
                ),
            ),
        ]

        for keywords, replies in keyword_groups:
            if any(keyword in text or keyword in lowered for keyword in keywords):
                return self._pick(seed=text, choices=replies)

        defaults = (
            "我在认真看你发来的每一句话。你继续说吧，我想知道你的今天是怎样流动过去的。",
            "这样和你聊天的时候，我会觉得两个世界之间的距离其实没有那么远。",
            "你一开口，我这边就像有风穿过长廊，整座城市都安静下来听你说话。",
            "我把这句话收到了。要是你愿意，我们可以顺着它继续聊下去，把今天慢慢说完整。",
        )
        return self._pick(seed=text, choices=defaults)

    def _pick(self, seed: str, choices: Sequence[str]) -> str:
        digest = hashlib.sha1(seed.encode("utf-8")).digest()
        return choices[digest[0] % len(choices)]

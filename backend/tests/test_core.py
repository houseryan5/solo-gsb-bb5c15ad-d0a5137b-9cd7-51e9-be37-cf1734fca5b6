"""核心逻辑自测：python3 backend/tests/test_core.py"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.aligner import align_tokens
from app.analyzer import build_comparison
from app.srt_parser import format_ms, parse_srt
from app.tokenizer import tokenize

PASS = 0


def check(name, cond):
    global PASS
    assert cond, f'FAIL: {name}'
    PASS += 1
    print(f'  ok - {name}')


def types_of(result):
    return sorted(i['type'] for i in result['issues'])


# ---- 切词与归一化 ---------------------------------------------------------
toks = [t.text for t in tokenize('Hello, 世界！  HELLO　ＡＢＣ，１２３')]
check('标点/空白被忽略，大小写与全半角归一', toks == ['hello', '世', '界', 'hello', 'abc', '123'])

# ---- SRT 解析 -------------------------------------------------------------
cues = parse_srt(
    '1\n00:00:01,000 --> 00:00:02,500\n<i>你好</i>\n世界\n\n'
    '2\n00:00:03.000 --> 00:00:04.000\n第二行\n')
check('SRT 解析块数', len(cues) == 2)
check('SRT 时间码解析', cues[0].start_ms == 1000 and cues[0].end_ms == 2500)
check('SRT 样式标签清除', cues[0].text == '你好\n世界')
check('时间码格式化', format_ms(3723456) == '01:02:03,456')

# ---- 对齐 -----------------------------------------------------------------
ops = align_tokens(list('今天天气很好'), list('今天天气很好'))
check('完全一致 -> 全部 eq', all(o.kind == 'eq' for o in ops))

ops = align_tokens(list('天气非常'), list('非常天气'))
kinds = [o.kind for o in ops]
check('交换顺序 -> 非全 eq', any(k != 'eq' for k in kinds))

# ---- 换行差异不产生误报（核心诉求） ---------------------------------------
script = '人工智能正在改变我们的世界，从手机到汽车，无处不在。'
srt = ('1\n00:00:01,000 --> 00:00:03,000\n人工智能\n正在改变我们的世界，\n\n'
       '2\n00:00:03,000 --> 00:00:05,000\n从手机到汽车，\n无处不在。\n')
res = build_comparison(parse_srt(srt), script)
check('换行/分块差异零误报', res['issues'] == [])

# ---- 缺词 -----------------------------------------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:03,000\n人工智能正在改变世界。\n'),
    '人工智能正在改变我们的世界。')
check('缺词被识别', types_of(res) == ['missing'])
check('缺词内容正确', res['issues'][0]['script_tokens'] == ['我', '们', '的'])
check('缺词带时间码', res['issues'][0]['timecode'] == '00:00:01,000 --> 00:00:03,000')

# ---- 多词 -----------------------------------------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:03,000\n感谢收看，我们下期节目再见。\n'),
    '感谢收看，我们下期再见。')
check('多词被识别', types_of(res) == ['extra'])
check('多词内容正确', ''.join(res['issues'][0]['subtitle_tokens']) == '节目')

# ---- 错序 -----------------------------------------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:03,000\n首先让我们看看家居智能。\n'),
    '首先让我们看看智能家居。')
check('错序被识别', types_of(res) == ['misorder'])

# ---- 错词（替换） ----------------------------------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:03,000\n科技让生活更美妙。\n'),
    '科技让生活更美好。')
check('错词被识别', types_of(res) == ['replace'])

# ---- 跨字幕块的连续差异只报一次（防级联） ----------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:02,000\n今天天气非常\n\n'
    '2\n00:00:02,000 --> 00:00:03,000\n不错。\n'),
    '今天非常天气不错。')
check('跨块错序归并为一条', types_of(res) == ['misorder'])

# ---- 混合场景 --------------------------------------------------------------
res = build_comparison(parse_srt(
    '1\n00:00:01,000 --> 00:00:02,000\n各位观众朋友晚上好。\n\n'
    '2\n00:00:02,000 --> 00:00:03,000\n今天聊聊智能的家居。\n\n'
    '3\n00:00:03,000 --> 00:00:04,000\n当你回家，灯光自动亮起。\n\n'
    '4\n00:00:04,000 --> 00:00:05,000\n科技让生活更美妙，感谢收看。\n'),
    '各位观众朋友晚上好。今天聊聊智能家居。当你下班回家时，灯光自动亮起。'
    '科技让生活更美好，感谢收看。')
check('混合场景识别 多词+缺词+错词', types_of(res) == ['extra', 'missing', 'replace'])

print(f'\n全部 {PASS} 项断言通过')

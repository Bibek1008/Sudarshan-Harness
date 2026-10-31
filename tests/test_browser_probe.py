"""Real Chromium fixture observations; not generated product acceptance."""
import tempfile
import unittest
from pathlib import Path

from demos.browser_probe import ChromiumProbe, browser_capability_preflight


class BrowserProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capability = browser_capability_preflight()
        if not capability.available:
            raise unittest.SkipTest(capability.reason)
        cls.browser = capability.executable

    def probe(self, config):
        return ChromiumProbe(config, executable=self.browser)

    def setUp(self):
        Path('work').mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=Path('work').resolve())
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_coffee_controls_and_visibility_at_three_widths(self):
        (self.root / 'hide.css').write_text('.external{display:none}')
        source = '''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="hide.css"></head><body><section>real copy</section><svg></svg>
<section class="external">hidden copy<svg></svg></section>
<span style="opacity:0.0">hidden</span><span style="filter:opacity(0)">hidden</span>
<button id="billing" onclick="price.textContent='annual'">Billing</button><p id="price">monthly</p>
<button id="brew" onclick="guide.textContent='new brew'">Brew</button><p id="guide">old brew</p>
<button id="faq" onclick="answer.hidden=!answer.hidden">FAQ</button><p id="answer" hidden>answer</p>
<button id="dark" onclick="document.documentElement.dataset.theme='dark';localStorage.setItem('theme','dark')">Dark</button>
<script>document.documentElement.dataset.theme=localStorage.getItem('theme')||'light';</script></body></html>'''
        index = self.root / 'index.html'
        index.write_text(source)
        probe = self.probe({'product': 'artisan-coffee', 'interactions': {
            'subscription_toggle': {'button': '#billing', 'target': '#price'},
            'brew_tabs': {'button': '#brew', 'target': '#guide'},
            'faq': {'button': '#faq', 'target': '#answer', 'attribute': 'hidden'},
            'dark': {'button': '#dark', 'target': 'html', 'attribute': 'data-theme'}},
            'dark': {'key': 'theme', 'target': 'html', 'attribute': 'data-theme'}})
        for width in (360, 768, 1280):
            with self.subTest(width=width):
                result = probe(index, width)
                self.assertEqual(result['viewport'], width)
                self.assertEqual(result['sections'], 1)
                self.assertEqual(result['svgs'], 1)
                self.assertEqual(set(result['checks']), {'subscription_toggle', 'brew_tabs', 'faq', 'dark', 'dark_persistence'})
                self.assertTrue(all(result['checks'].values()), result)

    def test_viper_real_key_events_and_persistence(self):
        index = self.root / 'index.html'
        index.write_text('''<!doctype html><body><canvas></canvas><button id="restart" onclick="state.score=0;state.paused=false">Restart</button>
<script>let state={head:{x:0,y:0},foods:0,score:0,interval:200,paused:false,highScore:Number(localStorage.getItem('best')||0)};
window.snapshot=()=>JSON.parse(JSON.stringify(state));
document.addEventListener('keydown',e=>{if(e.key==='p'){state.paused=!state.paused;return;}
if(e.key==='ArrowRight'&&!state.paused){state.head.x++;state.foods++;state.score++;
if(state.foods%5===0)state.interval-=20;state.highScore=Math.max(state.highScore,state.score);localStorage.setItem('best',state.highScore);}});
</script></body>''')
        result = self.probe({'product':'viper', 'snapshot':'window.snapshot()',
                                'food_keys':['ArrowRight']*5, 'step_ms':100,
                                'restart':'#restart'})(index, 768)
        self.assertEqual(len(result['checks']), 6)
        self.assertTrue(all(result['checks'].values()), result)

    def test_missing_keyboard_behavior_is_not_a_pass(self):
        index = self.root / 'index.html'
        index.write_text('''<canvas></canvas><button id="restart">Restart</button><script>
window.snapshot=()=>({head:{x:0,y:0},foods:0,score:0,interval:200,paused:false,highScore:0});
</script>''')
        result = self.probe({'product':'viper', 'snapshot':'window.snapshot()',
                                'food_keys':['ArrowRight']*5, 'step_ms':50,
                                'restart':'#restart'})(index, 768)
        self.assertFalse(result['checks']['keyboard_movement'])
        self.assertFalse(result['checks']['food_collection'])
        self.assertFalse(result['checks']['speed_change'])
        self.assertFalse(result['checks']['pause'])
        self.assertFalse(result['checks']['high_score_persistence'])

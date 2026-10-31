"""Trusted Chromium probe using only Python's standard library.

Runs real page JS with browser sandbox enabled, localhost-only HTTP and a fresh
profile. Selector/state mappings are independently supplied by the reviewer.
This is opt-in execution of product code, not an OS sandbox for hostile pages.
"""
import functools
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from html import unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sudarshan.environment import safe_shell_environment


def browser_executable():
    for name in ('chromium', 'google-chrome', 'chrome', 'msedge'):
        found = shutil.which(name)
        if found:
            return found
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        for suffix in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
            candidate = Path(os.environ.get(variable, '/nonexistent')) / suffix
            if candidate.is_file():
                return str(candidate)
    return None


SCRIPT = r'''
(async () => {
 if (location.search.includes('passive=1')) return;
 const cfg = CONFIG;
 const checks = {};
 const wait = ms => new Promise(r => setTimeout(r, ms));
 const assert = (name, value) => { checks[name] = !!value; };
 const visible = el => {
   for (let p=el; p; p=p.parentElement) {
     const s=getComputedStyle(p);
     if (p.hidden || p.getAttribute('aria-hidden')==='true' || s.display==='none' ||
         ['hidden','collapse'].includes(s.visibility) || Number(s.opacity)===0 ||
         /opacity\(0(?:\.0*)?\)/.test(s.filter) || s.clipPath!=='none' ||
         (s.clip && s.clip!=='auto')) return false;
   }
   const r=el.getBoundingClientRect();
   return r.width>1 && r.height>1;
 };
 const reloadFrame = async () => {
   const f=document.createElement('iframe');
   f.src=location.pathname+'?passive=1';
   await new Promise((resolve,reject) => {f.onload=resolve; f.onerror=reject; document.body.append(f);});
   return f;
 };
 try {
   await wait(150);
   const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
   let text='', n;
   while(n=walker.nextNode()) {
     if (!n.parentElement.closest('script,style,template,noscript') && visible(n.parentElement)) text+=' '+n.textContent;
   }
   const result={words:(text.match(/[\p{L}\p{N}_'-]+/gu)||[]).length,
     sections:[...document.querySelectorAll('section')].filter(visible).length,
     svgs:[...document.querySelectorAll('svg')].filter(visible).length,
     viewport:innerWidth, checks};
   if(cfg.product==='artisan-coffee') {
     for(const [name,spec] of Object.entries(cfg.interactions||{})) {
       const button=document.querySelector(spec.button), target=document.querySelector(spec.target);
       if(!button || !target) {assert(name,false);continue;}
       const read=()=>spec.attribute ? target.getAttribute(spec.attribute) : target.textContent;
       const before=read(); button.click(); await wait(50);
       assert(name,read()!==before);
     }
     if(cfg.dark) {
       const value=localStorage.getItem(cfg.dark.key);
       const frame=await reloadFrame();
       assert('dark_persistence', value!==null && frame.contentWindow.localStorage.getItem(cfg.dark.key)===value &&
         frame.contentDocument.querySelector(cfg.dark.target).getAttribute(cfg.dark.attribute)===
         document.querySelector(cfg.dark.target).getAttribute(cfg.dark.attribute));
       frame.remove();
     }
   }
   if(cfg.product==='viper') {
     const snapshot=(win=window)=>win.Function('return ('+cfg.snapshot+')')();
     const key=async k=>{document.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true}));await wait(cfg.step_ms||150);};
     const start=snapshot();
     await key(cfg.move_key||'ArrowRight');
     const moved=snapshot();
     assert('keyboard_movement',JSON.stringify(start.head)!==JSON.stringify(moved.head));
     for(const k of cfg.food_keys||[]) await key(k);
     const fed=snapshot();
     assert('food_collection',fed.foods>start.foods && fed.score>start.score);
     assert('speed_change',fed.foods>=5 && fed.interval<start.interval);
     await key(cfg.pause_key||'p'); const paused=snapshot();
     await wait(2*(cfg.step_ms||150));
     assert('pause',paused.paused===true && JSON.stringify(paused.head)===JSON.stringify(snapshot().head));
     const best=fed.highScore;
     document.querySelector(cfg.restart).click();await wait(50);
     assert('restart',snapshot().score===0 && snapshot().paused===false);
     const frame=await reloadFrame();
     assert('high_score_persistence',best>0 && snapshot(frame.contentWindow).highScore>=best);
     frame.remove();
   }
   const output=document.createElement('pre');output.id='sudarshan-probe-result';
   output.textContent=JSON.stringify(result);document.body.append(output);
   parent.postMessage(result,location.origin);
 } catch(error) {
   const output=document.createElement('pre');output.id='sudarshan-probe-result';
   output.textContent=JSON.stringify({error:String(error),checks});document.body.append(output);
   parent.postMessage({error:String(error),checks},location.origin);
 }
})();
'''


class ChromiumProbe:
    def __init__(self, config, executable=None):
        self.config = config
        self.executable = executable or browser_executable()
        if not self.executable:
            raise RuntimeError('No Chromium runtime available; manual verification remains required')

    def __call__(self, index_path, width):
        index_path = Path(index_path).resolve()
        script = SCRIPT.replace('CONFIG', json.dumps(self.config).replace('<', '\\u003c'), 1)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                try:
                    (index_path.parent / unquote(urlsplit(self.path).path).lstrip('/')).resolve().relative_to(index_path.parent)
                except ValueError:
                    self.send_error(403)
                    return
                if self.path == '/runner':
                    body = (f'<iframe id="product" src="/index.html?probe=1" style="border:0;width:{int(width)}px;height:900px"></iframe>'
                            '<script>addEventListener("message", e=>{if(e.source!==product.contentWindow)return;'
                            'const p=document.createElement("pre");p.id="sudarshan-probe-result";'
                            'p.textContent=JSON.stringify(e.data);document.body.append(p);});</script>').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path.split('?', 1)[0] == '/index.html':
                    source = index_path.read_text(encoding='utf-8')
                    body = (source + '<script>' + script + '</script>').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    super().do_GET()
        server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(index_path.parent)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        parent = Path('work').resolve()
        parent.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=parent) as profile:
                completed = subprocess.run([
                    self.executable, '--headless', '--disable-gpu', '--no-first-run',
                    '--no-default-browser-check', '--disable-background-networking',
                    '--no-proxy-server',
                    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
                    '--user-data-dir='+profile, f'--window-size={width},900',
                    '--hide-scrollbars', '--force-device-scale-factor=1',
                    '--virtual-time-budget=8000', '--dump-dom',
                    f'http://127.0.0.1:{server.server_port}/runner'],
                    env=safe_shell_environment(), capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=40)
                match = re.search(r'<pre id="sudarshan-probe-result">(.*?)</pre>', completed.stdout, re.S)
                if completed.returncode or not match:
                    raise ValueError('Chromium probe failed to produce observations')
                result = json.loads(unescape(match[1]))
                if 'error' in result:
                    raise ValueError('Browser scenario failed: ' + result['error'])
                if result.get('viewport') != width:
                    raise ValueError('Browser viewport did not match the requested width')
                result['runtime'] = 'Chromium headless'
                return result
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

"""Scripted model outputs for deterministic tests, NOT model-performance evidence."""
SOURCES = {
"slug": {"solution.py": "def slugify(text):\n    return '-'.join(text.lower().split())\n"},
"ledger": {"storage.py": "import json\nfrom pathlib import Path\ndef save(path, items): Path(path).write_text(json.dumps(items), encoding='utf-8')\ndef load(path):\n    path=Path(path)\n    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []\n", "app.py": "from storage import load\ndef total(path): return sum(load(path))\n"},
"median": {"solution.py": "def median(values):\n    if not values: raise ValueError('empty')\n    ordered=sorted(values); n=len(ordered)\n    return ordered[n//2] if n%2 else (ordered[n//2-1]+ordered[n//2])/2\n"},
"tests": {"test_solution.py": "import unittest\nfrom solution import clamp\nclass Clamp(unittest.TestCase):\n    def test_low(self): self.assertEqual(clamp(-1,0,10),0)\n    def test_mid(self): self.assertEqual(clamp(5,0,10),5)\n    def test_high(self): self.assertEqual(clamp(20,0,10),10)\n    def test_reverse(self):\n        with self.assertRaises(ValueError): clamp(1,10,0)\n"},
"ranges": {"solution.py": "def parse_range(text):\n    parts=text.split(':')\n    if len(parts)!=2: raise ValueError('format')\n    a,b=map(int,parts)\n    if a>b: raise ValueError('descending')\n    return list(range(a,b+1))\n"},
"port": {"solution.py": "import re\ndef parse_port(value):\n    if type(value) is int: number=value\n    elif isinstance(value,str) and re.fullmatch(r'[0-9]+',value): number=int(value)\n    else: raise ValueError('type')\n    if not 1<=number<=65535: raise ValueError('range')\n    return number\n"},
"config": {"settings.py": "import json\ndef load_config(text):\n    value=json.loads(text)\n    if not isinstance(value,dict) or not isinstance(value.get('name'),str) or not value['name'].strip(): raise ValueError('name')\n    retries=value.get('retries',3)\n    if type(retries) is not int or not 0<=retries<=5: raise ValueError('retries')\n    return {'name':value['name'],'retries':retries}\n"},
"orders": {"orders.py": "def total(items, member=False):\n    subtotal=sum(price*quantity for price,quantity in items)\n    return subtotal * 0.9 if member else subtotal\n"},
"unique": {"solution.py": "def unique(values):\n    result=[]\n    for value in values:\n        if value not in result: result.append(value)\n    return result\n"},
"csv": {"parse.py": "def parse_csv(text):\n    if not text.strip(): return []\n    return [int(value.strip()) for value in text.split(',')]\n", "stats.py": "from parse import parse_csv\ndef summarize(text):\n    values=parse_csv(text)\n    return {'count':len(values),'sum':sum(values),'mean':sum(values)/len(values) if values else None}\n"}}


def replies(task_id, usage=True):
    counts = {"input":100,"output":20,"total":125,"thought":5,"cached":0,"available":True}
    values = [{"text":"", "tool_calls":[{"name":"write_file", "args":{"path":path,"content":source}} for path,source in SOURCES[task_id].items()]},
              {"text":"PRIVATE_CLAIM_OF_SUCCESS", "tool_calls":[]}]
    if usage:
        for value in values: value["usage_details"] = counts
    return values

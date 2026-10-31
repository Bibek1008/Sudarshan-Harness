"""Day 5: live two-phase product builds with explicit sessions and turn evidence.

This runner never substitutes scripted provider replies. It records observed
assistant events, requires skill loading, and resumes the exact build session
for review. A successful model report is not a mechanical product pass.
"""

import json
from pathlib import Path

from sudarshan import Harness, run_fleet
from sudarshan.provider import api_key


QUALITY = "A real design system as CSS custom properties; at least 9 distinct sections for a landing page; at least 1,200 words of real copy, no lorem ipsum; at least 4 hand-drawn inline SVG illustrations, one being a product artifact in the hero; at least 3 working interactive behaviors; responsive at 360, 768, and 1280; semantic HTML with focus states; a self-review pass before finishing that counts sections, words, SVGs, and interactions against these minimums and fixes any shortfall."
REVIEW = "Review every file you produced against the skill bar as a demanding design director; list 12 concrete deficiencies; fix them all; verify again."
TASKS = {
    'artisan-coffee': '''Build a self-contained index.html for a premium specialty coffee roaster
in Goa. Include sticky navigation, hero product-artifact SVG, six origin cards
with prices, three subscription tiers with working monthly/annual toggle,
brew-guide tabs, FAQ accordion and dark mode persisted in localStorage.
Use 9 meaningful sections, over 1200 visible original words, four hand-drawn SVGs,
CSS custom properties, semantic HTML, visible focus and accessible contrast.
Verify layout at 360, 768, 1280 and exercise all controls. No hidden filler.
Write a verification report with actual measured counts and checks.''',
    'taskman': '''Build taskman.py using Python standard library: argparse add/list/done/rm/stats,
JSON persistence, stable IDs, aligned tables, validation, graceful missing and
malformed storage handling, configurable store. Add at least 10 meaningful
unittest tests calling the CLI with subprocess and a temporary store per test.
Run and fix all tests. Write README.md usage examples. Website-specific parts
of the skill do not apply; verify project-specific correctness and usability.''',
    'viper': '''Build one self-contained index.html containing a complete playable canvas Snake
game with grid movement, requestAnimationFrame, food generation, speed-up each
five foods, score, pause/resume, restart, persisted high score in localStorage,
keyboard controls, game-over state, responsive layout and accessible buttons.
Include instructions and an original design. Test game logic and actual controls.
Website word/section quotas do not apply; verify gameplay and usability.''',
}


def main() -> None:
    """Run fresh live builds and same-session reviews, saving truthful run evidence."""
    api_key()  # Fail before creating workspaces when credentials are absent.
    root = Path('projects').resolve()
    for name in TASKS:
        if (root / name).exists():
            raise RuntimeError(f'{root / name} already exists; preserve it and choose fresh workspaces')
    for name in TASKS:
        skill = root / name / 'skills' / 'design-engineering' / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\ndescription: Product engineering quality bar.\n---\n\n' + QUALITY + '\n', encoding='utf-8')
    evidence = {}
    sessions = {}

    def factory(workdir, phase):
        name = Path(workdir).name
        record = evidence.setdefault(name, {})[phase] = {'turns': 0, 'skill_loaded': False}
        def event(kind, payload):
            if kind == 'assistant':
                record['turns'] += 1
            if kind == 'tool_end' and payload['name'] == 'use_skill':
                record['skill_loaded'] = QUALITY in payload['text']
        harness = Harness(workdir, on_event=event, enable_subagents=False,
                          system_extra='Load design-engineering with use_skill before working. Write review findings and verification evidence to REVIEW.md. For non-landing-page tasks use project-specific requirements.')
        if phase == 'review':
            harness.resume(sessions[name])
        else:
            from sudarshan.session import new_session
            harness.session_path = new_session(workdir, name)
            sessions[name] = str(harness.session_path)
        record['session'] = str(harness.session_path)
        return harness

    jobs = [{'name': n, 'workdir': str(root / n), 'task': t} for n, t in TASKS.items()]
    builds = run_fleet(jobs, lambda directory: factory(directory, 'build'), max_workers=3)
    successful = {r['name'] for r in builds if r['ok']}
    review_jobs = [dict(job, task=REVIEW) for job in jobs if job['name'] in successful]
    reviews = run_fleet(review_jobs, lambda directory: factory(directory, 'review'), max_workers=3)
    report = {'builds': builds, 'reviews': reviews, 'evidence': evidence,
              'acceptance': 'Not determined: independently verify products and run additional repair passes on failures.'}
    (root / 'run-evidence.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

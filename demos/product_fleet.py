"""Day 5: live two-phase product builds with explicit sessions and turn evidence.

This runner never substitutes scripted provider replies. It records observed
assistant events, requires skill loading, and resumes the exact build session
for review. A successful model report is not a mechanical product pass.
"""

import json
from pathlib import Path

from sudarshan import run_fleet
from sudarshan.provider import api_key
from demos.product_approval import product_harness
from demos.product_verify import verify_product


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
malformed storage handling. Use a global --store PATH option, add TITLE,
list, done ID, rm ID and stats. Store a JSON list (or object with tasks list),
with id, title and boolean done fields. Add at least 10 meaningful
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
    report = run_products(Path('projects'))
    print(json.dumps(report, indent=2))


def run_products(root: Path, manual_evidence=None, browser_probe=None) -> dict:
    """Build, gate, repair and review; model text alone never establishes success."""
    root = root.resolve()
    if (root / 'run-evidence.json').exists():
        raise RuntimeError('Existing fleet evidence must not be overwritten')
    for name in TASKS:
        if (root / name).exists():
            raise RuntimeError(f'{root / name} already exists; preserve it and choose fresh workspaces')
    for name in TASKS:
        skill = root / name / 'skills' / 'design-engineering' / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\ndescription: Product engineering quality bar.\n---\n\n' + QUALITY + '\n', encoding='utf-8')
    evidence = {}
    sessions = {}
    report = {'evidence': evidence, 'phases': {}, 'acceptance': 'Incomplete: verification pending'}

    def save():
        (root / 'run-evidence.json').write_text(json.dumps(report, indent=2), encoding='utf-8')

    def factory(workdir, phase):
        name = Path(workdir).name
        record = evidence.setdefault(name, {})[phase] = {'turns': 0, 'skill_loaded': False}
        def event(kind, payload):
            if kind == 'assistant':
                record['turns'] += 1
            if kind == 'tool_end' and payload['name'] == 'use_skill':
                record['skill_loaded'] |= QUALITY in payload['text']
        harness = product_harness(workdir, on_event=event,
                          system_extra='Load design-engineering with use_skill in each phase before working. Write review findings and verification evidence to REVIEW.md. Only project file edits and the required skill are approved. For tests use exactly: python -m unittest discover -v (or python -m unittest discover -s tests -v). No arbitrary shell commands are approved. For non-landing-page tasks use project-specific requirements.')
        if phase != 'build':
            if not harness.resume(sessions[name]):
                raise RuntimeError(f'Could not resume build session for {name}')
        else:
            from sudarshan.session import new_session
            harness.session_path = new_session(workdir, name)
            sessions[name] = str(harness.session_path)
        record['session'] = str(harness.session_path)
        return harness

    jobs = [{'name': n, 'workdir': str(root / n), 'task': t} for n, t in TASKS.items()]

    def inspect(name, final=False):
        options = {'browser_probe': browser_probe} if browser_probe is not None else {}
        if final and manual_evidence and name in manual_evidence:
            options['manual_evidence'] = manual_evidence[name]
        return verify_product(name, root / name, **options)

    def phase(selected, label):
        results = run_fleet(selected, lambda directory: factory(directory, label), max_workers=3)
        for result in results:
            name = result['name']
            result['model_ok'] = result['ok']
            result['verification'] = inspect(name)
            loaded = evidence.get(name, {}).get(label, {}).get('skill_loaded', False)
            result['skill_loaded'] = loaded
            result['ok'] = bool(result['ok'] and loaded and result['verification']['automated_ok'])
        report['phases'][label] = results
        save()
        return {result['name']: result for result in results}

    def repairs(latest, label):
        selected = [dict(job, task='Repair the independently observed failures, then verify again. '
                         'Load the required skill. Requirements: ' + TASKS[job['name']] +
                         '\nObserved failures: ' + json.dumps(latest[job['name']]))
                    for job in jobs if not latest[job['name']]['ok']]
        return phase(selected, label) if selected else {}

    builds = phase(jobs, 'build')
    current = dict(builds)
    current.update(repairs(current, 'build_repair'))
    eligible = [dict(job, task=REVIEW) for job in jobs if current[job['name']]['ok']]
    reviews = phase(eligible, 'review')
    for job in jobs:
        name = job['name']
        if name not in reviews:
            reviews[name] = {'name': name, 'ok': False, 'status': 'blocked',
                             'report': 'Review blocked: artifact/skill gate failed after build repair',
                             'verification': current[name]['verification']}
    report['builds'] = list(builds.values())
    report['reviews'] = [reviews[job['name']] for job in jobs]
    save()
    repaired = repairs(reviews, 'review_repair')
    if repaired:
        eligible = [dict(job, task=REVIEW) for job in jobs if repaired.get(job['name'], {}).get('ok')]
        final_reviews = phase(eligible, 'final_review')
        reviews.update(final_reviews)
    # Always inspect every project again after the last review, including failures.
    final = []
    for job in jobs:
        name = job['name']
        verification = inspect(name, final=True)
        reviewed = reviews[name]['ok']
        final.append({'name': name, 'ok': bool(reviewed and verification['accepted']),
                      'automated_passed': verification['automated_ok'],
                      'manual_pending': verification.get('manual_pending', not verification['accepted']),
                      'manual_passed': verification.get('manual_passed', False),
                      'final_accepted': bool(reviewed and verification['accepted']),
                      'review_ok': reviewed, 'verification': verification,
                      'status': 'accepted' if reviewed and verification['accepted'] else 'incomplete'})
    report['final'] = final
    report['acceptance'] = 'Accepted' if all(result['ok'] for result in final) else 'Incomplete: see final verification and manual checks'
    save()
    return report


if __name__ == '__main__':
    main()

"""Day 1: hand-written tool schema and neutral-loop dice demonstration.

Keep the first example independent of decorators and Harness composition;
randomness is local and only the model conversation requires credentials.
"""

import random

from sudarshan.loop import run_loop
from sudarshan.provider import DEFAULT_MODEL
from sudarshan.tools import Tool


def roll_dice(count: str = '3') -> str:
    """Roll the requested number of six-sided dice and report the total."""
    number = int(count)
    if not 1 <= number <= 100:
        raise ValueError('count must be between 1 and 100')
    rolls = [random.randint(1, 6) for _ in range(number)]
    return f'Rolls: {rolls}; total: {sum(rolls)}'


def on_event(kind, payload):
    """Print model replies and tool lifecycle events."""
    print(f'{kind}: {payload}')


def main():
    """Ask the model to roll three dice through a manually specified Tool."""
    dice = Tool('roll_dice', {'schema': {
        'name': 'roll_dice', 'description': 'Roll six-sided dice.',
        'parameters': {'type': 'object', 'properties': {
            'count': {'type': 'string', 'description': 'Number of dice.'}}, 'required': []},
    }}, roll_dice)
    run_loop(DEFAULT_MODEL, 'Use the dice tool to answer the task.',
             [{'role': 'user', 'text': 'Roll 3 dice and tell me whether the total beats 10'}],
             {'roll_dice': dice}, on_event, lambda call: None)


if __name__ == '__main__':
    main()

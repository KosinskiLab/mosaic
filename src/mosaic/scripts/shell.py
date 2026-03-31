"""
Entry point for the ``mosaic-shell`` interactive scripting interface.

Copyright (c) 2024-2026 European Molecular Biology Laboratory

Author: Valentin Maurer <valentin.maurer@embl-hamburg.de>
"""

import argparse


def main():
    parser = argparse.ArgumentParser(description="Mosaic interactive shell")
    parser.add_argument("script", nargs="?", help="Script file to execute")
    parser.add_argument("-c", "--command", help="Execute a single command")
    parser.add_argument("--log", metavar="PATH", help="Log commands to a file")
    args = parser.parse_args()

    from mosaic.commands.repl import MosaicREPL

    repl = MosaicREPL(log_file=args.log)

    if args.command:
        output = repl.execute(args.command)
        if output:
            repl._console.print(output)
    elif args.script:
        output = repl.execute_script(args.script)
        if output:
            repl._console.print(output)
    else:
        repl.run()


if __name__ == "__main__":
    main()

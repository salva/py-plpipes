import plpipes.init
import plpipes.action
import sys
import argparse
import os
import pathlib
import json
import logging

class _PairAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, unpack=None, default=None, **kwargs):
        if nargs is not None:
            raise ValueError("nargs not allowed")
        if default is None:
            default = {}
        super().__init__(option_strings, dest, nargs=1, default=default, **kwargs)
        self.unpack = unpack

    def __call__(self, parser, namespace, values, option_string=None):
        if self.unpack:
            if self.unpack == "json":
                unpacker = lambda x: json.loads(x)
            else:
                raise Exception(f"Bad unpacker {unpack}")
        else:
            unpacker = None
        for pair in values:
            try:
                (k, v) = pair.split("=", 2)
            except:
                raise argparse.ArgumentError(self, f"Can not parse config pair '{pair}'")
            if unpacker:
                try:
                    v = unpacker(v)
                except:
                    raise argparse.ArgumentError(self, f"Can not unpack value part of '{pair}' as {self.unpack}.")
            try:
                getattr(namespace, self.dest).append({k:v})
            except Exception as ex:
                raise argparse.ArgumentError(self, f"Conflicting config pair '{pair}': {ex}") from ex

def main(args=None):
    if args is None:
        args = sys.argv

    if len(args) < 1:
        raise Exception("Unable to infer config stem. Program name missing from argument list")

    prog_path = pathlib.Path(args[0])
    stem = prog_path.stem
    if "PLPIPES_ROOT_DIR" in os.environ:
        root_dir = libpath.Path(os.environ["PLPIPES_ROOT_DIR"]).resolve(strict=True)
    else:
        root_dir = prog_path.parent.parent

    config_extra = [{ 'fs': { 'stem': str(prog_path.stem),
                              'root': str(root_dir) }}]

    parser = argparse.ArgumentParser(description="PLPipes runner")

    parser.add_argument('-d', '--debug',
                        help="Turns on debugging",
                        action='store_true')
    parser.add_argument('-c', '--config',
                        action="append",
                        metavar="CFG_FN",
                        help="Additional configuration file",
                        default=[])
    parser.add_argument('-s', '--set',
                        action=_PairAction,
                        metavar="CFG_KEY=VAL",
                        help="Set configuration entry",
                        default=config_extra)
    parser.add_argument('-S', '--set-json',
                        action=_PairAction,
                        metavar="CFG_KEY=JSON_VAL",
                        unpack="json",
                        dest="set",
                        help="Set configuration entry (value is parsed as JSON)",
                        default=config_extra)
    parser.add_argument('-e', '--env',
                        metavar="ENVIRONMENT",
                        help="Select environment (dev, pre, pro, etc.)")

    parser.add_argument('actions', nargs="*",
                        metavar="ACTION", default=["default"])

    opts = parser.parse_args(args[1:])

    if opts.env is not None:
        config_extra["env"] = opts.env
    if opts.debug:
        config_extra.append({"logging.level": "debug"})

    # print(f"actions {opts.action}")

    plpipes.init.init(*config_extra, config_files=opts.config)

    for action in opts.actions:
        logging.info(f"Executing action {action}")
        plpipes.action.run(action)

